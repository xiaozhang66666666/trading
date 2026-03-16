"""CLI entry for fetch/backtest/simulate workflows."""

from __future__ import annotations

import argparse
import errno
import gzip
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.data.manager import DataManager
from market_signal_system.data.quality import diagnose_ohlcv_quality
from market_signal_system.mvp import MvpPipelineConfig, run_mvp_pipeline
from market_signal_system.research import (
    analyze_walk_forward_stability,
    build_baseline_daily_summary,
    build_report_index,
    build_leaderboard,
    build_symbol_leaderboard,
    export_champion_switch_trend_csv,
    run_portfolio_backtest_detailed,
    run_grid_search,
    run_walk_forward,
)
from market_signal_system.signal_pilot import dispatch_alerts, report_alerts, scan_alerts, update_alerts
from market_signal_system.simulation.broker import create_broker
from market_signal_system.storage import DEFAULT_ACCOUNT_ID, SQLiteStore, normalize_account_id
from market_signal_system.strategies import get_strategy
from market_signal_system.utils.paths import OUTPUT_DIR, ensure_runtime_dirs

STRATEGY_CHOICES = [
    "ma_cross",
    "donchian",
    "momentum",
    "regime",
    "macd_regime",
    "atr_regime",
    "score_regime",
    "dual_momentum",
]
COMPARE_DEFAULT_STRATEGIES = ",".join(STRATEGY_CHOICES)


def _resolve_account_state_file(account_id: str | None, state_file: str) -> str:
    account = normalize_account_id(account_id)
    if account == DEFAULT_ACCOUNT_ID:
        return state_file
    if state_file in {"paper_broker.json", "paper_portfolio.json"}:
        return f"{account}__{state_file}"
    return state_file


def _parse_params(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--params 必须是 JSON 对象")
    return parsed


def _parse_grid(raw: str | None) -> dict[str, list[object]] | None:
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--grid 必须是 JSON 对象，值为列表")
    for key, value in parsed.items():
        if not isinstance(value, list):
            raise ValueError(f"--grid 字段 {key} 必须是列表")
    return parsed


def _normalize_config_value(key: str, value: Any) -> Any:
    if key in {"symbols", "strategies"} and isinstance(value, list):
        return ",".join(str(v) for v in value)
    if key in {"params", "grid", "simulate_params"} and isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _resolve_placeholders(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item, variables) for item in value]
    if not isinstance(value, str):
        return value

    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise ValueError(f"vars 缺少占位符变量: {key}")
        return str(variables[key])

    return pattern.sub(repl, value)


def _load_config_payload(config_path: str) -> dict[str, Any]:
    config_file = Path(config_path)
    text = config_file.read_text(encoding="utf-8")
    if config_file.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("配置文件必须是 JSON 对象（或 YAML 对象）")
    return payload


_CONFIG_SCHEMA_CACHE: dict[str, dict[str, Any]] | None = None


def _build_config_schema() -> dict[str, dict[str, Any]]:
    parser = build_parser()
    subparser_action: argparse._SubParsersAction | None = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparser_action = action
            break
    if subparser_action is None:
        return {}

    schema: dict[str, dict[str, Any]] = {}
    for command, subparser in subparser_action.choices.items():
        if command in {"run-config", "batch"}:
            continue
        actions: dict[str, argparse.Action] = {}
        required_fields: set[str] = set()
        for action in subparser._actions:
            if action.dest in {"help", "command", "func"}:
                continue
            actions[action.dest] = action
            if getattr(action, "required", False):
                required_fields.add(action.dest)
        schema[command] = {
            "actions": actions,
            "allowed": set(actions.keys()),
            "required": required_fields,
        }
    return schema


def _get_config_schema() -> dict[str, dict[str, Any]]:
    global _CONFIG_SCHEMA_CACHE
    if _CONFIG_SCHEMA_CACHE is None:
        _CONFIG_SCHEMA_CACHE = _build_config_schema()
    return _CONFIG_SCHEMA_CACHE


def _is_boolean_action(action: argparse.Action) -> bool:
    return isinstance(action, (argparse.BooleanOptionalAction, argparse._StoreTrueAction, argparse._StoreFalseAction))


def _validate_config_value_type(command: str, key: str, value: Any, action: argparse.Action) -> None:
    if value is None:
        return

    if key in {"symbols", "strategies"} and isinstance(value, list):
        return
    if key in {"params", "grid", "simulate_params"} and isinstance(value, dict):
        return

    if _is_boolean_action(action):
        if not isinstance(value, bool):
            raise ValueError(f"{command}.{key} 必须是布尔值")
        return

    expected_type = action.type
    if expected_type is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{command}.{key} 必须是整数")
    elif expected_type is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{command}.{key} 必须是数字")
    elif expected_type is str:
        if not isinstance(value, str):
            raise ValueError(f"{command}.{key} 必须是字符串")

    if action.choices and not isinstance(value, (dict, list)):
        if value not in action.choices:
            allowed = ", ".join(str(item) for item in action.choices)
            raise ValueError(f"{command}.{key} 不在允许取值中: {value}（可选: {allowed}）")


def _to_float_if_numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _validate_config_value_ranges(command: str, provided: dict[str, Any]) -> None:
    non_negative_fields = {
        "fee_rate",
        "slippage_bps",
        "cooldown_bars",
        "risk_cooldown_bars",
        "min_quantity",
        "retry_count",
        "retry_delay_ms",
        "idempotency_window_minutes",
        "champion_switch_watch_threshold",
        "champion_switch_high_threshold",
        "signal_min_count",
        "dispatch_max_failed_count",
    }
    positive_fields = {
        "bars_per_year",
        "lookback_days",
        "max_holding_days",
        "quantity",
        "max_events",
        "timeout_sec",
        "champion_switch_recent_runs",
        "signal_alert_window_days",
        "dispatch_window_days",
    }
    unit_interval_fields = {
        "max_drawdown",
        "max_portfolio_drawdown",
        "cash_reserve_ratio",
        "max_symbol_allocation",
        "max_total_allocation",
        "dispatch_max_failed_ratio",
    }

    for key, value in provided.items():
        numeric_value = _to_float_if_numeric(value)
        if numeric_value is None:
            continue
        if key in non_negative_fields and numeric_value < 0:
            raise ValueError(f"{command}.{key} 必须 >= 0")
        if key in positive_fields and numeric_value <= 0:
            raise ValueError(f"{command}.{key} 必须 > 0")
        if key in unit_interval_fields and not (0 <= numeric_value <= 1):
            raise ValueError(f"{command}.{key} 必须在 [0, 1] 区间内")
        if key == "allocation_per_signal" and not (0 < numeric_value <= 1):
            raise ValueError(f"{command}.{key} 必须在 (0, 1] 区间内")
        if key == "signal_min_win_rate" and not (0 <= numeric_value <= 1):
            raise ValueError(f"{command}.{key} 必须在 [0, 1] 区间内")


def _validate_config_args(command: str, args_raw: dict[str, Any], defaults: dict[str, Any]) -> None:
    schema = _get_config_schema().get(command)
    if schema is None:
        raise ValueError(f"Unsupported command in config: {command}")

    actions: dict[str, argparse.Action] = schema["actions"]
    allowed: set[str] = schema["allowed"]
    required: set[str] = schema["required"]
    provided: dict[str, Any] = {}
    unknown_keys: list[str] = []

    for raw_key, value in args_raw.items():
        if raw_key in {"command", "args", "vars"}:
            continue
        key = raw_key.replace("-", "_")
        provided[key] = value
        if key not in allowed:
            unknown_keys.append(raw_key)

    if unknown_keys:
        joined = ", ".join(sorted(unknown_keys))
        raise ValueError(f"{command} 配置包含不支持字段: {joined}")

    missing_required = sorted(field for field in required if field not in provided and field not in defaults)
    if missing_required:
        joined = ", ".join(missing_required)
        raise ValueError(f"{command} 缺少必填字段: {joined}")

    for key, value in provided.items():
        action = actions.get(key)
        if action is None:
            continue
        _validate_config_value_type(command, key, value, action)
    _validate_config_value_ranges(command, provided)


def _config_defaults(command: str) -> dict[str, Any]:
    if command == "fetch":
        return {"interval": "1d", "no_cache": False}
    if command == "update-cache":
        return {"symbols": "QQQ,ETH", "interval": "1d"}
    if command == "diagnose-data":
        return {"interval": "1d", "no_cache": False, "output_file": None}
    if command == "backtest":
        return {
            "interval": "1d",
            "fee_rate": 0.0008,
            "slippage_bps": 5.0,
            "bars_per_year": 252,
            "max_drawdown": None,
            "cooldown_bars": 20,
            "params": None,
            "output_tag": None,
        }
    if command == "simulate":
        return {
            "interval": "1d",
            "state_file": "paper_broker.json",
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
            "quantity": 1.0,
            "allocation_per_signal": None,
            "min_quantity": 0.0,
            "output_tag": None,
            "summary_file": None,
            "params": None,
        }
    if command == "mvp":
        return {
            "symbols": "QQQ,ETH",
            "strategies": "ma_cross,donchian,momentum",
            "simulate_strategy": "momentum",
            "simulate_params": None,
            "interval": "1d",
            "fee_rate": 0.0008,
            "slippage_bps": 5.0,
            "bars_per_year": 252,
            "max_drawdown": None,
            "cooldown_bars": 20,
            "quantity": 1.0,
            "state_prefix": None,
            "run_tag": None,
            "output_file": None,
            "strict_acceptance": False,
        }
    if command == "simulate-portfolio":
        return {
            "symbols": "QQQ,ETH",
            "strategy": "momentum",
            "interval": "1d",
            "state_file": "paper_portfolio.json",
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
            "allocation_per_signal": 0.3,
            "max_symbol_allocation": 0.4,
            "max_total_allocation": 1.0,
            "initial_margin_rate": 1.0,
            "cash_reserve_ratio": 0.05,
            "max_portfolio_drawdown": None,
            "risk_cooldown_bars": 20,
            "summary_file": None,
            "params": None,
        }
    if command == "research":
        return {
            "interval": "1d",
            "objective": "sharpe",
            "grid": None,
            "train_bars": 504,
            "test_bars": 126,
            "step_bars": None,
            "fee_rate": 0.0008,
            "slippage_bps": 5.0,
            "bars_per_year": 252,
            "max_drawdown": None,
            "cooldown_bars": 20,
        }
    if command == "compare":
        return {
            "symbols": "QQQ,ETH",
            "strategies": COMPARE_DEFAULT_STRATEGIES,
            "interval": "1d",
            "fee_rate": 0.0008,
            "slippage_bps": 5.0,
            "bars_per_year": 252,
            "max_drawdown": None,
            "cooldown_bars": 20,
        }
    if command == "portfolio":
        return {
            "symbols": "QQQ,ETH",
            "strategy": "ma_cross",
            "interval": "1d",
            "fee_rate": 0.0008,
            "slippage_bps": 5.0,
            "bars_per_year": 252,
            "allocation_mode": "equal",
            "vol_window": 20,
            "target_vol": 0.15,
            "max_leverage": 1.5,
            "corr_watch_threshold": 0.75,
            "corr_high_threshold": 0.85,
            "crowding_watch_threshold": 0.15,
            "crowding_high_threshold": 0.2,
            "drift_watch_threshold": 0.08,
            "drift_high_threshold": 0.15,
            "rebalance_on_drift": False,
            "rebalance_trigger": "high",
            "rebalance_scale": 1.0,
            "params": None,
        }
    if command == "report":
        return {
            "output_file": "report_index.md",
            "champion_switch_csv_file": "champion_switch_last_runs.csv",
            "champion_switch_recent_runs": 10,
            "champion_switch_watch_threshold": 1,
            "champion_switch_high_threshold": 2,
        }
    if command == "stability":
        return {"summary_file": None, "freq_file": None}
    if command == "scan-alerts":
        return {
            "symbols": "QQQ,ETH",
            "strategy": "score_regime",
            "interval": "1d",
            "lookback_days": 365,
            "end": None,
            "ledger_file": None,
            "notification_file": None,
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
            "params": None,
        }
    if command == "update-alerts":
        return {
            "ledger_file": None,
            "end": None,
            "max_holding_days": 60,
            "close_on_reverse": True,
            "symbols": None,
            "strategies": None,
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
        }
    if command == "report-alerts":
        return {
            "ledger_file": None,
            "as_of": None,
            "windows": "7,30,60",
            "output_prefix": "signal_pilot_alert_report",
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
        }
    if command == "dispatch-alerts":
        return {
            "queue_file": "signal_pilot_notifications.jsonl",
            "ledger_file": None,
            "webhook_url": None,
            "sink_file": "signal_pilot_notifications_dispatched.jsonl",
            "max_events": 200,
            "timeout_sec": 10.0,
            "retry_count": 0,
            "retry_delay_ms": 500,
            "idempotency_window_minutes": 0.0,
            "dry_run": False,
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
        }
    if command == "baseline-summary":
        return {
            "as_of": None,
            "output_json": "baseline_daily_digest.json",
            "output_csv": "baseline_daily_digest.csv",
            "mvp_summary_file": None,
            "signal_report_json_file": None,
            "report_index_file": "baseline_daily_report_index.md",
            "alert_ledger_file": None,
            "account_id": DEFAULT_ACCOUNT_ID,
            "db_file": None,
            "dispatch_window_days": 30,
            "signal_alert_window_days": 30,
            "signal_min_count": 3,
            "signal_min_win_rate": 0.5,
            "signal_min_avg_return_pct": 0.0,
            "simulation_min_return_pct": -0.05,
            "dispatch_max_failed_count": 3,
            "dispatch_max_failed_ratio": 0.5,
            "emit_alert_queue": False,
            "alert_queue_file": "baseline_summary_alerts.jsonl",
        }
    raise ValueError(f"Unsupported command in config: {command}")


