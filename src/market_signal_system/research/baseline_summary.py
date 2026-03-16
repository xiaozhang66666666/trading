"""Build deduplicated baseline daily digest from MVP + Signal Pilot + report artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.signal_pilot.ledger import load_alert_ledger
from market_signal_system.storage import DEFAULT_ACCOUNT_ID, SQLiteStore, normalize_account_id


def _to_float(value: Any, default: float = 0.0) -> float:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return default
    return float(num)


def _pick_latest_file(output_dir: Path, patterns: list[str]) -> Path | None:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(output_dir.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _resolve_alert_ledger_path(output_dir: Path, alert_ledger_file: str | None) -> Path:
    state_default = output_dir.parent / "data" / "state" / "signal_alert_ledger.csv"
    if not alert_ledger_file:
        return state_default
    raw = Path(alert_ledger_file)
    if raw.is_absolute():
        return raw
    output_candidate = output_dir / raw
    state_candidate = output_dir.parent / "data" / "state" / raw
    if output_candidate.exists():
        return output_candidate
    if state_candidate.exists():
        return state_candidate
    # 优先对齐 CLI 文档语义：相对路径默认基于 data/state。
    return state_candidate


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _extract_report_highlights(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("-")]

    def find_contains(keyword: str) -> str:
        for line in lines:
            if keyword in line:
                return line.removeprefix("- ").strip()
        return ""

    out: dict[str, str] = {}
    for key in (
        "aggregate_last_",
        "aggregate_all_runs",
        "champion_switch_last_",
        "failed_top_commands",
        "retry_budget_trace",
    ):
        val = find_contains(key)
        if val:
            out[key.rstrip("_")] = val
    # 提取“批处理执行摘要”中的最新一条 run 行，便于快速定位本次批处理状态。
    run_line = ""
    run_pattern = re.compile(r"run_id=.*tasks=.*success=.*failed=.*")
    for line in lines:
        core = line.removeprefix("- ").strip()
        if run_pattern.search(core):
            run_line = core
    if run_line:
        out["latest_run"] = run_line
    return out


def _build_signal_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    if df.empty or "window_days" not in df.columns:
        return {}
    df["window_days"] = pd.to_numeric(df["window_days"], errors="coerce")
    df["signal_count"] = pd.to_numeric(df.get("signal_count", 0), errors="coerce").fillna(0)
    df["win_rate"] = pd.to_numeric(df.get("win_rate", 0.0), errors="coerce").fillna(0.0)
    df["avg_return_pct"] = pd.to_numeric(df.get("avg_return_pct", 0.0), errors="coerce").fillna(0.0)
    df = df.dropna(subset=["window_days"]).copy()
    if df.empty:
        return {}

    metrics: dict[str, dict[str, float | int]] = {}
    for window, group in df.groupby("window_days"):
        total_signals = int(group["signal_count"].sum())
        weighted_win = (
            float((group["win_rate"] * group["signal_count"]).sum() / total_signals) if total_signals > 0 else 0.0
        )
        weighted_return = (
            float((group["avg_return_pct"] * group["signal_count"]).sum() / total_signals)
            if total_signals > 0
            else 0.0
        )
        metrics[str(int(window))] = {
            "signal_count": total_signals,
            "win_rate": weighted_win,
            "avg_return_pct": weighted_return,
        }
    return metrics


def _summary_to_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(category: str, key: str, value: Any, source: str) -> None:
        rows.append({"category": category, "key": key, "value": value, "source": source})

    src = summary.get("sources", {})
    mvp = summary.get("mvp", {})
    signal = summary.get("signal_pilot", {})
    dispatch = summary.get("signal_dispatch", {})
    dispatch_health = summary.get("signal_dispatch_health", {})
    report = summary.get("report", {})

    mvp_source = str(src.get("mvp_summary", ""))
    for symbol, row in (mvp.get("backtest_best_by_symbol", {}) or {}).items():
        add("mvp_backtest", f"{symbol}.strategy", row.get("strategy", ""), mvp_source)
        add("mvp_backtest", f"{symbol}.total_return", _to_float(row.get("total_return")), mvp_source)
        add("mvp_backtest", f"{symbol}.sharpe", _to_float(row.get("sharpe")), mvp_source)

    for symbol, row in (mvp.get("simulation_snapshot_by_symbol", {}) or {}).items():
        add("mvp_simulation", f"{symbol}.total_equity", _to_float(row.get("total_equity")), mvp_source)
        add("mvp_simulation", f"{symbol}.cumulative_pnl", _to_float(row.get("cumulative_pnl")), mvp_source)
        add("mvp_simulation", f"{symbol}.return_pct", _to_float(row.get("return_pct")), mvp_source)

    signal_source = str(src.get("signal_report", ""))
    for window, row in (signal.get("windows", {}) or {}).items():
        add("signal_pilot", f"window_{window}.signal_count", int(row.get("signal_count", 0)), signal_source)
        add("signal_pilot", f"window_{window}.win_rate", _to_float(row.get("win_rate")), signal_source)
        add("signal_pilot", f"window_{window}.avg_return_pct", _to_float(row.get("avg_return_pct")), signal_source)

    dispatch_source = str(src.get("alert_ledger", ""))
    for key in ("open_alerts", "pending_notification", "failed_notification", "failed_ratio"):
        if key in dispatch:
            add("signal_dispatch", key, dispatch.get(key), dispatch_source)
    dispatch_db_source = str(src.get("dispatch_db", ""))
    for key in (
        "dispatch_window_days",
        "attempt_count",
        "sent_count",
        "failed_count",
        "failed_ratio",
        "retry_used_count",
        "retry_hit_rate",
        "retry_count_sum",
        "last_event_time",
    ):
        if key in dispatch_health:
            add("signal_dispatch_health", key, dispatch_health.get(key), dispatch_db_source)

    report_source = str(src.get("report_index", ""))
    for key, value in (report.get("highlights", {}) or {}).items():
        add("report", key, str(value), report_source)

    for idx, alert in enumerate((summary.get("alerts", []) or []), start=1):
        if not isinstance(alert, dict):
            continue
        add("alerts", f"#{idx}.alert_id", str(alert.get("alert_id", "")), "computed")
        add("alerts", f"#{idx}.level", str(alert.get("level", "")), "computed")
        add("alerts", f"#{idx}.metric", str(alert.get("metric", "")), "computed")
        add("alerts", f"#{idx}.message", str(alert.get("message", "")), "computed")

    return rows


def _build_baseline_alerts(
    *,
    as_of_ts: pd.Timestamp,
    signal_metrics: dict[str, dict[str, float | int]],
    sim_snapshot: dict[str, dict[str, Any]],
    signal_alert_window_days: int,
    signal_min_count: int,
    signal_min_win_rate: float,
    signal_min_avg_return_pct: float,
    simulation_min_return_pct: float,
    dispatch_metrics: dict[str, float | int] | None,
    dispatch_max_failed_count: int,
    dispatch_max_failed_ratio: float,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    window_key = str(int(signal_alert_window_days))
    signal_row = signal_metrics.get(window_key, {})

    signal_count = int(_to_float(signal_row.get("signal_count"), 0.0))
    win_rate = _to_float(signal_row.get("win_rate"), 0.0)
    avg_return_pct = _to_float(signal_row.get("avg_return_pct"), 0.0)

    if signal_count < int(signal_min_count):
        alerts.append(
            {
                "alert_id": f"baseline_signal_count_{window_key}_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                "level": "watch",
                "metric": f"signal.window_{window_key}.signal_count",
                "value": signal_count,
                "threshold": int(signal_min_count),
                "message": f"window={window_key} 信号数不足：{signal_count} < {int(signal_min_count)}",
            }
        )
    if win_rate < float(signal_min_win_rate):
        alerts.append(
            {
                "alert_id": f"baseline_signal_win_rate_{window_key}_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                "level": "high",
                "metric": f"signal.window_{window_key}.win_rate",
                "value": win_rate,
                "threshold": float(signal_min_win_rate),
                "message": f"window={window_key} 胜率偏低：{win_rate:.4f} < {float(signal_min_win_rate):.4f}",
            }
        )
    if avg_return_pct < float(signal_min_avg_return_pct):
        alerts.append(
            {
                "alert_id": f"baseline_signal_avg_return_{window_key}_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                "level": "high",
                "metric": f"signal.window_{window_key}.avg_return_pct",
                "value": avg_return_pct,
                "threshold": float(signal_min_avg_return_pct),
                "message": (
                    f"window={window_key} 平均收益偏低：{avg_return_pct:.4f} < {float(signal_min_avg_return_pct):.4f}"
                ),
            }
        )

    for symbol, snap in sim_snapshot.items():
        sim_return = _to_float(snap.get("return_pct"), 0.0)
        if sim_return < float(simulation_min_return_pct):
            alerts.append(
                {
                    "alert_id": f"baseline_sim_return_{symbol}_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                    "level": "high",
                    "metric": f"simulation.{symbol}.return_pct",
                    "value": sim_return,
                    "threshold": float(simulation_min_return_pct),
                    "message": (
                        f"{symbol} 模拟累计收益偏低：{sim_return:.4f} < {float(simulation_min_return_pct):.4f}"
                    ),
                }
            )

    dispatch = dispatch_metrics or {}
    failed_count = int(_to_float(dispatch.get("failed_notification"), 0.0))
    failed_ratio = _to_float(dispatch.get("failed_ratio"), 0.0)
    if failed_count > int(dispatch_max_failed_count):
        alerts.append(
            {
                "alert_id": f"baseline_dispatch_failed_count_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                "level": "watch",
                "metric": "dispatch.failed_notification",
                "value": failed_count,
                "threshold": int(dispatch_max_failed_count),
                "message": f"通知失败累计偏高：{failed_count} > {int(dispatch_max_failed_count)}",
            }
        )
    if failed_ratio > float(dispatch_max_failed_ratio):
        alerts.append(
            {
                "alert_id": f"baseline_dispatch_failed_ratio_{as_of_ts.strftime('%Y%m%dT%H%M%SZ')}",
                "level": "high",
                "metric": "dispatch.failed_ratio",
                "value": failed_ratio,
                "threshold": float(dispatch_max_failed_ratio),
                "message": f"通知失败占比偏高：{failed_ratio:.4f} > {float(dispatch_max_failed_ratio):.4f}",
            }
        )

    return alerts


def _build_dispatch_metrics(ledger: pd.DataFrame | None) -> dict[str, float | int]:
    if ledger is None:
        return {}
    if ledger.empty:
        return {"open_alerts": 0, "pending_notification": 0, "failed_notification": 0, "failed_ratio": 0.0}

    status = ledger.get("status", pd.Series("", index=ledger.index)).astype(str).str.lower()
    sent = ledger.get("notification_sent", pd.Series(False, index=ledger.index)).map(
        lambda v: bool(v) if pd.notna(v) else False
    )
    fail_count = pd.to_numeric(ledger.get("notification_fail_count", 0), errors="coerce").fillna(0).astype(int)
    open_mask = status.eq("open")
    pending_mask = open_mask & (~sent.astype(bool))
    failed_mask = pending_mask & fail_count.gt(0)
    pending = int(pending_mask.sum())
    failed = int(failed_mask.sum())
    ratio = float(failed / pending) if pending > 0 else 0.0
    return {
        "open_alerts": int(open_mask.sum()),
        "pending_notification": pending,
        "failed_notification": failed,
        "failed_ratio": ratio,
    }


def _build_dispatch_db_metrics(
    *,
    account_id: str,
    db_file: str | None,
    as_of_ts: pd.Timestamp,
    dispatch_window_days: int,
) -> dict[str, float | int | str]:
    try:
        store = SQLiteStore(db_file)
    except Exception:
        return {}
    window_start = (as_of_ts - pd.Timedelta(days=int(dispatch_window_days))).isoformat()
    rows = store.list_dispatch_records(account_id, start_time=window_start, end_time=as_of_ts.isoformat())
    if rows.empty:
        return {
            "dispatch_window_days": int(dispatch_window_days),
            "attempt_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "failed_ratio": 0.0,
            "retry_used_count": 0,
            "retry_hit_rate": 0.0,
            "retry_count_sum": 0,
        }

    status = rows.get("status", pd.Series("", index=rows.index)).astype(str).str.lower()
    sent = status.eq("sent")
    failed = status.eq("failed")
    attempts = int(len(rows))
    sent_count = int(sent.sum())
    failed_count = int(failed.sum())
    retry_used_count = int(rows.get("used_retry", pd.Series(False, index=rows.index)).astype(bool).sum())
    retry_count_sum = int(pd.to_numeric(rows.get("retry_count", 0), errors="coerce").fillna(0).sum())
    last_event_time = rows.get("event_time", pd.Series("", index=rows.index)).astype(str).replace("", pd.NA).dropna()
    metrics: dict[str, float | int | str] = {
        "dispatch_window_days": int(dispatch_window_days),
        "attempt_count": attempts,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "failed_ratio": float(failed_count / attempts) if attempts > 0 else 0.0,
        "retry_used_count": retry_used_count,
        "retry_hit_rate": float(retry_used_count / attempts) if attempts > 0 else 0.0,
        "retry_count_sum": retry_count_sum,
    }
    if not last_event_time.empty:
        metrics["last_event_time"] = str(last_event_time.iloc[-1])
    return metrics


def _resolve_dispatch_db_file(ledger_path: Path, db_file: str | None) -> str:
    if db_file:
        return db_file
    return str(ledger_path.parent / "market_signal_system.db")


def build_baseline_daily_summary(
    output_dir: Path,
    *,
    as_of: str | None = None,
    mvp_summary_file: str | None = None,
    signal_report_json_file: str | None = None,
    report_index_file: str | None = None,
    alert_ledger_file: str | None = None,
    account_id: str = DEFAULT_ACCOUNT_ID,
    db_file: str | None = None,
    dispatch_window_days: int = 30,
    signal_alert_window_days: int = 30,
    signal_min_count: int = 3,
    signal_min_win_rate: float = 0.5,
    signal_min_avg_return_pct: float = 0.0,
    simulation_min_return_pct: float = -0.05,
    dispatch_max_failed_count: int = 3,
    dispatch_max_failed_ratio: float = 0.5,
) -> dict[str, Any]:
    out = output_dir
    out.mkdir(parents=True, exist_ok=True)

    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(datetime.now(timezone.utc))
    if as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")
    else:
        as_of_ts = as_of_ts.tz_convert("UTC")

    mvp_path = (out / mvp_summary_file) if mvp_summary_file else _pick_latest_file(out, ["mvp_summary_*.json"])
    signal_path = (
        (out / signal_report_json_file)
        if signal_report_json_file
        else _pick_latest_file(out, ["signal_pilot_alert_report_daily_*.json", "signal_pilot_alert_report_*.json"])
    )
    report_path = (out / report_index_file) if report_index_file else _pick_latest_file(
        out,
        ["baseline_daily_report_index.md", "report_index.md"],
    )
    account = normalize_account_id(account_id)
    ledger_path = _resolve_alert_ledger_path(out, alert_ledger_file)

    mvp_payload = _load_json(mvp_path)
    signal_payload = _load_json(signal_path)
    ledger_frame: pd.DataFrame | None = None
    try:
        ledger_frame = load_alert_ledger(ledger_path, account_id=account, db_path=db_file)
    except Exception:
        ledger_frame = None
    dispatch_metrics = _build_dispatch_metrics(ledger_frame)
    effective_db_file = _resolve_dispatch_db_file(ledger_path, db_file)
    dispatch_db_metrics = _build_dispatch_db_metrics(
        account_id=account,
        db_file=effective_db_file,
        as_of_ts=as_of_ts,
        dispatch_window_days=int(dispatch_window_days),
    )

    best_by_symbol: dict[str, dict[str, Any]] = {}
    for symbol, rows in (mvp_payload.get("backtest_topn_by_symbol", {}) or {}).items():
        if isinstance(rows, list) and rows:
            top = rows[0] if isinstance(rows[0], dict) else {}
            best_by_symbol[str(symbol)] = {
                "strategy": str(top.get("strategy", "")),
                "total_return": _to_float(top.get("total_return")),
                "sharpe": _to_float(top.get("sharpe")),
                "max_drawdown": _to_float(top.get("max_drawdown")),
            }

    sim_snapshot: dict[str, dict[str, Any]] = {}
    for row in (mvp_payload.get("simulations", []) or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).upper()
        snap = row.get("snapshot", {}) if isinstance(row.get("snapshot"), dict) else {}
        if not symbol:
            continue
        sim_snapshot[symbol] = {
            "trade_count": int(_to_float(row.get("trade_count"), 0.0)),
            "total_equity": _to_float(snap.get("total_equity")),
            "cumulative_pnl": _to_float(snap.get("cumulative_pnl")),
            "return_pct": _to_float(snap.get("return_pct")),
        }

    signal_rows = signal_payload.get("rows", []) if isinstance(signal_payload, dict) else []
    signal_metrics = _build_signal_metrics(signal_rows if isinstance(signal_rows, list) else [])
    alerts = _build_baseline_alerts(
        as_of_ts=as_of_ts,
        signal_metrics=signal_metrics,
        sim_snapshot=sim_snapshot,
        signal_alert_window_days=int(signal_alert_window_days),
        signal_min_count=int(signal_min_count),
        signal_min_win_rate=float(signal_min_win_rate),
        signal_min_avg_return_pct=float(signal_min_avg_return_pct),
        simulation_min_return_pct=float(simulation_min_return_pct),
        dispatch_metrics=dispatch_metrics,
        dispatch_max_failed_count=int(dispatch_max_failed_count),
        dispatch_max_failed_ratio=float(dispatch_max_failed_ratio),
    )

    summary = {
        "as_of": as_of_ts.isoformat(),
        "sources": {
            "mvp_summary": mvp_path.name if mvp_path and mvp_path.exists() else None,
            "signal_report": signal_path.name if signal_path and signal_path.exists() else None,
            "report_index": report_path.name if report_path and report_path.exists() else None,
            "alert_ledger": ledger_path.name if ledger_path and ledger_path.exists() else None,
            "dispatch_db": Path(effective_db_file).name if effective_db_file else None,
        },
        "account_id": account,
        "mvp": {
            "run_tag": mvp_payload.get("run_tag"),
            "symbols": mvp_payload.get("symbols", []),
            "strategies": mvp_payload.get("strategies", []),
            "backtest_best_by_symbol": best_by_symbol,
            "simulation_snapshot_by_symbol": sim_snapshot,
        },
        "signal_pilot": {
            "report_as_of": signal_payload.get("as_of") if isinstance(signal_payload, dict) else None,
            "windows": signal_metrics,
        },
        "signal_dispatch": dispatch_metrics,
        "signal_dispatch_health": dispatch_db_metrics,
        "report": {
            "highlights": _extract_report_highlights(report_path),
        },
        "alert_rules": {
            "dispatch_window_days": int(dispatch_window_days),
            "signal_alert_window_days": int(signal_alert_window_days),
            "signal_min_count": int(signal_min_count),
            "signal_min_win_rate": float(signal_min_win_rate),
            "signal_min_avg_return_pct": float(signal_min_avg_return_pct),
            "simulation_min_return_pct": float(simulation_min_return_pct),
            "dispatch_max_failed_count": int(dispatch_max_failed_count),
            "dispatch_max_failed_ratio": float(dispatch_max_failed_ratio),
        },
        "alerts": alerts,
    }

    summary["rows"] = _summary_to_rows(summary)
    return summary


__all__ = ["build_baseline_daily_summary"]
