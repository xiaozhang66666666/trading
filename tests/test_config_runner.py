import json
import gzip
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

from market_signal_system.cli import (
    _parse_compress_naming,
    _parse_batch_error_mode,
    _parse_batch_retry_budget,
    _parse_batch_retry_policy,
    _parse_retry_budget_trace_compress,
    _parse_retry_budget_trace_path,
    _parse_batch_retry_switches,
    _parse_batch_summary_compress,
    _parse_batch_summary_paths,
    _parse_config_task,
    _parse_config_tasks,
    cmd_run_config,
)
from market_signal_system.utils.paths import OUTPUT_DIR


def test_parse_config_task_with_list_and_dict_values(tmp_path):
    config = {
        "command": "compare",
        "args": {
            "symbols": ["QQQ", "ETH"],
            "strategies": ["ma_cross", "donchian"],
            "start": "2020-01-01",
            "end": "2020-12-31",
        },
    }
    path = tmp_path / "compare.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "compare"
    assert args.symbols == "QQQ,ETH"
    assert args.strategies == "ma_cross,donchian"
    assert args.interval == "1d"


def test_parse_config_task_supports_yaml_file(tmp_path):
    path = tmp_path / "compare.yaml"
    path.write_text(
        "\n".join(
            [
                "command: compare",
                "args:",
                "  symbols:",
                "    - QQQ",
                "    - ETH",
                "  strategies:",
                "    - ma_cross",
                "    - donchian",
                "  start: '2020-01-01'",
                "  end: '2020-12-31'",
            ]
        ),
        encoding="utf-8",
    )

    command, args = _parse_config_task(str(path))
    assert command == "compare"
    assert args.symbols == "QQQ,ETH"
    assert args.strategies == "ma_cross,donchian"
    assert args.interval == "1d"


def test_parse_config_task_rejects_non_object_yaml(tmp_path):
    path = tmp_path / "invalid.yml"
    path.write_text("- command: compare\n- command: report\n", encoding="utf-8")

    with pytest.raises(ValueError, match="配置文件必须是 JSON 对象"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_unknown_field(tmp_path):
    config = {
        "command": "backtest",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "unexpected_flag": True,
    }
    path = tmp_path / "bad_field.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="不支持字段"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_missing_required_field(tmp_path):
    config = {
        "command": "backtest",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-12-31",
    }
    path = tmp_path / "missing_required.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="缺少必填字段"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_invalid_value_type(tmp_path):
    config = {
        "command": "update-alerts",
        "close_on_reverse": "yes",
    }
    path = tmp_path / "invalid_type.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须是布尔值"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_invalid_choice(tmp_path):
    config = {
        "command": "mvp",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "simulate_strategy": "not_exists",
    }
    path = tmp_path / "invalid_choice.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="不在允许取值中"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_negative_fee_rate(tmp_path):
    config = {
        "command": "backtest",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "fee_rate": -0.001,
    }
    path = tmp_path / "invalid_fee_rate.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须 >= 0"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_invalid_allocation_per_signal(tmp_path):
    config = {
        "command": "simulate",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "allocation_per_signal": 1.2,
    }
    path = tmp_path / "invalid_allocation.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须在 \\(0, 1\\] 区间内"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_non_positive_recent_runs(tmp_path):
    config = {
        "command": "report",
        "champion_switch_recent_runs": 0,
    }
    path = tmp_path / "invalid_recent_runs.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须 > 0"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_negative_dispatch_retry_count(tmp_path):
    config = {
        "command": "dispatch-alerts",
        "retry_count": -1,
    }
    path = tmp_path / "invalid_dispatch_retry.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须 >= 0"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_invalid_signal_min_win_rate(tmp_path):
    config = {
        "command": "baseline-summary",
        "signal_min_win_rate": 1.2,
    }
    path = tmp_path / "invalid_baseline_signal_win_rate.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须在 \\[0, 1\\] 区间内"):
        _parse_config_task(str(path))


def test_parse_config_task_rejects_invalid_dispatch_failed_ratio(tmp_path):
    config = {
        "command": "baseline-summary",
        "dispatch_max_failed_ratio": 1.5,
    }
    path = tmp_path / "invalid_dispatch_failed_ratio.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="必须在 \\[0, 1\\] 区间内"):
        _parse_config_task(str(path))


def test_parse_config_task_normalizes_params_dict(tmp_path):
    config = {
        "command": "backtest",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2021-01-01",
        "params": {"fast_window": 40, "slow_window": 180},
    }
    path = tmp_path / "backtest.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "backtest"
    assert isinstance(args.params, str)
    assert '"fast_window": 40' in args.params


def test_parse_config_task_normalizes_mvp_simulate_params_dict(tmp_path):
    config = {
        "command": "mvp",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "simulate_strategy": "momentum",
        "simulate_params": {"lookback": 63, "vol_window": 20},
    }
    path = tmp_path / "mvp_simulate_params.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "mvp"
    assert isinstance(args.simulate_params, str)
    assert '"lookback": 63' in args.simulate_params


def test_parse_config_task_backtest_accepts_output_tag(tmp_path):
    config = {
        "command": "backtest",
        "symbol": "QQQ",
        "strategy": "macd_regime",
        "start": "2020-01-01",
        "end": "2021-01-01",
        "output_tag": "macd_base",
    }
    path = tmp_path / "backtest.output_tag.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "backtest"
    assert args.output_tag == "macd_base"


def test_parse_config_task_portfolio_defaults(tmp_path):
    config = {
        "command": "portfolio",
        "symbols": ["QQQ", "ETH"],
        "strategy": "momentum",
        "start": "2020-01-01",
        "end": "2021-01-01",
    }
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "portfolio"
    assert args.symbols == "QQQ,ETH"
    assert args.interval == "1d"
    assert args.strategy == "momentum"
    assert args.allocation_mode == "equal"
    assert args.vol_window == 20
    assert args.drift_watch_threshold == 0.08
    assert args.drift_high_threshold == 0.15
    assert args.rebalance_on_drift is False
    assert args.rebalance_trigger == "high"
    assert args.rebalance_scale == 1.0


def test_parse_config_task_report_defaults(tmp_path):
    config = {"command": "report"}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "report"
    assert args.output_file == "report_index.md"
    assert args.champion_switch_csv_file == "champion_switch_last_runs.csv"
    assert args.champion_switch_recent_runs == 10
    assert args.champion_switch_watch_threshold == 1
    assert args.champion_switch_high_threshold == 2