def _parse_config_payload(payload: dict[str, Any], variables: dict[str, Any] | None = None) -> tuple[str, argparse.Namespace]:
    if not isinstance(payload, dict):
        raise ValueError("配置文件必须是 JSON 对象（或 YAML 对象）")

    merged_vars = dict(variables or {})
    local_vars = payload.get("vars")
    if local_vars is not None:
        if not isinstance(local_vars, dict):
            raise ValueError("vars 必须是 JSON 对象（或 YAML 对象）")
        merged_vars.update(local_vars)
    resolved_payload = _resolve_placeholders(payload, merged_vars)

    command = str(resolved_payload.get("command", "")).strip()
    if not command:
        raise ValueError("配置文件缺少 command 字段")
    if command in {"run-config", "batch"}:
        raise ValueError("run-config 不允许递归调用")

    args_raw = resolved_payload.get("args", resolved_payload)
    if not isinstance(args_raw, dict):
        raise ValueError("args 必须是 JSON 对象（或 YAML 对象）")

    unsupported_command = False
    try:
        defaults = _config_defaults(command)
    except ValueError as exc:
        if "Unsupported command in config" not in str(exc):
            raise
        defaults = {}
        unsupported_command = True

    if not unsupported_command:
        _validate_config_args(command, args_raw, defaults)
    merged = defaults.copy()
    for key, value in args_raw.items():
        if key in {"command", "args", "vars"}:
            continue
        norm_key = key.replace("-", "_")
        merged[norm_key] = _normalize_config_value(norm_key, value)
    return command, argparse.Namespace(**merged)


def _parse_config_task(config_path: str) -> tuple[str, argparse.Namespace]:
    payload = _load_config_payload(config_path)
    return _parse_config_payload(payload)


def _parse_config_tasks(config_path: str) -> list[tuple[str, argparse.Namespace]]:
    config_file = Path(config_path)
    payload = _load_config_payload(str(config_file))
    global_vars = payload.get("vars", {})
    if not isinstance(global_vars, dict):
        raise ValueError("vars 必须是 JSON 对象（或 YAML 对象）")

    raw_tasks = payload.get("tasks")
    command = str(payload.get("command", "")).strip().lower()
    if command == "batch" or isinstance(raw_tasks, list):
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError("batch 配置必须包含非空 tasks 列表")

        tasks: list[tuple[str, argparse.Namespace]] = []
        for item in raw_tasks:
            if isinstance(item, str):
                rendered_item = str(_resolve_placeholders(item, global_vars))
                task_path = (config_file.parent / rendered_item).resolve()
                tasks.append(_parse_config_payload(_load_config_payload(str(task_path)), global_vars))
                continue
            if not isinstance(item, dict):
                raise ValueError("tasks 每项必须是字符串路径或对象")
            if "file" in item:
                task_retry_override = _parse_task_retry_override(item.get("retry"), "tasks.file.retry")
                rendered_file = str(_resolve_placeholders(item["file"], global_vars))
                task_path = (config_file.parent / rendered_file).resolve()
                task_vars = dict(global_vars)
                item_vars = item.get("vars")
                if item_vars is not None:
                    if not isinstance(item_vars, dict):
                        raise ValueError("tasks.file.vars 必须是 JSON 对象（或 YAML 对象）")
                    task_vars.update(item_vars)
                task_command, task_args = _parse_config_payload(_load_config_payload(str(task_path)), task_vars)
                setattr(task_args, "_task_retry_override", task_retry_override)
                tasks.append((task_command, task_args))
                continue
            task_retry_override = _parse_task_retry_override(item.get("retry"), "tasks[].retry")
            task_vars = dict(global_vars)
            item_vars = item.get("vars")
            if item_vars is not None:
                if not isinstance(item_vars, dict):
                    raise ValueError("tasks[].vars 必须是 JSON 对象（或 YAML 对象）")
                task_vars.update(item_vars)
            task_item = item.copy()
            task_item.pop("retry", None)
            task_command, task_args = _parse_config_payload(task_item, task_vars)
            setattr(task_args, "_task_retry_override", task_retry_override)
            tasks.append((task_command, task_args))
        return tasks

    return [_parse_config_payload(payload, global_vars)]


def _parse_batch_error_mode(config_path: str) -> str:
    payload = _load_config_payload(config_path)
    mode = str(payload.get("on_error", "fail_fast")).strip().lower()
    if mode not in {"fail_fast", "continue"}:
        raise ValueError("on_error 仅支持 fail_fast 或 continue")
    return mode


def _resolve_summary_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    return OUTPUT_DIR / path


def _parse_batch_summary_paths(config_path: str, is_batch: bool) -> tuple[Path | None, Path | None]:
    payload = _load_config_payload(config_path)
    global_vars = payload.get("vars", {})
    if not isinstance(global_vars, dict):
        raise ValueError("vars 必须是 JSON 对象")
    summary_json = payload.get("summary_json")
    summary_csv = payload.get("summary_csv")
    if summary_json is not None and not isinstance(summary_json, str):
        raise ValueError("summary_json 必须是字符串")
    if summary_csv is not None and not isinstance(summary_csv, str):
        raise ValueError("summary_csv 必须是字符串")
    if summary_json is None and summary_csv is None and is_batch:
        summary_json = "run_config_batch_summary.json"
        summary_csv = "run_config_batch_summary.csv"
    if summary_json is not None:
        summary_json = str(_resolve_placeholders(summary_json, global_vars))
    if summary_csv is not None:
        summary_csv = str(_resolve_placeholders(summary_csv, global_vars))
    return _resolve_summary_path(summary_json), _resolve_summary_path(summary_csv)


def _parse_batch_summary_compress(config_path: str) -> str:
    payload = _load_config_payload(config_path)
    compress = str(payload.get("summary_compress", "none")).strip().lower()
    if compress not in {"none", "gzip"}:
        raise ValueError("summary_compress 仅支持 none 或 gzip")
    return compress


def _parse_retry_budget_trace_path(config_path: str, is_batch: bool) -> Path | None:
    payload = _load_config_payload(config_path)
    global_vars = payload.get("vars", {})
    if not isinstance(global_vars, dict):
        raise ValueError("vars 必须是 JSON 对象")
    trace_csv = payload.get("retry_budget_trace_csv")
    if trace_csv is not None and not isinstance(trace_csv, str):
        raise ValueError("retry_budget_trace_csv 必须是字符串")
    if trace_csv is None and is_batch and payload.get("max_total_retries") is not None:
        trace_csv = "run_config_retry_budget_trace.csv"
    if trace_csv is not None:
        trace_csv = str(_resolve_placeholders(trace_csv, global_vars))
    return _resolve_summary_path(trace_csv)


def _parse_retry_budget_trace_compress(config_path: str) -> str:
    payload = _load_config_payload(config_path)
    compress = str(payload.get("retry_budget_trace_compress", "none")).strip().lower()
    if compress not in {"none", "gzip"}:
        raise ValueError("retry_budget_trace_compress 仅支持 none 或 gzip")
    return compress


def _parse_compress_naming(config_path: str) -> str:
    payload = _load_config_payload(config_path)
    naming = str(payload.get("compress_naming", "auto_suffix")).strip().lower()
    if naming not in {"auto_suffix", "strict"}:
        raise ValueError("compress_naming 仅支持 auto_suffix 或 strict")
    return naming


def _apply_compress_suffix(path: Path, compress: str, naming: str = "auto_suffix") -> Path:
    if compress != "gzip":
        return path
    if path.suffix == ".gz":
        return path
    if naming == "strict":
        raise ValueError(f"压缩输出路径必须以 .gz 结尾: {path}")
    if naming == "auto_suffix":
        return path.with_name(path.name + ".gz")
    return path


def _parse_batch_retry_policy(config_path: str) -> tuple[int, int]:
    payload = _load_config_payload(config_path)
    retry_count = payload.get("retry_count", 0)
    retry_delay_ms = payload.get("retry_delay_ms", 0)
    if not isinstance(retry_count, int) or retry_count < 0:
        raise ValueError("retry_count 必须是 >= 0 的整数")
    if not isinstance(retry_delay_ms, int) or retry_delay_ms < 0:
        raise ValueError("retry_delay_ms 必须是 >= 0 的整数")
    return retry_count, retry_delay_ms


def _parse_batch_retry_switches(config_path: str) -> tuple[bool, bool]:
    payload = _load_config_payload(config_path)
    retry_count = payload.get("retry_count", 0)
    retry_enabled = payload.get("retry_enabled")
    retry_retryable_only = payload.get("retry_retryable_only", True)
    if retry_enabled is None:
        retry_enabled = bool(retry_count > 0)
    if not isinstance(retry_enabled, bool):
        raise ValueError("retry_enabled 必须是布尔值")
    if not isinstance(retry_retryable_only, bool):
        raise ValueError("retry_retryable_only 必须是布尔值")
    return retry_enabled, retry_retryable_only


def _parse_batch_retry_budget(config_path: str) -> int | None:
    payload = _load_config_payload(config_path)
    max_total_retries = payload.get("max_total_retries")
    if max_total_retries is None:
        return None
    if not isinstance(max_total_retries, int) or max_total_retries < 0:
        raise ValueError("max_total_retries 必须是 >= 0 的整数")
    return max_total_retries


def _parse_task_retry_override(raw: Any, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")

    parsed: dict[str, Any] = {}
    if "count" in raw:
        count = raw["count"]
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"{field_name}.count 必须是 >= 0 的整数")
        parsed["count"] = count
    if "delay_ms" in raw:
        delay_ms = raw["delay_ms"]
        if not isinstance(delay_ms, int) or delay_ms < 0:
            raise ValueError(f"{field_name}.delay_ms 必须是 >= 0 的整数")
        parsed["delay_ms"] = delay_ms
    if "enabled" in raw:
        enabled = raw["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError(f"{field_name}.enabled 必须是布尔值")
        parsed["enabled"] = enabled
    if "retryable_only" in raw:
        retryable_only = raw["retryable_only"]
        if not isinstance(retryable_only, bool):
            raise ValueError(f"{field_name}.retryable_only 必须是布尔值")
        parsed["retryable_only"] = retryable_only
    return parsed


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, OSError):
        if isinstance(exc, (FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError)):
            return False
        transient_errno = {
            errno.EAGAIN,
            errno.ECONNABORTED,
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.ENETRESET,
            errno.ENETUNREACH,
            errno.ETIMEDOUT,
        }
        if exc.errno in transient_errno:
            return True
    message = str(exc).lower()
    retryable_keywords = (
        "timeout",
        "timed out",
        "temporarily",
        "temporary",
        "connection",
        "network",
        "dns",
        "unavailable",
        "try again",
        "rate limit",
        "too many requests",
        "429",
        "500",
        "502",
        "503",
        "504",
        "连接",
        "网络",
        "超时",
        "限流",
        "稍后重试",
        "服务不可用",
    )
    return any(keyword in message for keyword in retryable_keywords)


def _extract_symbol_champions_from_leaderboard(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if df.empty or "symbol" not in df.columns or "strategy" not in df.columns:
        return []
    temp = df.copy()
    if "composite_score" not in temp.columns:
        temp["composite_score"] = 0.0
    temp["composite_score"] = pd.to_numeric(temp["composite_score"], errors="coerce").fillna(0.0)
    if "symbol_rank" in temp.columns:
        temp["symbol_rank"] = pd.to_numeric(temp["symbol_rank"], errors="coerce")
        champions = temp[temp["symbol_rank"] == 1]
        if champions.empty:
            champions = temp.sort_values("composite_score", ascending=False).groupby("symbol", as_index=False).head(1)
    else:
        champions = temp.sort_values("composite_score", ascending=False).groupby("symbol", as_index=False).head(1)
    champions = champions.sort_values("symbol", ascending=True)
    rows: list[dict[str, Any]] = []
    for _, row in champions.iterrows():
        score_value = pd.to_numeric(pd.Series([row.get("composite_score")]), errors="coerce").iloc[0]
        rows.append(
            {
                "symbol": str(row.get("symbol", "")),
                "strategy": str(row.get("strategy", "")),
                "composite_score": 0.0 if pd.isna(score_value) else float(score_value),
                "leaderboard_file": path.name,
            }
        )
    return rows


def _collect_compare_symbol_champions(args: argparse.Namespace) -> list[dict[str, Any]]:
    symbols = [s.strip().upper() for s in str(getattr(args, "symbols", "")).split(",") if s.strip()]
    if not symbols:
        return []
    path = OUTPUT_DIR / f"leaderboard_by_symbol_{'_'.join(symbols)}.csv"
    return _extract_symbol_champions_from_leaderboard(path)


def _compute_counter_delta(
    initial: dict[str, Any],
    final: dict[str, Any],
) -> tuple[int, dict[str, int]]:
    initial_total = int(initial.get("skipped_duplicate_bars_total", 0))
    final_total = int(final.get("skipped_duplicate_bars_total", 0))
    initial_by_symbol = {
        str(symbol): int(value)
        for symbol, value in dict(initial.get("skipped_duplicate_bars_by_symbol", {})).items()
    }
    final_by_symbol = {
        str(symbol): int(value)
        for symbol, value in dict(final.get("skipped_duplicate_bars_by_symbol", {})).items()
    }

    delta_by_symbol: dict[str, int] = {}
    for symbol in sorted(set(initial_by_symbol.keys()) | set(final_by_symbol.keys())):
        delta = int(final_by_symbol.get(symbol, 0)) - int(initial_by_symbol.get(symbol, 0))
        if delta != 0:
            delta_by_symbol[symbol] = delta
    return final_total - initial_total, delta_by_symbol


def cmd_fetch(args: argparse.Namespace) -> None:
    dm = DataManager()
    df = dm.get_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
        use_cache=not args.no_cache,
        incremental=True,
    )
    print(f"Fetched {args.symbol} rows={len(df)} from {df.index.min()} to {df.index.max()}")