def test_parse_config_task_baseline_summary_defaults(tmp_path):
    config = {"command": "baseline-summary"}
    path = tmp_path / "baseline_summary.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "baseline-summary"
    assert args.output_json == "baseline_daily_digest.json"
    assert args.output_csv == "baseline_daily_digest.csv"
    assert args.mvp_summary_file is None
    assert args.signal_report_json_file is None
    assert args.report_index_file == "baseline_daily_report_index.md"
    assert args.alert_ledger_file is None
    assert args.account_id == "default"
    assert args.db_file is None
    assert args.dispatch_window_days == 30
    assert args.dispatch_max_failed_count == 3
    assert args.dispatch_max_failed_ratio == 0.5
    assert args.alert_ledger_file is None
    assert args.dispatch_max_failed_count == 3
    assert args.dispatch_max_failed_ratio == 0.5
    assert args.signal_alert_window_days == 30
    assert args.signal_min_count == 3
    assert args.signal_min_win_rate == 0.5
    assert args.signal_min_avg_return_pct == 0.0
    assert args.simulation_min_return_pct == -0.05
    assert args.emit_alert_queue is False
    assert args.alert_queue_file == "baseline_summary_alerts.jsonl"


def test_parse_config_task_diagnose_data_defaults(tmp_path):
    config = {
        "command": "diagnose-data",
        "symbol": "QQQ",
        "start": "2020-01-01",
        "end": "2021-01-01",
    }
    path = tmp_path / "diagnose.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "diagnose-data"
    assert args.symbol == "QQQ"
    assert args.interval == "1d"
    assert args.no_cache is False
    assert args.output_file is None


def test_parse_config_task_supports_signal_pilot_commands(tmp_path):
    scan_config = {
        "command": "scan-alerts",
        "symbols": "QQQ,ETH",
        "strategy": "score_regime",
    }
    scan_path = tmp_path / "scan_alerts.json"
    scan_path.write_text(json.dumps(scan_config, ensure_ascii=False), encoding="utf-8")

    scan_command, scan_args = _parse_config_task(str(scan_path))
    assert scan_command == "scan-alerts"
    assert scan_args.lookback_days == 365
    assert scan_args.interval == "1d"

    dispatch_config = {
        "command": "dispatch-alerts",
    }
    dispatch_path = tmp_path / "dispatch_alerts.json"
    dispatch_path.write_text(json.dumps(dispatch_config, ensure_ascii=False), encoding="utf-8")
    dispatch_command, dispatch_args = _parse_config_task(str(dispatch_path))
    assert dispatch_command == "dispatch-alerts"
    assert dispatch_args.queue_file == "signal_pilot_notifications.jsonl"
    assert dispatch_args.max_events == 200
    assert dispatch_args.timeout_sec == 10.0
    assert dispatch_args.retry_count == 0
    assert dispatch_args.retry_delay_ms == 500
    assert dispatch_args.idempotency_window_minutes == 0.0
    assert dispatch_args.dry_run is False

    report_config = {
        "command": "report-alerts",
    }
    report_path = tmp_path / "report_alerts.json"
    report_path.write_text(json.dumps(report_config, ensure_ascii=False), encoding="utf-8")

    report_command, report_args = _parse_config_task(str(report_path))
    assert report_command == "report-alerts"
    assert report_args.windows == "7,30,60"
    assert report_args.output_prefix == "signal_pilot_alert_report"


def test_parse_config_task_simulate_portfolio_defaults(tmp_path):
    config = {
        "command": "simulate-portfolio",
        "symbols": ["QQQ", "ETH"],
        "strategy": "momentum",
        "start": "2020-01-01",
        "end": "2021-01-01",
    }
    path = tmp_path / "sim_portfolio.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "simulate-portfolio"
    assert args.symbols == "QQQ,ETH"
    assert args.state_file == "paper_portfolio.json"
    assert args.allocation_per_signal == 0.3
    assert args.max_symbol_allocation == 0.4
    assert args.max_total_allocation == 1.0
    assert args.initial_margin_rate == 1.0
    assert args.cash_reserve_ratio == 0.05
    assert args.max_portfolio_drawdown is None
    assert args.risk_cooldown_bars == 20


def test_parse_config_task_simulate_defaults(tmp_path):
    config = {
        "command": "simulate",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-02-01",
    }
    path = tmp_path / "simulate.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "simulate"
    assert args.state_file == "paper_broker.json"
    assert args.quantity == 1.0
    assert args.allocation_per_signal is None
    assert args.min_quantity == 0.0
    assert args.output_tag is None
    assert args.summary_file is None


def test_parse_config_task_simulate_accepts_output_tag(tmp_path):
    config = {
        "command": "simulate",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2020-02-01",
        "output_tag": "sim_case_a",
    }
    path = tmp_path / "simulate.output_tag.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "simulate"
    assert args.output_tag == "sim_case_a"


def test_parse_config_task_mvp_defaults(tmp_path):
    config = {
        "command": "mvp",
        "start": "2020-01-01",
        "end": "2020-12-31",
    }
    path = tmp_path / "mvp.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "mvp"
    assert args.symbols == "QQQ,ETH"
    assert args.strategies == "ma_cross,donchian,momentum"
    assert args.simulate_strategy == "momentum"
    assert args.interval == "1d"
    assert args.quantity == 1.0
    assert args.output_file is None
    assert args.strict_acceptance is False


def test_parse_config_task_update_cache_defaults(tmp_path):
    config = {
        "command": "update-cache",
        "start": "2020-01-01",
        "end": "2020-12-31",
    }
    path = tmp_path / "update_cache.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "update-cache"
    assert args.symbols == "QQQ,ETH"
    assert args.interval == "1d"


def test_parse_config_task_stability_defaults(tmp_path):
    config = {
        "command": "stability",
        "walk_forward_file": "outputs/walk_forward_QQQ_donchian.csv",
    }
    path = tmp_path / "stability.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    command, args = _parse_config_task(str(path))
    assert command == "stability"
    assert args.walk_forward_file == "outputs/walk_forward_QQQ_donchian.csv"
    assert args.summary_file is None
    assert args.freq_file is None


def test_parse_config_tasks_supports_batch_file_refs(tmp_path):
    backtest = {
        "command": "backtest",
        "symbol": "QQQ",
        "strategy": "ma_cross",
        "start": "2020-01-01",
        "end": "2021-01-01",
    }
    compare = {
        "command": "compare",
        "symbols": ["QQQ", "ETH"],
        "strategies": ["ma_cross", "momentum"],
        "start": "2020-01-01",
        "end": "2021-01-01",
    }
    (tmp_path / "cfg.backtest.json").write_text(json.dumps(backtest, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "cfg.compare.json").write_text(json.dumps(compare, ensure_ascii=False), encoding="utf-8")
    batch = {
        "command": "batch",
        "tasks": ["cfg.backtest.json", {"file": "cfg.compare.json"}],
    }
    batch_path = tmp_path / "cfg.batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    tasks = _parse_config_tasks(str(batch_path))
    assert len(tasks) == 2
    assert tasks[0][0] == "backtest"
    assert tasks[1][0] == "compare"


def test_parse_config_tasks_supports_yaml_batch_file(tmp_path):
    (tmp_path / "task.report.json").write_text(json.dumps({"command": "report"}, ensure_ascii=False), encoding="utf-8")
    batch_path = tmp_path / "batch.yml"
    batch_path.write_text("command: batch\ntasks:\n  - task.report.json\n", encoding="utf-8")

    tasks = _parse_config_tasks(str(batch_path))
    assert len(tasks) == 1
    assert tasks[0][0] == "report"


def test_parse_config_tasks_supports_inline_batch_items(tmp_path):
    batch = {
        "tasks": [
            {
                "command": "fetch",
                "symbol": "QQQ",
                "start": "2024-01-01",
                "end": "2024-02-01",
            },
            {
                "command": "report",
                "output_file": "daily_report.md",
            },
        ]
    }
    path = tmp_path / "cfg.inline_batch.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    tasks = _parse_config_tasks(str(path))
    assert len(tasks) == 2
    assert tasks[0][0] == "fetch"
    assert tasks[1][0] == "report"
    assert tasks[1][1].output_file == "daily_report.md"


def test_parse_config_tasks_supports_vars_placeholders(tmp_path):
    batch = {
        "command": "batch",
        "vars": {"symbol": "QQQ", "start": "2024-01-01", "end": "2024-02-01"},
        "tasks": [
            {"command": "fetch", "symbol": "${symbol}", "start": "${start}", "end": "${end}"},
            {"command": "fetch", "vars": {"symbol": "ETH"}, "symbol": "${symbol}", "start": "${start}", "end": "${end}"},
        ],
    }
    path = tmp_path / "cfg.vars_batch.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    tasks = _parse_config_tasks(str(path))
    assert len(tasks) == 2
    assert tasks[0][1].symbol == "QQQ"
    assert tasks[1][1].symbol == "ETH"


def test_parse_config_tasks_supports_simulate_resume_pipeline(tmp_path):
    batch = {
        "command": "batch",
        "vars": {
            "symbol": "QQQ",
            "state_file": "resume_demo.json",
            "start_1": "2020-01-01",
            "end_1": "2020-06-01",
            "start_2": "2020-06-02",
            "end_2": "2020-12-31",
        },
        "tasks": [
            {
                "command": "simulate",
                "symbol": "${symbol}",
                "strategy": "ma_cross",
                "params": {"fast_window": 20, "slow_window": 80},
                "start": "${start_1}",
                "end": "${end_1}",
                "state_file": "${state_file}",
            },
            {
                "command": "simulate",
                "symbol": "${symbol}",
                "strategy": "ma_cross",
                "params": {"fast_window": 20, "slow_window": 80},
                "start": "${start_2}",
                "end": "${end_2}",
                "state_file": "${state_file}",
            },
            {"command": "report", "output_file": "resume_report.md"},
        ],
    }
    path = tmp_path / "cfg.simulate_resume.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    tasks = _parse_config_tasks(str(path))
    assert len(tasks) == 3
    assert tasks[0][0] == "simulate"
    assert tasks[1][0] == "simulate"
    assert tasks[0][1].state_file == "resume_demo.json"
    assert tasks[1][1].state_file == "resume_demo.json"
    assert tasks[2][0] == "report"


def test_parse_config_tasks_supports_output_tag_compare_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.output_tag_compare.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 4
    for idx in range(3):
        command, args = tasks[idx]
        assert command == "backtest"
        assert args.output_tag
    assert tasks[3][0] == "report"


def test_parse_config_tasks_supports_mvp_daily_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.mvp_daily.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 2
    assert tasks[0][0] == "mvp"
    assert tasks[0][1].run_tag == "mvp_daily"
    assert tasks[0][1].symbols == "QQQ,ETH"
    assert tasks[0][1].strategies == "ma_cross,donchian,momentum"
    assert tasks[1][0] == "report"


def test_parse_config_tasks_supports_mvp_daily_yaml_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.mvp_daily.yaml"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 2
    assert tasks[0][0] == "mvp"
    assert tasks[0][1].run_tag == "mvp_daily"
    assert tasks[1][0] == "report"


def test_parse_config_tasks_supports_refresh_mvp_daily_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.refresh_mvp_daily.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 3
    assert tasks[0][0] == "update-cache"
    assert tasks[0][1].symbols == "QQQ,ETH"
    assert tasks[1][0] == "mvp"
    assert tasks[1][1].run_tag == "refresh_mvp_daily"
    assert tasks[2][0] == "report"
    assert tasks[2][1].output_file == "refresh_mvp_daily_report_index.md"


def test_parse_config_task_supports_mvp_yaml_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.mvp.yaml"

    command, args = _parse_config_task(str(template))
    assert command == "mvp"
    assert args.start == "2020-01-01"
    assert args.end == "2025-01-01"
    assert args.symbols == "QQQ,ETH"
    assert args.strategies == "ma_cross,donchian,momentum"


def test_parse_config_tasks_supports_signal_pilot_daily_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.signal_pilot.daily.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 4
    assert tasks[0][0] == "scan-alerts"
    assert tasks[0][1].end == "2026-03-16"
    assert tasks[1][0] == "dispatch-alerts"
    assert tasks[1][1].queue_file == "signal_pilot_notifications.jsonl"
    assert tasks[2][0] == "update-alerts"
    assert tasks[2][1].end == "2026-03-16"
    assert tasks[3][0] == "report-alerts"
    assert tasks[3][1].as_of == "2026-03-16"
    assert tasks[3][1].output_prefix == "signal_pilot_alert_report_daily"


def test_parse_config_tasks_supports_signal_pilot_daily_yaml_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.signal_pilot.daily.yaml"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 4
    assert tasks[0][0] == "scan-alerts"
    assert tasks[0][1].end == "2026-03-16"
    assert tasks[1][0] == "dispatch-alerts"
    assert tasks[2][0] == "update-alerts"
    assert tasks[2][1].end == "2026-03-16"
    assert tasks[3][0] == "report-alerts"
    assert tasks[3][1].as_of == "2026-03-16"


def test_parse_config_tasks_supports_signal_pilot_daily_account_templates():
    project_root = Path(__file__).resolve().parents[1]
    cases = [
        ("config.batch.signal_pilot.daily.default.json", "default"),
        ("config.batch.signal_pilot.daily.prod.json", "prod"),
        ("config.batch.signal_pilot.daily.research.json", "research"),
    ]
    for name, account in cases:
        tasks = _parse_config_tasks(str(project_root / "examples" / name))
        assert len(tasks) == 4
        assert tasks[0][0] == "scan-alerts"
        assert tasks[0][1].account_id == account
        assert tasks[0][1].db_file == "market_signal_system.db"
        assert tasks[1][0] == "dispatch-alerts"
        assert tasks[1][1].account_id == account
        assert tasks[1][1].db_file == "market_signal_system.db"
        assert tasks[2][0] == "update-alerts"
        assert tasks[2][1].account_id == account
        assert tasks[3][0] == "report-alerts"
        assert tasks[3][1].account_id == account


def test_parse_config_tasks_supports_baseline_daily_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.baseline.daily.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 7
    assert tasks[0][0] == "mvp"
    assert tasks[1][0] == "scan-alerts"
    assert tasks[2][0] == "dispatch-alerts"
    assert tasks[3][0] == "update-alerts"
    assert tasks[4][0] == "report-alerts"
    assert tasks[5][0] == "report"
    assert tasks[5][1].output_file == "baseline_daily_report_index.md"
    assert tasks[6][0] == "baseline-summary"
    assert tasks[6][1].output_json == "baseline_daily_digest.json"


def test_parse_config_tasks_supports_baseline_daily_yaml_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.baseline.daily.yaml"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 7
    assert tasks[0][0] == "mvp"
    assert tasks[1][0] == "scan-alerts"
    assert tasks[2][0] == "dispatch-alerts"
    assert tasks[3][0] == "update-alerts"
    assert tasks[4][0] == "report-alerts"
    assert tasks[5][0] == "report"
    assert tasks[6][0] == "baseline-summary"
    assert tasks[6][1].output_json == "baseline_daily_digest.json"


def test_parse_config_task_supports_baseline_alerts_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.baseline.summary.alerts.json"
    command, args = _parse_config_task(str(template))
    assert command == "baseline-summary"
    assert args.output_json == "baseline_daily_digest.alerts.json"
    assert args.signal_alert_window_days == 30
    assert args.signal_min_count == 3
    assert args.signal_min_win_rate == 0.5
    assert args.simulation_min_return_pct == -0.05
    assert args.emit_alert_queue is True
    assert args.alert_queue_file == "baseline_summary_alerts.jsonl"


def test_parse_config_task_supports_baseline_alerts_yaml_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.baseline.summary.alerts.yaml"
    command, args = _parse_config_task(str(template))
    assert command == "baseline-summary"
    assert args.output_csv == "baseline_daily_digest.alerts.csv"
    assert args.signal_min_avg_return_pct == 0.0
    assert args.emit_alert_queue is True


def test_parse_config_tasks_supports_baseline_alerts_daily_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.baseline.alerts.daily.json"
    tasks = _parse_config_tasks(str(template))
    assert tasks[0][0] == "mvp"
    assert tasks[6][0] == "baseline-summary"
    assert tasks[6][1].emit_alert_queue is True
    assert tasks[6][1].alert_queue_file == "baseline_summary_alerts_daily.jsonl"
    assert tasks[7][0] == "dispatch-alerts"
    assert tasks[7][1].queue_file == "baseline_summary_alerts_daily.jsonl"


def test_parse_config_tasks_supports_baseline_alerts_daily_yaml_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.baseline.alerts.daily.yaml"
    tasks = _parse_config_tasks(str(template))
    assert tasks[0][0] == "mvp"
    assert tasks[6][0] == "baseline-summary"
    assert tasks[7][0] == "dispatch-alerts"


def test_parse_config_task_supports_score_regime_research_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.research.score_regime.json"

    command, args = _parse_config_task(str(template))
    assert command == "research"
    assert args.strategy == "score_regime"
    grid = json.loads(args.grid)
    assert "score_threshold" in grid
    assert "momentum_weight" in grid


def test_parse_config_task_supports_score_regime_backtest_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.backtest.score_regime.json"

    command, args = _parse_config_task(str(template))
    assert command == "backtest"
    assert args.strategy == "score_regime"
    params = json.loads(args.params)
    assert params["trend_window"] == 200
    assert params["score_threshold"] == 0.25


def test_parse_config_task_supports_update_cache_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.update_cache.json"

    command, args = _parse_config_task(str(template))
    assert command == "update-cache"
    assert args.symbols == "QQQ,ETH"
    assert args.interval == "1d"


def test_parse_config_task_supports_dual_momentum_research_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.research.dual_momentum.json"

    command, args = _parse_config_task(str(template))
    assert command == "research"
    assert args.strategy == "dual_momentum"
    grid = json.loads(args.grid)
    assert "fast_window" in grid
    assert "slow_window" in grid


def test_parse_config_task_supports_dual_momentum_backtest_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.backtest.dual_momentum.json"

    command, args = _parse_config_task(str(template))
    assert command == "backtest"
    assert args.strategy == "dual_momentum"
    params = json.loads(args.params)
    assert params["fast_window"] == 63
    assert params["slow_window"] == 252


def test_parse_config_task_supports_atr_regime_research_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.research.atr_regime.json"

    command, args = _parse_config_task(str(template))
    assert command == "research"
    assert args.strategy == "atr_regime"
    grid = json.loads(args.grid)
    assert "atr_window" in grid
    assert "strength_threshold" in grid


def test_parse_config_task_supports_atr_regime_backtest_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.backtest.atr_regime.json"

    command, args = _parse_config_task(str(template))
    assert command == "backtest"
    assert args.strategy == "atr_regime"
    params = json.loads(args.params)
    assert params["atr_window"] == 20
    assert params["trend_window"] == 180


def test_parse_config_task_supports_signal_pilot_scan_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.signal_pilot.scan.json"
    command, args = _parse_config_task(str(template))
    assert command == "scan-alerts"
    assert args.end == "2026-03-16"
    assert args.ledger_file == "signal_alert_ledger.csv"
    assert args.notification_file == "signal_pilot_notifications.jsonl"
    assert args.account_id == "default"
    assert args.db_file is None


def test_parse_config_task_supports_signal_pilot_dispatch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.signal_pilot.dispatch.json"

    command, args = _parse_config_task(str(template))
    assert command == "dispatch-alerts"
    assert args.queue_file == "signal_pilot_notifications.jsonl"
    assert args.sink_file == "signal_pilot_notifications_dispatched.jsonl"
    assert args.max_events == 200
    assert args.retry_count == 0
    assert args.retry_delay_ms == 500
    assert args.idempotency_window_minutes == 0.0
    assert args.account_id == "default"
    assert args.db_file is None


def test_parse_config_tasks_supports_score_regime_stability_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.score_regime_stability.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 3
    assert tasks[0][0] == "research"
    assert tasks[0][1].strategy == "score_regime"
    assert tasks[1][0] == "stability"
    assert tasks[1][1].walk_forward_file == "outputs/walk_forward_QQQ_score_regime.csv"
    assert tasks[2][0] == "report"


def test_parse_config_tasks_supports_atr_regime_stability_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.atr_regime_stability.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 3
    assert tasks[0][0] == "research"
    assert tasks[0][1].strategy == "atr_regime"
    assert tasks[1][0] == "stability"
    assert tasks[1][1].walk_forward_file == "outputs/walk_forward_QQQ_atr_regime.csv"
    assert tasks[2][0] == "report"


def test_parse_config_tasks_supports_score_vs_macd_compare_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.score_vs_macd_compare.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 4
    assert tasks[0][0] == "backtest"
    assert tasks[0][1].strategy == "score_regime"
    assert tasks[0][1].output_tag == "score_base"
    assert tasks[1][0] == "backtest"
    assert tasks[1][1].strategy == "macd_regime"
    assert tasks[1][1].output_tag == "macd_base"
    assert tasks[2][0] == "compare"
    assert tasks[2][1].strategies == "score_regime,macd_regime"
    assert tasks[3][0] == "report"


def test_parse_config_tasks_supports_score_vs_macd_compare_eth_batch_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.batch.score_vs_macd_compare.eth.json"

    tasks = _parse_config_tasks(str(template))
    assert len(tasks) == 4
    assert tasks[0][0] == "backtest"
    assert tasks[0][1].strategy == "score_regime"
    assert tasks[0][1].output_tag == "score_eth_base"
    assert tasks[1][0] == "backtest"
    assert tasks[1][1].strategy == "macd_regime"
    assert tasks[1][1].output_tag == "macd_eth_base"
    assert tasks[2][0] == "compare"
    assert tasks[2][1].symbols == "ETH"
    assert tasks[3][0] == "report"


def test_parse_config_task_supports_weekly_compare_template():
    project_root = Path(__file__).resolve().parents[1]
    template = project_root / "examples" / "config.compare.weekly.json"

    command, args = _parse_config_task(str(template))
    assert command == "compare"
    assert args.symbols == "QQQ,ETH"
    assert args.interval == "1wk"
    assert "dual_momentum" in args.strategies


def test_parse_config_tasks_missing_vars_raises(tmp_path):
    batch = {
        "command": "batch",
        "vars": {"start": "2024-01-01"},
        "tasks": [
            {"command": "fetch", "symbol": "${symbol}", "start": "${start}", "end": "2024-02-01"},
        ],
    }
    path = tmp_path / "cfg.vars_missing.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _parse_config_tasks(str(path))
    assert "缺少占位符变量" in str(exc.value)


def test_parse_config_tasks_rejects_invalid_task_vars_type(tmp_path):
    batch = {
        "command": "batch",
        "vars": {"start": "2024-01-01"},
        "tasks": [
            {
                "command": "fetch",
                "vars": "not-an-object",
                "symbol": "QQQ",
                "start": "${start}",
                "end": "2024-02-01",
            },
        ],
    }
    path = tmp_path / "cfg.invalid_task_vars.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _parse_config_tasks(str(path))
    assert "tasks[].vars" in str(exc.value)


def test_parse_config_tasks_rejects_invalid_file_vars_type(tmp_path):
    task_file = {
        "command": "report",
        "output_file": "tmp.md",
    }
    (tmp_path / "task.report.json").write_text(json.dumps(task_file, ensure_ascii=False), encoding="utf-8")
    batch = {
        "command": "batch",
        "tasks": [
            {"file": "task.report.json", "vars": "bad-vars"},
        ],
    }
    path = tmp_path / "cfg.invalid_file_vars.json"
    path.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _parse_config_tasks(str(path))
    assert "tasks.file.vars" in str(exc.value)


def test_parse_batch_error_mode_defaults_and_custom(tmp_path):
    default_cfg = {"command": "report"}
    default_path = tmp_path / "default.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_error_mode(str(default_path)) == "fail_fast"

    continue_cfg = {"command": "batch", "on_error": "continue", "tasks": [{"command": "report"}]}
    continue_path = tmp_path / "continue.json"
    continue_path.write_text(json.dumps(continue_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_error_mode(str(continue_path)) == "continue"


def test_parse_batch_error_mode_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "on_error": "skip", "tasks": [{"command": "report"}]}
    path = tmp_path / "invalid_on_error.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    try:
        _parse_batch_error_mode(str(path))
    except ValueError as exc:
        assert "on_error" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_parse_batch_retry_policy_defaults_and_custom(tmp_path):
    default_cfg = {"command": "report"}
    default_path = tmp_path / "default.retry.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_policy(str(default_path)) == (0, 0)

    custom_cfg = {"command": "batch", "retry_count": 2, "retry_delay_ms": 100, "tasks": [{"command": "report"}]}
    custom_path = tmp_path / "custom.retry.json"
    custom_path.write_text(json.dumps(custom_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_policy(str(custom_path)) == (2, 100)


def test_parse_batch_retry_policy_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "retry_count": -1, "tasks": [{"command": "report"}]}
    path = tmp_path / "invalid.retry.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        _parse_batch_retry_policy(str(path))


def test_parse_batch_retry_switches_defaults_and_custom(tmp_path):
    default_cfg = {"command": "report"}
    default_path = tmp_path / "default.retry_switch.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_switches(str(default_path)) == (False, True)

    custom_cfg = {
        "command": "batch",
        "retry_count": 2,
        "retry_enabled": True,
        "retry_retryable_only": False,
        "tasks": [{"command": "report"}],
    }
    custom_path = tmp_path / "custom.retry_switch.json"
    custom_path.write_text(json.dumps(custom_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_switches(str(custom_path)) == (True, False)


def test_parse_batch_retry_budget_defaults_and_custom(tmp_path):
    default_cfg = {"command": "batch", "tasks": [{"command": "report"}]}
    default_path = tmp_path / "default.retry_budget.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_budget(str(default_path)) is None

    custom_cfg = {"command": "batch", "max_total_retries": 5, "tasks": [{"command": "report"}]}
    custom_path = tmp_path / "custom.retry_budget.json"
    custom_path.write_text(json.dumps(custom_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_retry_budget(str(custom_path)) == 5


def test_parse_batch_retry_budget_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "max_total_retries": -1, "tasks": [{"command": "report"}]}
    path = tmp_path / "invalid.retry_budget.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        _parse_batch_retry_budget(str(path))


def test_parse_config_tasks_supports_task_retry_override(tmp_path):
    task_file = {"command": "report", "output_file": "tmp_report.md"}
    (tmp_path / "task.report.json").write_text(json.dumps(task_file, ensure_ascii=False), encoding="utf-8")
    cfg = {
        "command": "batch",
        "tasks": [
            {"file": "task.report.json", "retry": {"enabled": True, "count": 1, "delay_ms": 50}},
            {"command": "report", "output_file": "tmp_report_2.md", "retry": {"retryable_only": False}},
        ],
    }
    path = tmp_path / "cfg.retry_override.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    tasks = _parse_config_tasks(str(path))
    assert getattr(tasks[0][1], "_task_retry_override") == {"enabled": True, "count": 1, "delay_ms": 50}
    assert getattr(tasks[1][1], "_task_retry_override") == {"retryable_only": False}


def test_run_config_continue_mode_raises_with_summary(tmp_path):
    cfg = {
        "command": "batch",
        "on_error": "continue",
        "tasks": [
            {"command": "unknown-task"},
            {"command": "report", "output_file": "tmp_report_for_test.md"},
        ],
    }
    path = tmp_path / "continue_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        cmd_run_config(Namespace(file=str(path)))
    assert "失败任务" in str(exc.value)


def test_run_config_fail_fast_still_raises_on_failed_task(tmp_path):
    cfg = {
        "command": "batch",
        "on_error": "fail_fast",
        "tasks": [
            {"command": "unknown-task"},
            {"command": "report", "output_file": "should_not_run.md"},
        ],
    }
    path = tmp_path / "fail_fast_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    try:
        cmd_run_config(Namespace(file=str(path)))
    except ValueError as exc:
        assert "Unsupported command" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_run_config_writes_summary_json_and_csv(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {"command": "report", "output_file": "tmp_report_for_summary.md"},
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "summary_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    assert summary_json.exists()
    assert summary_csv.exists()
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["task_count"] == 2
    assert payload["failed_count"] == 1
    assert payload["success_count"] == 1
    assert "run_started_at" in payload
    assert "run_ended_at" in payload
    assert "run_duration_ms" in payload


def test_run_config_summary_includes_symbol_group_champions_for_compare_task(tmp_path, monkeypatch):
    summary_json = OUTPUT_DIR / "tmp_batch_compare_champions_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_compare_champions_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    def _fake_compare(args: Namespace) -> None:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        out = OUTPUT_DIR / f"leaderboard_by_symbol_{'_'.join(symbols)}.csv"
        pd.DataFrame(
            [
                {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.81, "symbol_rank": 1},
                {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.77, "symbol_rank": 1},
            ]
        ).to_csv(out, index=False)

    monkeypatch.setattr("market_signal_system.cli.cmd_compare", _fake_compare)

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {
                "command": "compare",
                "symbols": "QQQ,ETH",
                "strategies": "score_regime,atr_regime",
                "start": "2024-01-01",
                "end": "2024-02-01",
            }
        ],
    }
    path = tmp_path / "summary_compare_champions.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["failed_count"] == 0
    assert payload["symbol_group_champions"][0]["task_index"] == 1
    assert payload["symbol_group_champions"][0]["champion_count"] == 2
    assert payload["symbol_group_champions"][0]["champions"][0]["symbol"] == "ETH"
    assert payload["symbol_group_champions"][0]["champions"][1]["strategy"] == "atr_regime"
    assert "ETH:score_regime(0.8100)" in payload["results"][0]["symbol_group_champions"]


def test_run_config_compare_champions_tolerates_missing_composite_score(tmp_path, monkeypatch):
    summary_json = OUTPUT_DIR / "tmp_batch_compare_champions_missing_score_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_compare_champions_missing_score_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    def _fake_compare(args: Namespace) -> None:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        out = OUTPUT_DIR / f"leaderboard_by_symbol_{'_'.join(symbols)}.csv"
        pd.DataFrame(
            [
                {"symbol": "ETH", "strategy": "score_regime", "symbol_rank": 1},
                {"symbol": "QQQ", "strategy": "atr_regime", "symbol_rank": 1},
            ]
        ).to_csv(out, index=False)

    monkeypatch.setattr("market_signal_system.cli.cmd_compare", _fake_compare)

    cfg = {
        "command": "batch",
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {
                "command": "compare",
                "symbols": "QQQ,ETH",
                "strategies": "score_regime,atr_regime",
                "start": "2024-01-01",
                "end": "2024-02-01",
            }
        ],
    }
    path = tmp_path / "summary_compare_champions_missing_score.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["failed_count"] == 0
    assert payload["symbol_group_champions"][0]["champion_count"] == 2
    assert payload["symbol_group_champions"][0]["champions"][0]["composite_score"] == 0.0


def test_run_config_default_retry_only_applies_to_retryable_errors(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_retry_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_retry_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 2,
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {"command": "stability", "walk_forward_file": str(tmp_path / "missing.csv")},
        ],
    }
    path = tmp_path / "retry_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["failed_count"] == 1
    assert payload["retry_retryable_only"] is True
    assert payload["results"][0]["attempts"] == 1


def test_run_config_can_disable_retryable_only_and_force_retry(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_retry_force_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_retry_force_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 2,
        "retry_retryable_only": False,
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "retry_force_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["retry_retryable_only"] is False
    assert payload["results"][0]["attempts"] == 3


def test_run_config_respects_task_retry_count_override(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_retry_task_override_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_retry_task_override_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 3,
        "retry_retryable_only": False,
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {"command": "unknown-task", "retry": {"count": 0}},
        ],
    }
    path = tmp_path / "retry_task_override_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["results"][0]["attempts"] == 1
    assert payload["results"][0]["retries_used"] == 0


def test_run_config_respects_total_retry_budget(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_retry_budget_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_retry_budget_summary.csv"
    if summary_json.exists():
        summary_json.unlink()
    if summary_csv.exists():
        summary_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 3,
        "retry_retryable_only": False,
        "max_total_retries": 1,
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "tasks": [
            {"command": "unknown-task"},
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "retry_budget_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["max_total_retries"] == 1
    assert payload["retry_budget_remaining"] == 0
    assert payload["results"][0]["attempts"] == 2
    assert payload["results"][1]["attempts"] == 1


def test_parse_batch_summary_paths_defaults_for_batch(tmp_path):
    cfg = {"command": "batch", "tasks": [{"command": "report"}]}
    path = tmp_path / "cfg.batch.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    summary_json, summary_csv = _parse_batch_summary_paths(str(path), is_batch=True)
    assert summary_json is not None
    assert summary_csv is not None
    assert summary_json.name == "run_config_batch_summary.json"
    assert summary_csv.name == "run_config_batch_summary.csv"


def test_parse_config_tasks_raises_on_missing_placeholder_var(tmp_path):
    cfg = {
        "command": "batch",
        "vars": {"start": "2024-01-01", "end": "2024-02-01"},
        "tasks": [
            {"command": "fetch", "symbol": "${symbol}", "start": "${start}", "end": "${end}"},
        ],
    }
    path = tmp_path / "cfg.missing_var.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    try:
        _parse_config_tasks(str(path))
    except ValueError as exc:
        assert "vars 缺少占位符变量" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_parse_config_tasks_raises_on_invalid_vars_type(tmp_path):
    cfg = {
        "command": "batch",
        "vars": ["QQQ"],
        "tasks": [{"command": "report"}],
    }
    path = tmp_path / "cfg.bad_vars_type.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    try:
        _parse_config_tasks(str(path))
    except ValueError as exc:
        assert "vars 必须是 JSON 对象" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_parse_config_tasks_raises_on_invalid_task_vars_type(tmp_path):
    cfg = {
        "command": "batch",
        "vars": {"start": "2024-01-01", "end": "2024-02-01"},
        "tasks": [
            {
                "command": "fetch",
                "vars": ["ETH"],
                "symbol": "QQQ",
                "start": "${start}",
                "end": "${end}",
            }
        ],
    }
    path = tmp_path / "cfg.bad_task_vars_type.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _parse_config_tasks(str(path))
    assert "tasks[].vars 必须是 JSON 对象" in str(exc.value)


def test_parse_batch_summary_paths_supports_vars(tmp_path):
    cfg = {
        "command": "batch",
        "vars": {"tag": "demo"},
        "summary_json": "summary_${tag}.json",
        "summary_csv": "summary_${tag}.csv",
        "tasks": [{"command": "report"}],
    }
    path = tmp_path / "cfg.batch.vars.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    summary_json, summary_csv = _parse_batch_summary_paths(str(path), is_batch=True)
    assert summary_json is not None and summary_json.name == "summary_demo.json"
    assert summary_csv is not None and summary_csv.name == "summary_demo.csv"


def test_parse_batch_summary_paths_rejects_non_string_values(tmp_path):
    cfg = {
        "command": "batch",
        "summary_json": 123,
        "summary_csv": [],
        "tasks": [{"command": "report"}],
    }
    path = tmp_path / "cfg.batch.invalid_summary.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _parse_batch_summary_paths(str(path), is_batch=True)
    assert "summary_json" in str(exc.value) or "summary_csv" in str(exc.value)


def test_parse_batch_summary_compress_defaults_and_custom(tmp_path):
    default_cfg = {"command": "batch", "tasks": [{"command": "report"}]}
    default_path = tmp_path / "cfg.batch.default_compress.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_summary_compress(str(default_path)) == "none"

    gzip_cfg = {"command": "batch", "summary_compress": "gzip", "tasks": [{"command": "report"}]}
    gzip_path = tmp_path / "cfg.batch.gzip_compress.json"
    gzip_path.write_text(json.dumps(gzip_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_batch_summary_compress(str(gzip_path)) == "gzip"


def test_parse_batch_summary_compress_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "summary_compress": "zip", "tasks": [{"command": "report"}]}
    path = tmp_path / "cfg.batch.invalid_compress.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        _parse_batch_summary_compress(str(path))
    assert "summary_compress" in str(exc.value)


def test_parse_compress_naming_defaults_and_custom(tmp_path):
    default_cfg = {"command": "batch", "tasks": [{"command": "report"}]}
    default_path = tmp_path / "cfg.batch.default_compress_naming.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_compress_naming(str(default_path)) == "auto_suffix"

    strict_cfg = {"command": "batch", "compress_naming": "strict", "tasks": [{"command": "report"}]}
    strict_path = tmp_path / "cfg.batch.strict_compress_naming.json"
    strict_path.write_text(json.dumps(strict_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_compress_naming(str(strict_path)) == "strict"


def test_parse_compress_naming_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "compress_naming": "manual", "tasks": [{"command": "report"}]}
    path = tmp_path / "cfg.batch.invalid_compress_naming.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        _parse_compress_naming(str(path))
    assert "compress_naming" in str(exc.value)


def test_parse_retry_budget_trace_path_defaults_and_custom(tmp_path):
    cfg_default = {"command": "batch", "max_total_retries": 2, "tasks": [{"command": "report"}]}
    path_default = tmp_path / "cfg.batch.default_trace.json"
    path_default.write_text(json.dumps(cfg_default, ensure_ascii=False), encoding="utf-8")
    trace_path = _parse_retry_budget_trace_path(str(path_default), is_batch=True)
    assert trace_path is not None
    assert trace_path.name == "run_config_retry_budget_trace.csv"

    cfg_custom = {
        "command": "batch",
        "vars": {"tag": "demo"},
        "max_total_retries": 2,
        "retry_budget_trace_csv": "trace_${tag}.csv",
        "tasks": [{"command": "report"}],
    }
    path_custom = tmp_path / "cfg.batch.custom_trace.json"
    path_custom.write_text(json.dumps(cfg_custom, ensure_ascii=False), encoding="utf-8")
    trace_custom = _parse_retry_budget_trace_path(str(path_custom), is_batch=True)
    assert trace_custom is not None
    assert trace_custom.name == "trace_demo.csv"


def test_parse_retry_budget_trace_path_rejects_non_string(tmp_path):
    cfg = {"command": "batch", "retry_budget_trace_csv": 123, "tasks": [{"command": "report"}]}
    path = tmp_path / "cfg.batch.invalid_trace.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        _parse_retry_budget_trace_path(str(path), is_batch=True)
    assert "retry_budget_trace_csv" in str(exc.value)


def test_parse_retry_budget_trace_compress_defaults_and_custom(tmp_path):
    default_cfg = {"command": "batch", "tasks": [{"command": "report"}]}
    default_path = tmp_path / "cfg.batch.default_trace_compress.json"
    default_path.write_text(json.dumps(default_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_retry_budget_trace_compress(str(default_path)) == "none"

    custom_cfg = {"command": "batch", "retry_budget_trace_compress": "gzip", "tasks": [{"command": "report"}]}
    custom_path = tmp_path / "cfg.batch.trace_compress.json"
    custom_path.write_text(json.dumps(custom_cfg, ensure_ascii=False), encoding="utf-8")
    assert _parse_retry_budget_trace_compress(str(custom_path)) == "gzip"


def test_parse_retry_budget_trace_compress_rejects_invalid_value(tmp_path):
    cfg = {"command": "batch", "retry_budget_trace_compress": "zip", "tasks": [{"command": "report"}]}
    path = tmp_path / "cfg.batch.invalid_trace_compress.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        _parse_retry_budget_trace_compress(str(path))
    assert "retry_budget_trace_compress" in str(exc.value)


def test_run_config_writes_retry_budget_trace_csv(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_retry_trace_summary.json"
    summary_csv = OUTPUT_DIR / "tmp_batch_retry_trace_summary.csv"
    trace_csv = OUTPUT_DIR / "tmp_batch_retry_trace.csv"
    for p in [summary_json, summary_csv, trace_csv]:
        if p.exists():
            p.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 2,
        "retry_retryable_only": False,
        "max_total_retries": 1,
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "retry_budget_trace_csv": trace_csv.name,
        "tasks": [
            {"command": "unknown-task"},
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "retry_trace_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    assert trace_csv.exists()
    trace_df = pd.read_csv(trace_csv)
    assert len(trace_df) == 2
    assert list(trace_df["budget_before"]) == [1, 0]
    assert list(trace_df["budget_after"]) == [0, 0]


def test_run_config_writes_gzip_retry_budget_trace_csv(tmp_path):
    trace_csv = OUTPUT_DIR / "tmp_batch_retry_trace_gzip.csv.gz"
    if trace_csv.exists():
        trace_csv.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "retry_count": 1,
        "retry_retryable_only": False,
        "max_total_retries": 1,
        "retry_budget_trace_csv": "tmp_batch_retry_trace_gzip.csv",
        "retry_budget_trace_compress": "gzip",
        "tasks": [
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "retry_trace_gzip_exec.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    assert trace_csv.exists()
    trace_df = pd.read_csv(trace_csv, compression="gzip")
    assert len(trace_df) == 1
    assert trace_df.loc[0, "budget_before"] == 1
    assert trace_df.loc[0, "budget_after"] == 0


def test_run_config_writes_gzip_summary_files(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_summary_gzip.json.gz"
    summary_csv = OUTPUT_DIR / "tmp_batch_summary_gzip.csv.gz"
    for p in [summary_json, summary_csv]:
        if p.exists():
            p.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": "tmp_batch_summary_gzip.json",
        "summary_csv": "tmp_batch_summary_gzip.csv",
        "summary_compress": "gzip",
        "tasks": [
            {"command": "report", "output_file": "tmp_report_for_gzip.md"},
            {"command": "unknown-task"},
        ],
    }
    path = tmp_path / "summary_exec_gzip.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    assert summary_json.exists()
    assert summary_csv.exists()
    with gzip.open(summary_json, "rt", encoding="utf-8") as fp:
        payload = json.load(fp)
    assert payload["task_count"] == 2
    assert payload["failed_count"] == 1
    summary_df = pd.read_csv(summary_csv, compression="gzip")
    assert len(summary_df) == 2


def test_run_config_strict_compress_naming_requires_gz_suffix(tmp_path):
    cfg = {
        "command": "batch",
        "summary_json": "tmp_batch_summary_strict.json",
        "summary_csv": "tmp_batch_summary_strict.csv",
        "summary_compress": "gzip",
        "compress_naming": "strict",
        "tasks": [{"command": "report", "output_file": "tmp_report_for_strict.md"}],
    }
    path = tmp_path / "summary_exec_strict.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        cmd_run_config(Namespace(file=str(path)))
    assert ".gz" in str(exc.value)


def test_run_config_strict_compress_naming_accepts_gz_suffix(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_summary_strict_ok.json.gz"
    summary_csv = OUTPUT_DIR / "tmp_batch_summary_strict_ok.csv.gz"
    for p in [summary_json, summary_csv]:
        if p.exists():
            p.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "summary_compress": "gzip",
        "compress_naming": "strict",
        "tasks": [
            {"command": "report", "output_file": "tmp_report_for_strict_ok.md"},
        ],
    }
    path = tmp_path / "summary_exec_strict_ok.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    cmd_run_config(Namespace(file=str(path)))

    assert summary_json.exists()
    assert summary_csv.exists()
    with gzip.open(summary_json, "rt", encoding="utf-8") as fp:
        payload = json.load(fp)
    assert payload["task_count"] == 1
    assert payload["failed_count"] == 0
    summary_df = pd.read_csv(summary_csv, compression="gzip")
    assert len(summary_df) == 1


def test_run_config_strict_compress_naming_requires_gz_suffix_for_retry_trace(tmp_path):
    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": "tmp_batch_summary_strict_trace.json.gz",
        "summary_csv": "tmp_batch_summary_strict_trace.csv.gz",
        "summary_compress": "gzip",
        "compress_naming": "strict",
        "max_total_retries": 1,
        "retry_budget_trace_compress": "gzip",
        "retry_budget_trace_csv": "tmp_batch_retry_trace_strict.csv",
        "tasks": [{"command": "unknown-task"}],
    }
    path = tmp_path / "summary_exec_strict_trace_invalid.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        cmd_run_config(Namespace(file=str(path)))
    assert ".gz" in str(exc.value)


def test_run_config_strict_compress_naming_accepts_gz_suffix_for_retry_trace(tmp_path):
    summary_json = OUTPUT_DIR / "tmp_batch_summary_strict_trace_ok.json.gz"
    summary_csv = OUTPUT_DIR / "tmp_batch_summary_strict_trace_ok.csv.gz"
    trace_csv = OUTPUT_DIR / "tmp_batch_retry_trace_strict_ok.csv.gz"
    for p in [summary_json, summary_csv, trace_csv]:
        if p.exists():
            p.unlink()

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "summary_json": summary_json.name,
        "summary_csv": summary_csv.name,
        "summary_compress": "gzip",
        "compress_naming": "strict",
        "retry_count": 1,
        "retry_retryable_only": False,
        "max_total_retries": 1,
        "retry_budget_trace_compress": "gzip",
        "retry_budget_trace_csv": trace_csv.name,
        "tasks": [{"command": "unknown-task"}],
    }
    path = tmp_path / "summary_exec_strict_trace_ok.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError):
        cmd_run_config(Namespace(file=str(path)))

    assert summary_json.exists()
    assert summary_csv.exists()
    assert trace_csv.exists()
    trace_df = pd.read_csv(trace_csv, compression="gzip")
    assert len(trace_df) == 1