def cmd_update_cache(args: argparse.Namespace) -> None:
    dm = DataManager()
    symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    if not symbols:
        raise ValueError("--symbols 不能为空")

    updates: list[dict[str, object]] = []
    for symbol in symbols:
        summary = dm.update_cache(
            symbol=symbol,
            start=args.start,
            end=args.end,
            interval=args.interval,
        )
        updates.append(summary)

    result = {
        "command": "update-cache",
        "start": args.start,
        "end": args.end,
        "interval": args.interval,
        "symbol_count": len(updates),
        "cache_rows_added_total": int(sum(int(item["cache_rows_added"]) for item in updates)),
        "cache_changed_count": int(sum(1 for item in updates if bool(item["cache_changed"]))),
        "results": updates,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_mvp(args: argparse.Namespace) -> None:
    config = MvpPipelineConfig(
        start=args.start,
        end=args.end,
        symbols=[s.strip().upper() for s in str(args.symbols).split(",") if s.strip()],
        strategies=[s.strip().lower() for s in str(args.strategies).split(",") if s.strip()],
        simulate_strategy=str(args.simulate_strategy),
        simulate_params=_parse_params(getattr(args, "simulate_params", None)),
        interval=str(args.interval),
        fee_rate=float(args.fee_rate),
        slippage_bps=float(args.slippage_bps),
        bars_per_year=int(args.bars_per_year),
        max_drawdown=args.max_drawdown,
        cooldown_bars=int(args.cooldown_bars),
        quantity=float(args.quantity),
        run_tag=getattr(args, "run_tag", None),
        state_prefix=getattr(args, "state_prefix", None),
        output_file=getattr(args, "output_file", None),
    )
    summary_path, summary = run_mvp_pipeline(config)
    print(f"MVP pipeline done, summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if bool(getattr(args, "strict_acceptance", False)) and not bool(summary["mvp_acceptance"]["overall_passed"]):
        failed = ",".join(summary["mvp_acceptance"]["failed_check_ids"])
        raise ValueError(f"MVP 验收未通过（strict 模式）: {failed}")


def cmd_scan_alerts(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("--symbols 不能为空")
    summary = scan_alerts(
        symbols=symbols,
        strategy_name=args.strategy,
        interval=args.interval,
        strategy_params=_parse_params(args.params),
        lookback_days=int(args.lookback_days),
        end=args.end,
        ledger_path=args.ledger_file,
        notification_file=args.notification_file,
        account_id=args.account_id,
        db_path=args.db_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_update_alerts(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    symbols = [s.strip().upper() for s in (args.symbols or "").split(",") if s.strip()]
    strategies = [s.strip().lower() for s in (args.strategies or "").split(",") if s.strip()]
    summary = update_alerts(
        ledger_path=args.ledger_file,
        end=args.end,
        max_holding_days=int(args.max_holding_days),
        close_on_reverse=bool(args.close_on_reverse),
        symbols=symbols,
        strategies=strategies,
        account_id=args.account_id,
        db_path=args.db_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_report_alerts(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    windows = [int(x) for x in str(args.windows).split(",") if x.strip()]
    summary = report_alerts(
        ledger_path=args.ledger_file,
        as_of=args.as_of,
        windows=windows,
        output_prefix=args.output_prefix,
        account_id=args.account_id,
        db_path=args.db_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_dispatch_alerts(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    summary = dispatch_alerts(
        queue_file=args.queue_file,
        ledger_path=args.ledger_file,
        webhook_url=args.webhook_url,
        sink_file=args.sink_file,
        max_events=int(args.max_events),
        timeout_sec=float(args.timeout_sec),
        retry_count=int(args.retry_count),
        retry_delay_ms=int(args.retry_delay_ms),
        idempotency_window_minutes=float(args.idempotency_window_minutes),
        dry_run=bool(args.dry_run),
        account_id=args.account_id,
        db_path=args.db_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_baseline_summary(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    summary = build_baseline_daily_summary(
        OUTPUT_DIR,
        as_of=args.as_of,
        mvp_summary_file=args.mvp_summary_file,
        signal_report_json_file=args.signal_report_json_file,
        report_index_file=args.report_index_file,
        alert_ledger_file=args.alert_ledger_file,
        account_id=args.account_id,
        db_file=args.db_file,
        dispatch_window_days=int(args.dispatch_window_days),
        signal_alert_window_days=int(args.signal_alert_window_days),
        signal_min_count=int(args.signal_min_count),
        signal_min_win_rate=float(args.signal_min_win_rate),
        signal_min_avg_return_pct=float(args.signal_min_avg_return_pct),
        simulation_min_return_pct=float(args.simulation_min_return_pct),
        dispatch_max_failed_count=int(args.dispatch_max_failed_count),
        dispatch_max_failed_ratio=float(args.dispatch_max_failed_ratio),
    )
    json_path = OUTPUT_DIR / args.output_json
    csv_path = OUTPUT_DIR / args.output_csv
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(summary.get("rows", [])).to_csv(csv_path, index=False)

    queue_count = 0
    if bool(getattr(args, "emit_alert_queue", False)):
        queue_path = OUTPUT_DIR / str(getattr(args, "alert_queue_file", "baseline_summary_alerts.jsonl"))
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        events: list[dict[str, Any]] = []
        for alert in summary.get("alerts", []):
            if not isinstance(alert, dict):
                continue
            alert_id = str(alert.get("alert_id", "")).strip()
            if not alert_id:
                continue
            events.append(
                {
                    "alert_id": alert_id,
                    "source": "baseline-summary",
                    "as_of": summary.get("as_of"),
                    "level": str(alert.get("level", "")),
                    "metric": str(alert.get("metric", "")),
                    "value": alert.get("value"),
                    "threshold": alert.get("threshold"),
                    "message": str(alert.get("message", "")),
                }
            )
        queue_count = len(events)
        queue_path.write_text(
            "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
            encoding="utf-8",
        )

    print(f"Baseline summary generated: {json_path}")
    print(f"Baseline summary CSV generated: {csv_path}")
    if bool(getattr(args, "emit_alert_queue", False)):
        print(f"Baseline alert queue generated: {queue_path}")
        print(f"Baseline alert queue count: {queue_count}")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=2))


def cmd_diagnose_data(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    df = dm.get_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
        use_cache=not args.no_cache,
        incremental=True,
    )
    result = diagnose_ohlcv_quality(df)

    output_path = OUTPUT_DIR / (args.output_file or f"data_quality_{args.symbol}_{args.interval}.json")
    output_path.write_text(json.dumps(result.report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved data quality report: {output_path}")

    if not result.anomalies.empty:
        anomalies_path = OUTPUT_DIR / f"data_quality_anomalies_{args.symbol}_{args.interval}.csv"
        result.anomalies.to_csv(anomalies_path, index=False)
        print(f"Saved anomalies: {anomalies_path}")

    print(json.dumps(result.report, ensure_ascii=False, indent=2))


def cmd_backtest(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    strategy = get_strategy(args.strategy, **_parse_params(args.params))

    data = dm.get_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
    )
    result = BacktestEngine(
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        bars_per_year=args.bars_per_year,
        max_drawdown=args.max_drawdown,
        cooldown_bars=args.cooldown_bars,
    ).run(data=data, strategy=strategy, symbol=args.symbol)

    tag = f"_{args.output_tag}" if getattr(args, "output_tag", None) else ""
    metrics_path = OUTPUT_DIR / f"metrics_{args.symbol}_{args.strategy}{tag}.json"
    equity_path = OUTPUT_DIR / f"equity_{args.symbol}_{args.strategy}{tag}.csv"
    trades_path = OUTPUT_DIR / f"trades_{args.symbol}_{args.strategy}{tag}.csv"
    signal_path = OUTPUT_DIR / f"signals_{args.symbol}_{args.strategy}{tag}.csv"

    metrics_path.write_text(json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    result.equity_curve.to_csv(equity_path, header=True)
    result.trades.to_csv(trades_path, index=False)
    result.signal_explain.to_csv(signal_path, index=True)

    print(f"Backtest done: {args.symbol} / {strategy.name}")
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    print(f"Saved: {metrics_path}\nSaved: {equity_path}\nSaved: {trades_path}\nSaved: {signal_path}")


def cmd_simulate(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    strategy = get_strategy(args.strategy, **_parse_params(args.params))
    account_id = normalize_account_id(getattr(args, "account_id", DEFAULT_ACCOUNT_ID))
    resolved_state_file = _resolve_account_state_file(account_id, args.state_file)
    broker = create_broker(state_file=resolved_state_file)
    initial_snapshot = broker.snapshot()
    initial_snapshot = broker.snapshot()
    allocation_per_signal = getattr(args, "allocation_per_signal", None)
    min_quantity = float(getattr(args, "min_quantity", 0.0))
    if allocation_per_signal is not None and not 0 < float(allocation_per_signal) <= 1:
        raise ValueError("--allocation-per-signal 必须在 (0,1] 之间")
    if min_quantity < 0:
        raise ValueError("--min-quantity 必须 >= 0")

    data = dm.get_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
    )
    signals = strategy.generate_signals(data)
    explain = strategy.explain(data).reindex(data.index)
    explain["signal"] = explain.get("signal", signals).fillna(0).astype(int)
    if "reason" not in explain.columns:
        explain["reason"] = explain["signal"].map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})

    signal_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    for ts, row in data.iterrows():
        signal = int(explain.loc[ts, "signal"])
        reason = str(explain.loc[ts, "reason"])
        quantity_reason: str | None = None
        current = broker.positions.get(args.symbol)
        current_side = current.side if current else 0
        quantity = float(args.quantity)
        if signal != 0 and signal != current_side:
            if allocation_per_signal is not None:
                snap = broker.snapshot()
                total_equity = float(snap["total_equity"])
                target_notional = max(0.0, total_equity * float(allocation_per_signal))
                price = float(row["close"])
                quantity = (target_notional / price) if price > 0 else 0.0
            if quantity < min_quantity:
                signal = 0
                quantity = 0.0
                quantity_reason = "qty_below_min"
        broker.process_signal(
            symbol=args.symbol,
            signal=signal,
            price=float(row["close"]),
            timestamp=ts.isoformat(),
            quantity=quantity,
        )
        broker.mark_to_market(args.symbol, float(row["close"]))
        snap = broker.snapshot()
        pos = broker.positions.get(args.symbol)
        signal_rows.append(
            {
                "timestamp": ts.isoformat(),
                "price": float(row["close"]),
                "signal": signal,
                "reason": f"{reason}|{quantity_reason}" if quantity_reason else reason,
                "quantity": quantity,
            }
        )
        equity_rows.append(
            {
                "timestamp": ts.isoformat(),
                "price": float(row["close"]),
                "cash": float(snap["cash"]),
                "realized_pnl": float(snap["realized_pnl"]),
                "floating_pnl": float(snap["floating_pnl"]),
                "cumulative_pnl": float(snap["cumulative_pnl"]),
                "total_equity": float(snap["total_equity"]),
                "return_pct": float(snap["return_pct"]),
                "position_side": int(pos.side) if pos is not None else 0,
                "position_quantity": float(pos.quantity) if pos is not None else 0.0,
                "position_entry_price": float(pos.entry_price) if pos is not None else 0.0,
                "position_mark_price": float(pos.mark_price) if pos is not None else 0.0,
                "position_unrealized_pnl": float(pos.unrealized_pnl) if pos is not None else 0.0,
            }
        )

    broker.save_state()

    tag = f"_{args.output_tag}" if getattr(args, "output_tag", None) else ""
    trades_df = pd.DataFrame([t.__dict__ for t in broker.trades])
    trades_path = OUTPUT_DIR / f"sim_trades_{args.symbol}_{args.strategy}{tag}.csv"
    if not trades_df.empty:
        trades_df.to_csv(trades_path, index=False)
        print(f"Saved trade log: {trades_path}")
    signal_path = OUTPUT_DIR / f"sim_signals_{args.symbol}_{args.strategy}{tag}.csv"
    equity_path = OUTPUT_DIR / f"sim_equity_{args.symbol}_{args.strategy}{tag}.csv"
    summary_path = OUTPUT_DIR / (
        getattr(args, "summary_file", None) or f"sim_summary_{args.symbol}_{args.strategy}{tag}.json"
    )
    pd.DataFrame(signal_rows).to_csv(signal_path, index=False)
    pd.DataFrame(equity_rows).to_csv(equity_path, index=False)
    final_snapshot = broker.snapshot()
    summary_payload = {
        "account_id": account_id,
        "symbol": args.symbol,
        "strategy": args.strategy,
        "start": args.start,
        "end": args.end,
        "interval": args.interval,
        "output_tag": getattr(args, "output_tag", None),
        "state_file": resolved_state_file,
        "signal_file": signal_path.name,
        "equity_file": equity_path.name,
        "trades_file": trades_path.name if trades_path.exists() else None,
        "snapshot": final_snapshot,
        "latest_position": final_snapshot.get("positions", {}).get(args.symbol),
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    SQLiteStore(getattr(args, "db_file", None)).upsert_sim_state_meta(
        account_id=account_id,
        state_key=f"simulate:{args.symbol}:{args.strategy}",
        state_path=resolved_state_file,
        meta={
            "symbol": args.symbol,
            "strategy": args.strategy,
            "interval": args.interval,
            "state_file": resolved_state_file,
        },
    )
    print(f"Saved signal log: {signal_path}")
    print(f"Saved equity curve: {equity_path}")
    print(f"Saved simulate summary: {summary_path}")

    print(json.dumps(broker.snapshot(), ensure_ascii=False, indent=2))
    print(f"State persisted: data/state/{resolved_state_file}")


def cmd_simulate_portfolio(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("--symbols 不能为空")
    if not 0 < args.allocation_per_signal <= 1:
        raise ValueError("--allocation-per-signal 必须在 (0,1] 之间")
    if not 0 < args.max_symbol_allocation <= 1:
        raise ValueError("--max-symbol-allocation 必须在 (0,1] 之间")
    if not 0 < args.max_total_allocation:
        raise ValueError("--max-total-allocation 必须 > 0")
    if args.max_symbol_allocation > args.max_total_allocation:
        raise ValueError("--max-symbol-allocation 不能大于 --max-total-allocation")
    if not 0 < args.initial_margin_rate <= 1:
        raise ValueError("--initial-margin-rate 必须在 (0,1] 之间")
    if not 0 <= args.cash_reserve_ratio < 1:
        raise ValueError("--cash-reserve-ratio 必须在 [0,1) 之间")
    if args.max_portfolio_drawdown is not None and not 0 < args.max_portfolio_drawdown < 1:
        raise ValueError("--max-portfolio-drawdown 必须在 (0,1) 之间")
    if args.risk_cooldown_bars < 0:
        raise ValueError("--risk-cooldown-bars 必须 >= 0")

    strategy = get_strategy(args.strategy, **_parse_params(args.params))
    account_id = normalize_account_id(getattr(args, "account_id", DEFAULT_ACCOUNT_ID))
    resolved_state_file = _resolve_account_state_file(account_id, args.state_file)
    broker = create_broker(state_file=resolved_state_file)
    initial_snapshot = broker.snapshot()

    if hasattr(dm, "get_aligned_history"):
        bars = dm.get_aligned_history(
            symbols=symbols,
            start=args.start,
            end=args.end,
            interval=args.interval,
        )
    else:
        bars = {
            symbol: dm.get_history(symbol=symbol, start=args.start, end=args.end, interval=args.interval)
            for symbol in symbols
        }
        common_index: pd.DatetimeIndex | None = None
        for frame in bars.values():
            common_index = frame.index if common_index is None else common_index.intersection(frame.index)
        if common_index is None or len(common_index) == 0:
            raise ValueError("组合标的没有可对齐的共同时间区间")
        bars = {symbol: frame.loc[common_index].copy() for symbol, frame in bars.items()}
    explain_map: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        data = bars[symbol]
        explain = strategy.explain(data).reindex(data.index)
        signals = explain.get("signal", strategy.generate_signals(data)).fillna(0).astype(int).clip(-1, 1)
        explain["signal"] = signals
        if "reason" not in explain.columns:
            explain["reason"] = signals.map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})
        explain_map[symbol] = explain

    common_index = next(iter(bars.values())).index

    signal_rows: list[dict[str, Any]] = []
    capital_rows: list[dict[str, Any]] = []
    peak_equity = float(broker.snapshot()["total_equity"])
    cooldown_left = 0
    for ts in common_index:
        # 先按当根 close 对现有仓位盯市，再处理新的开平仓信号。
        for symbol in symbols:
            price = float(bars[symbol].loc[ts, "close"])
            broker.mark_to_market(symbol, price)

        snap = broker.snapshot()
        total_equity = float(snap["total_equity"])
        peak_equity = max(peak_equity, total_equity)
        drawdown = (total_equity / peak_equity - 1.0) if peak_equity > 0 else 0.0

        if (
            args.max_portfolio_drawdown is not None
            and drawdown <= -args.max_portfolio_drawdown
            and broker.positions
        ):
            for pos_symbol in list(broker.positions.keys()):
                px = float(bars[pos_symbol].loc[ts, "close"])
                broker.process_signal(
                    symbol=pos_symbol,
                    signal=0,
                    price=px,
                    timestamp=ts.isoformat(),
                    quantity=0.0,
                )
                broker.mark_to_market(pos_symbol, px)
                signal_rows.append(
                    {
                        "timestamp": ts.isoformat(),
                        "symbol": pos_symbol,
                        "price": px,
                        "signal": 0,
                        "reason": f"risk_drawdown_flatten(drawdown={drawdown:.4f})",
                        "quantity": 0.0,
                    }
                )
            cooldown_left = args.risk_cooldown_bars

        for symbol in symbols:
            price = float(bars[symbol].loc[ts, "close"])
            signal = int(explain_map[symbol].loc[ts, "signal"])
            reason = str(explain_map[symbol].loc[ts, "reason"])
            quantity = 0.0
            used_margin = 0.0
            available_margin = 0.0
            blocked_reason: str | None = None
            current = broker.positions.get(symbol)
            current_side = current.side if current else 0
            if signal != 0 and cooldown_left > 0 and current_side == 0:
                blocked_reason = f"risk_cooldown_block({cooldown_left})"
                signal = 0

            if signal != 0 and price > 0:
                snap_live = broker.snapshot()
                equity_live = float(snap_live["total_equity"])
                exposure_map: dict[str, float] = {}
                for pos_symbol, pos in broker.positions.items():
                    pos_px = float(bars[pos_symbol].loc[ts, "close"]) if pos_symbol in bars else float(pos.mark_price)
                    exposure_map[pos_symbol] = abs(float(pos.quantity) * pos_px)
                symbol_cap = equity_live * args.max_symbol_allocation
                total_cap = equity_live * args.max_total_allocation
                current_total = sum(exposure_map.values())
                current_symbol = exposure_map.get(symbol, 0.0)
                available_total = max(0.0, total_cap - (current_total - current_symbol))
                reserve_cash = max(0.0, equity_live * args.cash_reserve_ratio)
                used_margin = max(0.0, (current_total - current_symbol) * args.initial_margin_rate)
                available_margin = max(0.0, equity_live - reserve_cash - used_margin)
                margin_cap = available_margin / args.initial_margin_rate if args.initial_margin_rate > 0 else 0.0
                target_notional = min(equity_live * args.allocation_per_signal, symbol_cap, available_total, margin_cap)

                if target_notional <= 0 and current_side == 0:
                    if margin_cap <= 0:
                        blocked_reason = blocked_reason or "risk_margin_block"
                    elif available_total <= 0:
                        blocked_reason = blocked_reason or "risk_notional_block"
                    else:
                        blocked_reason = blocked_reason or "risk_cash_reserve_block"
                    signal = 0
                else:
                    quantity = (target_notional / price) if target_notional > 0 else 0.0

            broker.process_signal(
                symbol=symbol,
                signal=signal,
                price=price,
                timestamp=ts.isoformat(),
                quantity=quantity,
            )
            broker.mark_to_market(symbol, price)
            signal_rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "symbol": symbol,
                    "price": price,
                    "signal": signal,
                    "reason": f"{reason}|{blocked_reason}" if blocked_reason else reason,
                    "quantity": quantity,
                    "margin_used_est": used_margin if signal != 0 else 0.0,
                    "margin_available_est": available_margin if signal != 0 else 0.0,
                }
            )
        if cooldown_left > 0:
            cooldown_left -= 1

        final_snap = broker.snapshot()
        final_equity = float(final_snap["total_equity"])
        exposure_map: dict[str, float] = {}
        for pos_symbol, pos in broker.positions.items():
            pos_px = float(bars[pos_symbol].loc[ts, "close"]) if pos_symbol in bars else float(pos.mark_price)
            exposure_map[pos_symbol] = abs(float(pos.quantity) * pos_px)
        gross_exposure = sum(exposure_map.values())
        reserve_cash = max(0.0, final_equity * args.cash_reserve_ratio)
        used_margin = gross_exposure * args.initial_margin_rate
        available_margin = max(0.0, final_equity - reserve_cash - used_margin)
        capital_rows.append(
            {
                "timestamp": ts.isoformat(),
                "total_equity": final_equity,
                "gross_exposure": gross_exposure,
                "gross_exposure_ratio": (gross_exposure / final_equity) if final_equity > 0 else 0.0,
                "used_margin": used_margin,
                "available_margin": available_margin,
                "reserve_cash": reserve_cash,
                "drawdown": (final_equity / peak_equity - 1.0) if peak_equity > 0 else 0.0,
                "cooldown_left": cooldown_left,
            }
        )

    broker.save_state()

    trades_df = pd.DataFrame([t.__dict__ for t in broker.trades])
    trades_path = OUTPUT_DIR / f"sim_portfolio_trades_{'_'.join(symbols)}_{args.strategy}.csv"
    if not trades_df.empty:
        trades_df.to_csv(trades_path, index=False)
        print(f"Saved trade log: {trades_path}")
    signal_path = OUTPUT_DIR / f"sim_portfolio_signals_{'_'.join(symbols)}_{args.strategy}.csv"
    pd.DataFrame(signal_rows).to_csv(signal_path, index=False)
    capital_path = OUTPUT_DIR / f"sim_portfolio_capital_{'_'.join(symbols)}_{args.strategy}.csv"
    pd.DataFrame(capital_rows).to_csv(capital_path, index=False)
    summary_path = OUTPUT_DIR / (
        getattr(args, "summary_file", None) or f"sim_portfolio_summary_{'_'.join(symbols)}_{args.strategy}.json"
    )
    final_snapshot = broker.snapshot()
    skipped_delta_total, skipped_delta_by_symbol = _compute_counter_delta(initial_snapshot, final_snapshot)
    summary_payload = {
        "account_id": account_id,
        "symbols": symbols,
        "strategy": args.strategy,
        "start": args.start,
        "end": args.end,
        "interval": args.interval,
        "state_file": resolved_state_file,
        "signal_file": signal_path.name,
        "capital_file": capital_path.name,
        "trades_file": trades_path.name if trades_path.exists() else None,
        "skipped_duplicate_bars_run_delta": {
            "total": int(skipped_delta_total),
            "by_symbol": skipped_delta_by_symbol,
        },
        "snapshot_before": initial_snapshot,
        "snapshot_after": final_snapshot,
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved signal log: {signal_path}")
    print(f"Saved capital log: {capital_path}")
    print(f"Saved simulate-portfolio summary: {summary_path}")
    SQLiteStore(getattr(args, "db_file", None)).upsert_sim_state_meta(
        account_id=account_id,
        state_key=f"simulate_portfolio:{'_'.join(symbols)}:{args.strategy}",
        state_path=resolved_state_file,
        meta={
            "symbols": symbols,
            "strategy": args.strategy,
            "interval": args.interval,
            "state_file": resolved_state_file,
        },
    )

    print(json.dumps(final_snapshot, ensure_ascii=False, indent=2))
    print(f"State persisted: data/state/{resolved_state_file}")


def cmd_research(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    data = dm.get_history(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        interval=args.interval,
    )
    engine = BacktestEngine(
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        bars_per_year=args.bars_per_year,
        max_drawdown=args.max_drawdown,
        cooldown_bars=args.cooldown_bars,
    )
    grid = _parse_grid(args.grid)
    grid_report = run_grid_search(
        data=data,
        strategy_name=args.strategy,
        symbol=args.symbol,
        engine=engine,
        param_grid=grid,
        objective=args.objective,
    )
    summary, detail = run_walk_forward(
        data=data,
        strategy_name=args.strategy,
        symbol=args.symbol,
        engine=engine,
        param_grid=grid,
        objective=args.objective,
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
    )

    grid_path = OUTPUT_DIR / f"grid_{args.symbol}_{args.strategy}.csv"
    wf_path = OUTPUT_DIR / f"walk_forward_{args.symbol}_{args.strategy}.csv"
    wf_summary_path = OUTPUT_DIR / f"walk_forward_summary_{args.symbol}_{args.strategy}.json"
    grid_report.to_csv(grid_path, index=False)
    detail.to_csv(wf_path, index=False)
    wf_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Research done: {args.symbol} / {args.strategy}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved: {grid_path}\nSaved: {wf_path}\nSaved: {wf_summary_path}")


def cmd_compare(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    engine = BacktestEngine(
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        bars_per_year=args.bars_per_year,
        max_drawdown=args.max_drawdown,
        cooldown_bars=args.cooldown_bars,
    )
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategies = [s.strip().lower() for s in args.strategies.split(",") if s.strip()]
    report = build_leaderboard(
        data_manager=dm,
        engine=engine,
        symbols=symbols,
        strategies=strategies,
        start=args.start,
        end=args.end,
        interval=args.interval,
    )
    path = OUTPUT_DIR / f"leaderboard_{'_'.join(symbols)}.csv"
    by_symbol_path = OUTPUT_DIR / f"leaderboard_by_symbol_{'_'.join(symbols)}.csv"
    report.to_csv(path, index=False)
    build_symbol_leaderboard(report).to_csv(by_symbol_path, index=False)
    print(f"Compare done: {len(report)} rows")
    print(report.head(10).to_string(index=False))
    print(f"Saved: {path}\nSaved: {by_symbol_path}")


def cmd_portfolio(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    dm = DataManager()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategy_params = _parse_params(args.params)
    metrics, equity, positions, detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=symbols,
        strategy_name=args.strategy,
        strategy_params=strategy_params,
        start=args.start,
        end=args.end,
        interval=args.interval,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
        bars_per_year=args.bars_per_year,
        allocation_mode=args.allocation_mode,
        vol_window=args.vol_window,
        target_vol=args.target_vol,
        max_leverage=args.max_leverage,
        corr_watch_threshold=args.corr_watch_threshold,
        corr_high_threshold=args.corr_high_threshold,
        crowding_watch_threshold=args.crowding_watch_threshold,
        crowding_high_threshold=args.crowding_high_threshold,
        drift_watch_threshold=args.drift_watch_threshold,
        drift_high_threshold=args.drift_high_threshold,
        rebalance_on_drift=args.rebalance_on_drift,
        rebalance_trigger=args.rebalance_trigger,
        rebalance_scale=args.rebalance_scale,
    )
    suffix = "_".join(symbols)
    metrics_path = OUTPUT_DIR / f"portfolio_metrics_{args.strategy}_{suffix}.json"
    equity_path = OUTPUT_DIR / f"portfolio_equity_{args.strategy}_{suffix}.csv"
    pos_path = OUTPUT_DIR / f"portfolio_positions_{args.strategy}_{suffix}.csv"
    contrib_path = OUTPUT_DIR / f"portfolio_contrib_{args.strategy}_{suffix}.csv"
    attribution_path = OUTPUT_DIR / f"portfolio_attribution_{args.strategy}_{suffix}.csv"
    alert_path = OUTPUT_DIR / f"portfolio_alerts_{args.strategy}_{suffix}.csv"
    weights_path = OUTPUT_DIR / f"portfolio_weights_{args.strategy}_{suffix}.csv"
    drift_path = OUTPUT_DIR / f"portfolio_drift_{args.strategy}_{suffix}.csv"
    rebalance_path = OUTPUT_DIR / f"portfolio_rebalance_{args.strategy}_{suffix}.csv"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    equity.to_csv(equity_path, header=True)
    positions.to_csv(pos_path, index=True)
    detail["net_contrib"].to_csv(contrib_path, index=True)
    detail["attribution"].to_csv(attribution_path, index=False)
    detail["alerts"].to_csv(alert_path, index=False)
    detail["weights"].to_csv(weights_path, index=True)
    detail["drift"].to_csv(drift_path, index=True)
    detail["rebalance"].to_csv(rebalance_path, index=True)
    print(f"Portfolio backtest done: symbols={symbols} strategy={args.strategy}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(
        f"Saved: {metrics_path}\nSaved: {equity_path}\nSaved: {pos_path}\nSaved: {contrib_path}\n"
        f"Saved: {attribution_path}\nSaved: {alert_path}\nSaved: {weights_path}\nSaved: {drift_path}\n"
        f"Saved: {rebalance_path}"
    )


def cmd_report(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    if args.champion_switch_recent_runs <= 0:
        raise ValueError("--champion-switch-recent-runs 必须 > 0")
    if args.champion_switch_watch_threshold < 0:
        raise ValueError("--champion-switch-watch-threshold 必须 >= 0")
    if args.champion_switch_high_threshold < args.champion_switch_watch_threshold:
        raise ValueError("--champion-switch-high-threshold 必须 >= --champion-switch-watch-threshold")
    content = build_report_index(
        OUTPUT_DIR,
        champion_switch_watch_threshold=args.champion_switch_watch_threshold,
        champion_switch_high_threshold=args.champion_switch_high_threshold,
        champion_switch_recent_runs=args.champion_switch_recent_runs,
    )
    path = OUTPUT_DIR / args.output_file
    path.write_text(content, encoding="utf-8")
    print(f"Report index generated: {path}")
    csv_file = str(getattr(args, "champion_switch_csv_file", "") or "").strip()
    if csv_file:
        csv_path = export_champion_switch_trend_csv(
            OUTPUT_DIR,
            output_file=csv_file,
            recent_runs=args.champion_switch_recent_runs,
            watch_threshold=args.champion_switch_watch_threshold,
            high_threshold=args.champion_switch_high_threshold,
        )
        if csv_path is not None:
            print(f"Champion switch trend CSV generated: {csv_path}")


def cmd_stability(args: argparse.Namespace) -> None:
    ensure_runtime_dirs()
    detail = pd.read_csv(args.walk_forward_file)
    summary, freq = analyze_walk_forward_stability(detail)

    stem = Path(args.walk_forward_file).stem.replace("walk_forward_", "")
    summary_file = OUTPUT_DIR / (args.summary_file or f"stability_summary_{stem}.json")
    freq_file = OUTPUT_DIR / (args.freq_file or f"stability_freq_{stem}.csv")

    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    freq.to_csv(freq_file, index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved: {summary_file}\nSaved: {freq_file}")


def cmd_run_config(args: argparse.Namespace) -> None:
    tasks = _parse_config_tasks(args.file)
    on_error = _parse_batch_error_mode(args.file)
    summary_json_path, summary_csv_path = _parse_batch_summary_paths(args.file, is_batch=len(tasks) > 1)
    summary_compress = _parse_batch_summary_compress(args.file)
    compress_naming = _parse_compress_naming(args.file)
    if summary_json_path is not None:
        summary_json_path = _apply_compress_suffix(summary_json_path, summary_compress, compress_naming)
    if summary_csv_path is not None:
        summary_csv_path = _apply_compress_suffix(summary_csv_path, summary_compress, compress_naming)
    retry_budget_trace_path = _parse_retry_budget_trace_path(args.file, is_batch=len(tasks) > 1)
    retry_budget_trace_compress = _parse_retry_budget_trace_compress(args.file)
    if retry_budget_trace_path is not None:
        retry_budget_trace_path = _apply_compress_suffix(
            retry_budget_trace_path,
            retry_budget_trace_compress,
            compress_naming,
        )
    retry_count, retry_delay_ms = _parse_batch_retry_policy(args.file)
    retry_enabled, retry_retryable_only = _parse_batch_retry_switches(args.file)
    retry_budget_total = _parse_batch_retry_budget(args.file)
    retry_budget_left = retry_budget_total
    ensure_runtime_dirs()
    run_started_at = datetime.now(timezone.utc)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dispatch = {
        "fetch": cmd_fetch,
        "update-cache": cmd_update_cache,
        "mvp": cmd_mvp,
        "scan-alerts": cmd_scan_alerts,
        "dispatch-alerts": cmd_dispatch_alerts,
        "update-alerts": cmd_update_alerts,
        "report-alerts": cmd_report_alerts,
        "baseline-summary": cmd_baseline_summary,
        "diagnose-data": cmd_diagnose_data,
        "backtest": cmd_backtest,
        "simulate": cmd_simulate,
        "simulate-portfolio": cmd_simulate_portfolio,
        "research": cmd_research,
        "compare": cmd_compare,
        "portfolio": cmd_portfolio,
        "report": cmd_report,
        "stability": cmd_stability,
    }
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    retry_budget_rows: list[dict[str, Any]] = []
    compare_champion_summaries: list[dict[str, Any]] = []
    for idx, (command, cfg_args) in enumerate(tasks, start=1):
        budget_before_task = retry_budget_left
        started_at = datetime.now(timezone.utc)
        attempts = 0
        status = "success"
        error_message = ""
        last_exc: Exception | None = None
        task_retry_count = retry_count
        task_retry_delay_ms = retry_delay_ms
        task_retry_enabled = retry_enabled
        task_retryable_only = retry_retryable_only
        task_retry_override = getattr(cfg_args, "_task_retry_override", None)
        if isinstance(task_retry_override, dict):
            if "enabled" in task_retry_override:
                task_retry_enabled = bool(task_retry_override["enabled"])
            if "count" in task_retry_override:
                task_retry_count = int(task_retry_override["count"])
            if "delay_ms" in task_retry_override:
                task_retry_delay_ms = int(task_retry_override["delay_ms"])
            if "retryable_only" in task_retry_override:
                task_retryable_only = bool(task_retry_override["retryable_only"])
        if not task_retry_enabled:
            task_retry_count = 0

        if len(tasks) > 1:
            print(f"[run-config] ({idx}/{len(tasks)}) 执行 {command}")

        while attempts <= task_retry_count:
            attempts += 1
            try:
                if command not in dispatch:
                    raise ValueError(f"Unsupported command in config: {command}")
                dispatch[command](cfg_args)
                last_exc = None
                break
            except Exception as exc:  # pragma: no cover - exercised in integration flows
                last_exc = exc
                can_retry_more = attempts <= task_retry_count
                retryable = _is_retryable_exception(exc)
                has_retry_budget = (retry_budget_left is None) or (retry_budget_left > 0)
                should_retry = can_retry_more and (retryable or not task_retryable_only) and has_retry_budget
                if should_retry:
                    retry_idx = attempts
                    if retry_budget_left is not None:
                        retry_budget_left -= 1
                    print(
                        f"[run-config] ({idx}/{len(tasks)}) {command} 重试 {retry_idx}/{task_retry_count}，原因: {exc}"
                    )
                    if task_retry_delay_ms > 0:
                        time.sleep(task_retry_delay_ms / 1000.0)
                    continue
                if can_retry_more and not has_retry_budget:
                    print(
                        f"[run-config] ({idx}/{len(tasks)}) {command} 重试预算耗尽，停止重试: {exc}"
                    )
                if can_retry_more and task_retryable_only and not retryable:
                    print(
                        f"[run-config] ({idx}/{len(tasks)}) {command} 命中非可重试错误，停止重试: {exc}"
                    )
                break

        if last_exc is not None:
            status = "failed"
            error_message = str(last_exc)
            symbol_champions: list[dict[str, Any]] = []
            symbol_champion_text = ""
            if command == "compare":
                compare_champion_summaries.append(
                    {
                        "task_index": idx,
                        "command": command,
                        "status": status,
                        "champion_count": 0,
                        "champions": [],
                    }
                )
            msg = f"[run-config] ({idx}/{len(tasks)}) {command} 失败: {last_exc}"
            if on_error == "continue":
                print(msg)
                errors.append(msg)
            else:
                ended_at = datetime.now(timezone.utc)
                duration_ms = (ended_at - started_at).total_seconds() * 1000.0
                results.append(
                    {
                        "run_id": run_id,
                        "index": idx,
                        "task_total": len(tasks),
                        "command": command,
                        "status": status,
                        "error": error_message,
                        "started_at": started_at.isoformat(),
                        "ended_at": ended_at.isoformat(),
                        "duration_ms": round(duration_ms, 3),
                        "attempts": attempts,
                        "retries_used": max(0, attempts - 1),
                        "retry_enabled": task_retry_enabled,
                        "retry_retryable_only": task_retryable_only,
                        "retry_count": task_retry_count,
                        "symbol_group_champion_count": len(symbol_champions),
                        "symbol_group_champions": symbol_champion_text,
                    }
                )
                retry_budget_rows.append(
                    {
                        "run_id": run_id,
                        "index": idx,
                        "command": command,
                        "status": status,
                        "attempts": attempts,
                        "retries_used": max(0, attempts - 1),
                        "budget_before": budget_before_task,
                        "budget_after": retry_budget_left,
                    }
                )
                raise last_exc

        ended_at = datetime.now(timezone.utc)
        duration_ms = (ended_at - started_at).total_seconds() * 1000.0
        symbol_champions = _collect_compare_symbol_champions(cfg_args) if command == "compare" else []
        symbol_champion_text = ",".join(
            f"{row.get('symbol')}:{row.get('strategy')}({float(row.get('composite_score', 0.0)):.4f})"
            for row in symbol_champions
        )
        if command == "compare":
            compare_champion_summaries.append(
                {
                    "task_index": idx,
                    "command": command,
                    "status": status,
                    "champion_count": len(symbol_champions),
                    "champions": symbol_champions,
                }
            )
        results.append(
            {
                "run_id": run_id,
                "index": idx,
                "task_total": len(tasks),
                "command": command,
                "status": status,
                "error": error_message,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "duration_ms": round(duration_ms, 3),
                "attempts": attempts,
                "retries_used": max(0, attempts - 1),
                "retry_enabled": task_retry_enabled,
                "retry_retryable_only": task_retryable_only,
                "retry_count": task_retry_count,
                "symbol_group_champion_count": len(symbol_champions),
                "symbol_group_champions": symbol_champion_text,
            }
        )
        retry_budget_rows.append(
            {
                "run_id": run_id,
                "index": idx,
                "command": command,
                "status": status,
                "attempts": attempts,
                "retries_used": max(0, attempts - 1),
                "budget_before": budget_before_task,
                "budget_after": retry_budget_left,
            }
        )
        if status == "failed" and on_error == "continue":
            continue
    if summary_json_path is not None:
        summary_json_path.parent.mkdir(parents=True, exist_ok=True)
        run_ended_at = datetime.now(timezone.utc)
        summary_payload = {
            "run_id": run_id,
            "config_file": str(Path(args.file).resolve()),
            "task_count": len(tasks),
            "success_count": sum(1 for x in results if x["status"] == "success"),
            "failed_count": sum(1 for x in results if x["status"] == "failed"),
            "on_error": on_error,
            "retry_enabled": retry_enabled,
            "retry_retryable_only": retry_retryable_only,
            "retry_count": retry_count,
            "retry_delay_ms": retry_delay_ms,
            "max_total_retries": retry_budget_total,
            "retry_budget_remaining": retry_budget_left,
            "run_started_at": run_started_at.isoformat(),
            "run_ended_at": run_ended_at.isoformat(),
            "run_duration_ms": round((run_ended_at - run_started_at).total_seconds() * 1000.0, 3),
            "symbol_group_champions": compare_champion_summaries,
            "results": results,
        }
        summary_json_text = json.dumps(summary_payload, ensure_ascii=False, indent=2)
        if summary_compress == "gzip":
            with gzip.open(summary_json_path, "wt", encoding="utf-8") as fp:
                fp.write(summary_json_text)
        else:
            summary_json_path.write_text(summary_json_text, encoding="utf-8")
        print(f"[run-config] 执行摘要(JSON): {summary_json_path}")
    if summary_csv_path is not None:
        summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_csv(summary_csv_path, index=False, compression=("gzip" if summary_compress == "gzip" else None))
        print(f"[run-config] 执行摘要(CSV): {summary_csv_path}")
    if retry_budget_trace_path is not None:
        retry_budget_trace_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(retry_budget_rows).to_csv(
            retry_budget_trace_path,
            index=False,
            compression=("gzip" if retry_budget_trace_compress == "gzip" else None),
        )
        print(f"[run-config] 重试预算轨迹(CSV): {retry_budget_trace_path}")
    if errors:
        raise RuntimeError("批处理执行完成，但存在失败任务：\n" + "\n".join(errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="市场信号系统 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="拉取历史行情")
    fetch.add_argument("--symbol", required=True, choices=["QQQ", "ETH", "ETHUSDT"])
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--interval", default="1d")
    fetch.add_argument("--no-cache", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    update_cache = sub.add_parser("update-cache", help="增量更新本地行情缓存（可批量标的）")
    update_cache.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔标的列表，例如 QQQ,ETH")
    update_cache.add_argument("--start", required=True)
    update_cache.add_argument("--end", required=True)
    update_cache.add_argument("--interval", default="1d")
    update_cache.set_defaults(func=cmd_update_cache)

    mvp = sub.add_parser("mvp", help="一键执行 MVP 验收链路（拉取+回测+模拟）")
    mvp.add_argument("--start", required=True, help="开始日期")
    mvp.add_argument("--end", required=True, help="结束日期")
    mvp.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔标的，默认 QQQ,ETH")
    mvp.add_argument(
        "--strategies",
        default="ma_cross,donchian,momentum",
        help="逗号分隔策略名，至少 3 个，默认 ma_cross,donchian,momentum",
    )
    mvp.add_argument(
        "--simulate-strategy",
        default="momentum",
        choices=STRATEGY_CHOICES,
        help="模拟交易使用的策略",
    )
    mvp.add_argument("--simulate-params", help="模拟交易策略参数 JSON")
    mvp.add_argument("--interval", default="1d")
    mvp.add_argument("--fee-rate", type=float, default=0.0008)
    mvp.add_argument("--slippage-bps", type=float, default=5.0)
    mvp.add_argument("--bars-per-year", type=int, default=252)
    mvp.add_argument("--max-drawdown", type=float, help="最大回撤阈值（0~1），触发后强制空仓")
    mvp.add_argument("--cooldown-bars", type=int, default=20, help="回撤触发后空仓冷却 bar 数")
    mvp.add_argument("--quantity", type=float, default=1.0, help="模拟交易固定下单数量")
    mvp.add_argument("--state-prefix", help="模拟状态文件前缀（默认 mvp_<run_tag>）")
    mvp.add_argument("--run-tag", help="输出工件标签（默认 UTC 时间戳）")
    mvp.add_argument("--output-file", help="MVP 摘要输出文件名（默认 mvp_summary_<run_tag>.json）")
    mvp.add_argument(
        "--strict-acceptance",
        action="store_true",
        help="若 MVP 验收检查未通过则返回非零退出码（默认仅写入摘要不失败）",
    )
    mvp.set_defaults(func=cmd_mvp)

    scan_alerts_parser = sub.add_parser("scan-alerts", help="扫描新信号并写入 alert ledger（Signal Pilot）")
    scan_alerts_parser.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔标的列表，例如 QQQ,ETH")
    scan_alerts_parser.add_argument(
        "--strategy",
        default="score_regime",
        choices=STRATEGY_CHOICES,
    )
    scan_alerts_parser.add_argument("--params", help="策略参数 JSON")
    scan_alerts_parser.add_argument("--interval", default="1d")
    scan_alerts_parser.add_argument("--lookback-days", type=int, default=365, help="回看天数（用于计算最新信号）")
    scan_alerts_parser.add_argument("--end", help="扫描结束时间（默认当前 UTC 时间）")
    scan_alerts_parser.add_argument("--ledger-file", help="alert ledger 文件路径（默认 data/state/signal_alert_ledger.csv）")
    scan_alerts_parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    scan_alerts_parser.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    scan_alerts_parser.add_argument(
        "--notification-file",
        help="待通知事件文件（JSONL，默认 outputs/signal_pilot_notifications.jsonl）",
    )
    scan_alerts_parser.set_defaults(func=cmd_scan_alerts)

    dispatch_alerts_parser = sub.add_parser("dispatch-alerts", help="派发 Signal Pilot 待通知队列并回写台账")
    dispatch_alerts_parser.add_argument(
        "--queue-file",
        default="signal_pilot_notifications.jsonl",
        help="待通知队列文件（JSONL，相对 outputs）",
    )
    dispatch_alerts_parser.add_argument("--ledger-file", help="alert ledger 文件路径（默认 data/state/signal_alert_ledger.csv）")
    dispatch_alerts_parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    dispatch_alerts_parser.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    dispatch_alerts_parser.add_argument("--webhook-url", help="可选，Webhook URL；未设置时仅写入本地派发文件")
    dispatch_alerts_parser.add_argument(
        "--sink-file",
        default="signal_pilot_notifications_dispatched.jsonl",
        help="本地派发落盘文件（相对 outputs，仅在未设置 webhook 时使用）",
    )
    dispatch_alerts_parser.add_argument("--max-events", type=int, default=200, help="单次最多处理事件数")
    dispatch_alerts_parser.add_argument("--timeout-sec", type=float, default=10.0, help="Webhook 请求超时秒数")
    dispatch_alerts_parser.add_argument("--retry-count", type=int, default=0, help="Webhook 失败重试次数（仅重试可重试错误）")
    dispatch_alerts_parser.add_argument("--retry-delay-ms", type=int, default=500, help="Webhook 重试间隔毫秒")
    dispatch_alerts_parser.add_argument(
        "--idempotency-window-minutes",
        type=float,
        default=0.0,
        help="幂等窗口分钟数（>0 时，窗口内已尝试的 alert_id 跳过）",
    )
    dispatch_alerts_parser.add_argument("--dry-run", action="store_true", help="仅演练，不发送也不写本地 sink")
    dispatch_alerts_parser.set_defaults(func=cmd_dispatch_alerts)

    update_alerts_parser = sub.add_parser("update-alerts", help="刷新 open alert 的观察收益并更新状态（Signal Pilot）")
    update_alerts_parser.add_argument("--ledger-file", help="alert ledger 文件路径（默认 data/state/signal_alert_ledger.csv）")
    update_alerts_parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    update_alerts_parser.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    update_alerts_parser.add_argument("--end", help="观察更新截止时间（默认当前 UTC 时间）")
    update_alerts_parser.add_argument("--max-holding-days", type=int, default=60, help="最大观察天数，超过后标记 expired")
    update_alerts_parser.add_argument(
        "--close-on-reverse",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在反向信号出现时自动平仓（默认开启）",
    )
    update_alerts_parser.add_argument("--symbols", help="可选，逗号分隔标的过滤")
    update_alerts_parser.add_argument("--strategies", help="可选，逗号分隔策略过滤")
    update_alerts_parser.set_defaults(func=cmd_update_alerts)

    report_alerts_parser = sub.add_parser("report-alerts", help="输出 Signal Pilot 观察期报告（7/30/60 天）")
    report_alerts_parser.add_argument("--ledger-file", help="alert ledger 文件路径（默认 data/state/signal_alert_ledger.csv）")
    report_alerts_parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    report_alerts_parser.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    report_alerts_parser.add_argument("--as-of", help="报告统计时点（默认当前 UTC 时间）")
    report_alerts_parser.add_argument("--windows", default="7,30,60", help="观察窗口，逗号分隔，例如 7,30,60")
    report_alerts_parser.add_argument("--output-prefix", default="signal_pilot_alert_report", help="输出文件名前缀")
    report_alerts_parser.set_defaults(func=cmd_report_alerts)

    baseline_summary = sub.add_parser("baseline-summary", help="生成 baseline daily 去重摘要（MVP+Signal+Report）")
    baseline_summary.add_argument("--as-of", help="摘要时点（默认当前 UTC 时间）")
    baseline_summary.add_argument("--output-json", default="baseline_daily_digest.json", help="摘要 JSON 文件名")
    baseline_summary.add_argument("--output-csv", default="baseline_daily_digest.csv", help="摘要 CSV 文件名")
    baseline_summary.add_argument("--mvp-summary-file", help="指定 mvp_summary JSON 文件名（相对 outputs）")
    baseline_summary.add_argument(
        "--signal-report-json-file",
        help="指定 signal_pilot report JSON 文件名（相对 outputs）",
    )
    baseline_summary.add_argument(
        "--report-index-file",
        default="baseline_daily_report_index.md",
        help="指定 report 索引文件名（相对 outputs）",
    )
    baseline_summary.add_argument("--alert-ledger-file", help="指定 alert ledger CSV（默认 data/state/signal_alert_ledger.csv）")
    baseline_summary.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    baseline_summary.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    baseline_summary.add_argument(
        "--dispatch-window-days",
        type=int,
        default=30,
        help="派发健康度聚合窗口（天，仅统计该时间窗内 dispatch 记录）",
    )
    baseline_summary.add_argument("--signal-alert-window-days", type=int, default=30, help="Signal 告警窗口（天）")
    baseline_summary.add_argument("--signal-min-count", type=int, default=3, help="Signal 最少信号数阈值")
    baseline_summary.add_argument("--signal-min-win-rate", type=float, default=0.5, help="Signal 最小胜率阈值（0~1）")
    baseline_summary.add_argument("--signal-min-avg-return-pct", type=float, default=0.0, help="Signal 最小平均收益阈值")
    baseline_summary.add_argument(
        "--simulation-min-return-pct",
        type=float,
        default=-0.05,
        help="模拟累计收益最小阈值（低于阈值触发高优先级告警）",
    )
    baseline_summary.add_argument(
        "--dispatch-max-failed-count",
        type=int,
        default=3,
        help="通知失败累计阈值（高于阈值触发 watch）",
    )
    baseline_summary.add_argument(
        "--dispatch-max-failed-ratio",
        type=float,
        default=0.5,
        help="通知失败占比阈值（高于阈值触发 high，范围 [0,1]）",
    )
    baseline_summary.add_argument(
        "--emit-alert-queue",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否导出 baseline 告警队列（JSONL）",
    )
    baseline_summary.add_argument("--alert-queue-file", default="baseline_summary_alerts.jsonl", help="告警队列文件名（相对 outputs）")
    baseline_summary.set_defaults(func=cmd_baseline_summary)

    diagnose = sub.add_parser("diagnose-data", help="诊断行情数据质量并导出报告")
    diagnose.add_argument("--symbol", required=True, choices=["QQQ", "ETH", "ETHUSDT"])
    diagnose.add_argument("--start", required=True)
    diagnose.add_argument("--end", required=True)
    diagnose.add_argument("--interval", default="1d")
    diagnose.add_argument("--no-cache", action="store_true")
    diagnose.add_argument("--output-file", help="报告输出文件名（默认 data_quality_<symbol>_<interval>.json）")
    diagnose.set_defaults(func=cmd_diagnose_data)

    backtest = sub.add_parser("backtest", help="执行策略回测")
    backtest.add_argument("--symbol", required=True, choices=["QQQ", "ETH", "ETHUSDT"])
    backtest.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGY_CHOICES,
    )
    backtest.add_argument("--params", help="策略参数 JSON，例如 '{\"fast_window\":40,\"slow_window\":180}'")
    backtest.add_argument("--start", required=True)
    backtest.add_argument("--end", required=True)
    backtest.add_argument("--interval", default="1d")
    backtest.add_argument("--fee-rate", type=float, default=0.0008)
    backtest.add_argument("--slippage-bps", type=float, default=5.0)
    backtest.add_argument("--bars-per-year", type=int, default=252)
    backtest.add_argument("--max-drawdown", type=float, help="最大回撤阈值（0~1），触发后强制空仓")
    backtest.add_argument("--cooldown-bars", type=int, default=20, help="回撤触发后空仓冷却 bar 数")
    backtest.add_argument("--output-tag", help="回测输出文件标签（用于区分同策略多参数批量运行）")
    backtest.set_defaults(func=cmd_backtest)

    simulate = sub.add_parser("simulate", help="执行历史驱动模拟交易")
    simulate.add_argument("--symbol", required=True, choices=["QQQ", "ETH", "ETHUSDT"])
    simulate.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGY_CHOICES,
    )
    simulate.add_argument("--params", help="策略参数 JSON")
    simulate.add_argument("--start", required=True)
    simulate.add_argument("--end", required=True)
    simulate.add_argument("--interval", default="1d")
    simulate.add_argument("--state-file", default="paper_broker.json")
    simulate.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    simulate.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    simulate.add_argument("--quantity", type=float, default=1.0)
    simulate.add_argument(
        "--allocation-per-signal",
        type=float,
        help="按总权益比例自动计算开仓数量（0,1]；设置后优先于 --quantity）",
    )
    simulate.add_argument("--min-quantity", type=float, default=0.0, help="最小开仓数量，小于则阻断该次开仓")
    simulate.add_argument("--output-tag", help="模拟输出文件标签（用于区分同策略多参数批量运行）")
    simulate.add_argument("--summary-file", help="模拟结果摘要输出文件名（默认 sim_summary_<symbol>_<strategy>.json）")
    simulate.set_defaults(func=cmd_simulate)

    simulate_portfolio = sub.add_parser("simulate-portfolio", help="多标的共享账户模拟交易")
    simulate_portfolio.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔，例如 QQQ,ETH")
    simulate_portfolio.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGY_CHOICES,
    )
    simulate_portfolio.add_argument("--params", help="策略参数 JSON")
    simulate_portfolio.add_argument("--start", required=True)
    simulate_portfolio.add_argument("--end", required=True)
    simulate_portfolio.add_argument("--interval", default="1d")
    simulate_portfolio.add_argument("--state-file", default="paper_portfolio.json")
    simulate_portfolio.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="账号/命名空间 ID（默认 default）")
    simulate_portfolio.add_argument("--db-file", help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    simulate_portfolio.add_argument(
        "--allocation-per-signal",
        type=float,
        default=0.3,
        help="每个持仓信号使用当前总权益的资金占比",
    )
    simulate_portfolio.add_argument("--max-symbol-allocation", type=float, default=0.4, help="单标的最大仓位占比")
    simulate_portfolio.add_argument("--max-total-allocation", type=float, default=1.0, help="组合总仓位占比上限")
    simulate_portfolio.add_argument(
        "--initial-margin-rate",
        type=float,
        default=1.0,
        help="初始保证金率（1.0 表示 1x，无杠杆）",
    )
    simulate_portfolio.add_argument(
        "--cash-reserve-ratio",
        type=float,
        default=0.05,
        help="现金保留比例（避免满仓占用全部权益）",
    )
    simulate_portfolio.add_argument("--max-portfolio-drawdown", type=float, help="组合最大回撤阈值（0~1）")
    simulate_portfolio.add_argument("--risk-cooldown-bars", type=int, default=20, help="回撤触发后禁止新开仓 bar 数")
    simulate_portfolio.add_argument(
        "--summary-file",
        help="组合模拟结果摘要输出文件名（默认 sim_portfolio_summary_<symbols>_<strategy>.json）",
    )
    simulate_portfolio.set_defaults(func=cmd_simulate_portfolio)

    research = sub.add_parser("research", help="参数搜索 + Walk-Forward 稳健性评估")
    research.add_argument("--symbol", required=True, choices=["QQQ", "ETH", "ETHUSDT"])
    research.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGY_CHOICES,
    )
    research.add_argument("--start", required=True)
    research.add_argument("--end", required=True)
    research.add_argument("--interval", default="1d")
    research.add_argument("--objective", default="sharpe")
    research.add_argument("--grid", help="参数网格 JSON，例如 '{\"lookback\":[40,55],\"exit_lookback\":[15,20]}'")
    research.add_argument("--train-bars", type=int, default=504)
    research.add_argument("--test-bars", type=int, default=126)
    research.add_argument("--step-bars", type=int)
    research.add_argument("--fee-rate", type=float, default=0.0008)
    research.add_argument("--slippage-bps", type=float, default=5.0)
    research.add_argument("--bars-per-year", type=int, default=252)
    research.add_argument("--max-drawdown", type=float, help="最大回撤阈值（0~1），触发后强制空仓")
    research.add_argument("--cooldown-bars", type=int, default=20, help="回撤触发后空仓冷却 bar 数")
    research.set_defaults(func=cmd_research)

    compare = sub.add_parser("compare", help="批量回测并输出策略排行榜")
    compare.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔，例如 QQQ,ETH")
    compare.add_argument(
        "--strategies",
        default=COMPARE_DEFAULT_STRATEGIES,
        help="逗号分隔策略名",
    )
    compare.add_argument("--start", required=True)
    compare.add_argument("--end", required=True)
    compare.add_argument("--interval", default="1d")
    compare.add_argument("--fee-rate", type=float, default=0.0008)
    compare.add_argument("--slippage-bps", type=float, default=5.0)
    compare.add_argument("--bars-per-year", type=int, default=252)
    compare.add_argument("--max-drawdown", type=float, help="最大回撤阈值（0~1），触发后强制空仓")
    compare.add_argument("--cooldown-bars", type=int, default=20, help="回撤触发后空仓冷却 bar 数")
    compare.set_defaults(func=cmd_compare)

    portfolio = sub.add_parser("portfolio", help="多标的组合回测（等权/风险平价/波动率目标）")
    portfolio.add_argument("--symbols", default="QQQ,ETH", help="逗号分隔，例如 QQQ,ETH")
    portfolio.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGY_CHOICES,
    )
    portfolio.add_argument("--params", help="策略参数 JSON")
    portfolio.add_argument("--start", required=True)
    portfolio.add_argument("--end", required=True)
    portfolio.add_argument("--interval", default="1d")
    portfolio.add_argument("--fee-rate", type=float, default=0.0008)
    portfolio.add_argument("--slippage-bps", type=float, default=5.0)
    portfolio.add_argument("--bars-per-year", type=int, default=252)
    portfolio.add_argument(
        "--allocation-mode",
        default="equal",
        choices=["equal", "risk_parity", "vol_target", "cov_risk_parity", "cov_vol_target"],
        help="组合分配模式",
    )
    portfolio.add_argument("--vol-window", type=int, default=20, help="滚动波动率窗口（风险平价/波动率目标）")
    portfolio.add_argument("--target-vol", type=float, default=0.15, help="目标年化波动率（vol_target）")
    portfolio.add_argument("--max-leverage", type=float, default=1.5, help="vol_target 模式杠杆上限")
    portfolio.add_argument("--corr-watch-threshold", type=float, default=0.75, help="相关性 watch 告警阈值")
    portfolio.add_argument("--corr-high-threshold", type=float, default=0.85, help="相关性 high 告警阈值")
    portfolio.add_argument("--crowding-watch-threshold", type=float, default=0.15, help="拥挤度 watch 告警阈值")
    portfolio.add_argument("--crowding-high-threshold", type=float, default=0.2, help="拥挤度 high 告警阈值")
    portfolio.add_argument("--drift-watch-threshold", type=float, default=0.08, help="权重偏移 watch 告警阈值")
    portfolio.add_argument("--drift-high-threshold", type=float, default=0.15, help="权重偏移 high 告警阈值")
    portfolio.add_argument("--rebalance-on-drift", action="store_true", help="启用漂移告警触发的额外再平衡成本注入")
    portfolio.add_argument(
        "--rebalance-trigger",
        default="high",
        choices=["high", "watch"],
        help="触发再平衡动作的最小告警级别",
    )
    portfolio.add_argument("--rebalance-scale", type=float, default=1.0, help="再平衡换手缩放因子")
    portfolio.set_defaults(func=cmd_portfolio)

    report = sub.add_parser("report", help="汇总 outputs 目录中的实验结果")
    report.add_argument("--output-file", default="report_index.md")
    report.add_argument(
        "--champion-switch-csv-file",
        default="champion_switch_last_runs.csv",
        help="冠军切换趋势 CSV 文件名（为空字符串则不导出）",
    )
    report.add_argument(
        "--champion-switch-recent-runs",
        type=int,
        default=10,
        help="冠军切换趋势统计最近 N 次 run（默认 10）",
    )
    report.add_argument(
        "--champion-switch-watch-threshold",
        type=int,
        default=1,
        help="冠军切换 watch 告警阈值（switches 次数）",
    )
    report.add_argument(
        "--champion-switch-high-threshold",
        type=int,
        default=2,
        help="冠军切换 high 告警阈值（switches 次数）",
    )
    report.set_defaults(func=cmd_report)

    stability = sub.add_parser("stability", help="分析 walk-forward 参数稳定性")
    stability.add_argument("--walk-forward-file", required=True, help="walk_forward_*.csv 路径")
    stability.add_argument("--summary-file", help="输出摘要 JSON 文件名（默认自动命名）")
    stability.add_argument("--freq-file", help="输出参数频次 CSV 文件名（默认自动命名）")
    stability.set_defaults(func=cmd_stability)

    run_config = sub.add_parser("run-config", help="从 JSON/YAML 配置文件运行任务")
    run_config.add_argument("--file", required=True, help="配置文件路径（.json/.yaml/.yml）")
    run_config.set_defaults(func=cmd_run_config)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
