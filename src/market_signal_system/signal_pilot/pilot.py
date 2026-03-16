"""Signal pilot workflows: scan / update / report."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.data.manager import DataManager
from market_signal_system.signal_pilot.ledger import (
    create_alert_row,
    load_alert_ledger,
    normalize_strategy_params,
    save_alert_ledger,
    upsert_alert_rows,
)
from market_signal_system.strategies import get_strategy
from market_signal_system.utils.paths import OUTPUT_DIR


def _signal_to_side(signal: int) -> str:
    if signal > 0:
        return "long"
    if signal < 0:
        return "short"
    return "flat"


def _parse_iso_ts(raw: str) -> pd.Timestamp:
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _has_open_same_side(
    ledger: pd.DataFrame,
    *,
    symbol: str,
    strategy: str,
    interval: str,
    side: str,
    strategy_params: str,
) -> bool:
    if ledger.empty:
        return False
    mask = (
        ledger["status"].astype(str).eq("open")
        & ledger["symbol"].astype(str).str.upper().eq(symbol.upper())
        & ledger["strategy"].astype(str).str.lower().eq(strategy.lower())
        & ledger["interval"].astype(str).eq(interval)
        & ledger["side"].astype(str).eq(side)
        & ledger["strategy_params"].astype(str).eq(strategy_params)
    )
    return bool(mask.any())


def _append_notifications(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def scan_alerts(
    *,
    symbols: list[str],
    strategy_name: str,
    interval: str,
    strategy_params: dict[str, Any] | None = None,
    lookback_days: int = 365,
    end: str | None = None,
    ledger_path: str | Path | None = None,
    notification_file: str | Path | None = None,
    account_id: str = "default",
    db_path: str | Path | None = None,
    data_manager: DataManager | None = None,
) -> dict[str, Any]:
    dm = data_manager or DataManager()
    strategy = get_strategy(strategy_name, **(strategy_params or {}))
    end_ts = pd.Timestamp(end) if end else pd.Timestamp(datetime.now(timezone.utc))
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")
    start_ts = end_ts - timedelta(days=max(5, int(lookback_days)))
    params_norm = normalize_strategy_params(strategy_params)

    ledger = load_alert_ledger(ledger_path, account_id=account_id, db_path=db_path)
    new_rows: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []
    scanned = 0

    for raw_symbol in symbols:
        symbol = raw_symbol.strip().upper()
        if not symbol:
            continue
        scanned += 1
        data = dm.get_history(
            symbol=symbol,
            start=start_ts,
            end=end_ts,
            interval=interval,
            use_cache=True,
            incremental=True,
        )
        if data.empty:
            continue
        explain = strategy.explain(data).reindex(data.index)
        signals = explain.get("signal", strategy.generate_signals(data)).fillna(0).astype(int).clip(-1, 1)
        explain["signal"] = signals
        if "reason" not in explain.columns:
            explain["reason"] = signals.map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})

        last_ts = data.index[-1]
        last_signal = int(explain.iloc[-1]["signal"])
        side = _signal_to_side(last_signal)
        if side == "flat":
            continue
        if _has_open_same_side(
            ledger,
            symbol=symbol,
            strategy=strategy_name,
            interval=interval,
            side=side,
            strategy_params=params_norm,
        ):
            continue

        alert_row = create_alert_row(
            symbol=symbol,
            strategy=strategy_name,
            interval=interval,
            side=side,
            alert_price=float(data.iloc[-1]["close"]),
            alert_reason=str(explain.iloc[-1].get("reason", "")),
            strategy_params=strategy_params,
            created_at=last_ts.isoformat(),
            notification_sent=False,
            notification_channel="local_file",
        )
        new_rows.append(alert_row)
        if ledger.empty:
            ledger = pd.DataFrame([alert_row])
        else:
            ledger = pd.concat([ledger, pd.DataFrame([alert_row])], axis=0, ignore_index=True)
        notifications.append(
            {
                "alert_id": alert_row["alert_id"],
                "account_id": account_id,
                "created_at": alert_row["created_at"],
                "symbol": symbol,
                "strategy": strategy_name,
                "interval": interval,
                "side": side,
                "alert_price": alert_row["alert_price"],
                "alert_reason": alert_row["alert_reason"],
                "strategy_params": strategy_params or {},
            }
        )

    updated_ledger, out_ledger_path = upsert_alert_rows(
        new_rows,
        ledger_path,
        account_id=account_id,
        db_path=db_path,
    )
    notify_path = Path(notification_file) if notification_file else (OUTPUT_DIR / "signal_pilot_notifications.jsonl")
    if not notify_path.is_absolute():
        notify_path = OUTPUT_DIR / notify_path
    _append_notifications(notify_path, notifications)
    return {
        "scanned_symbols": scanned,
        "new_alerts": len(new_rows),
        "account_id": account_id,
        "ledger_path": str(out_ledger_path),
        "notification_file": str(notify_path),
        "alerts": notifications,
        "ledger_rows": len(updated_ledger),
    }


def _calc_return_series(close: pd.Series, entry_price: float, side: str) -> pd.Series:
    if side == "long":
        return close / entry_price - 1.0
    if side == "short":
        return entry_price / close - 1.0
    return pd.Series([0.0] * len(close), index=close.index, dtype=float)


def _side_to_signal(side: str) -> int:
    if side == "long":
        return 1
    if side == "short":
        return -1
    return 0


def update_alerts(
    *,
    ledger_path: str | Path | None = None,
    end: str | None = None,
    max_holding_days: int = 60,
    close_on_reverse: bool = True,
    symbols: list[str] | None = None,
    strategies: list[str] | None = None,
    account_id: str = "default",
    db_path: str | Path | None = None,
    data_manager: DataManager | None = None,
) -> dict[str, Any]:
    dm = data_manager or DataManager()
    ledger = load_alert_ledger(ledger_path, account_id=account_id, db_path=db_path)
    if ledger.empty:
        out = save_alert_ledger(ledger, ledger_path, account_id=account_id, db_path=db_path)
        return {
            "updated": 0,
            "closed": 0,
            "expired": 0,
            "open_remaining": 0,
            "ledger_path": str(out),
            "account_id": account_id,
        }
    ledger["close_time"] = ledger["close_time"].astype("object")

    end_ts = pd.Timestamp(end) if end else pd.Timestamp(datetime.now(timezone.utc))
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")

    symbol_filter = {s.strip().upper() for s in (symbols or []) if s.strip()}
    strategy_filter = {s.strip().lower() for s in (strategies or []) if s.strip()}
    updated = 0
    closed = 0
    expired = 0

    for idx, row in ledger.iterrows():
        if str(row.get("status", "")) != "open":
            continue
        symbol = str(row.get("symbol", "")).upper()
        strategy_name = str(row.get("strategy", "")).lower()
        if symbol_filter and symbol not in symbol_filter:
            continue
        if strategy_filter and strategy_name not in strategy_filter:
            continue

        created_at = _parse_iso_ts(str(row.get("created_at")))
        interval = str(row.get("interval", "1d"))
        side = str(row.get("side", "flat"))
        entry_price = float(row.get("alert_price", 0.0) or 0.0)
        if entry_price <= 0:
            continue
        if end_ts <= created_at:
            # Same timestamp means no new bar available for update.
            continue

        data = dm.get_history(
            symbol=symbol,
            start=created_at,
            end=end_ts,
            interval=interval,
            use_cache=True,
            incremental=True,
        )
        if data.empty:
            continue
        trail = data.loc[data.index >= created_at]
        if trail.empty:
            continue

        close_series = trail["close"].astype(float)
        ret = _calc_return_series(close_series, entry_price, side)
        current_price = float(close_series.iloc[-1])
        current_pct = float(ret.iloc[-1]) if not ret.empty else 0.0
        current_pnl = (current_price - entry_price) if side == "long" else (entry_price - current_price)
        mfe = float(ret.max()) if not ret.empty else 0.0
        mae = float(ret.min()) if not ret.empty else 0.0
        holding_bars = max(0, len(trail) - 1)
        holding_days = max(0.0, (trail.index[-1] - created_at).total_seconds() / 86400.0)

        ledger.at[idx, "current_price"] = current_price
        ledger.at[idx, "current_pnl"] = float(current_pnl)
        ledger.at[idx, "current_pnl_pct"] = current_pct
        ledger.at[idx, "max_favorable_excursion"] = mfe
        ledger.at[idx, "max_adverse_excursion"] = mae
        ledger.at[idx, "holding_bars"] = int(holding_bars)
        ledger.at[idx, "holding_days"] = float(holding_days)
        updated += 1

        closed_by_reverse = False
        if close_on_reverse:
            params_raw = str(row.get("strategy_params", "{}") or "{}")
            try:
                params = json.loads(params_raw)
            except json.JSONDecodeError:
                params = {}
            strategy = get_strategy(strategy_name, **params)
            explain = strategy.explain(trail).reindex(trail.index)
            signals = explain.get("signal", strategy.generate_signals(trail)).fillna(0).astype(int).clip(-1, 1)
            latest_signal = int(signals.iloc[-1]) if not signals.empty else 0
            if latest_signal != 0 and latest_signal == -_side_to_signal(side):
                closed_by_reverse = True

        if closed_by_reverse:
            ledger.at[idx, "status"] = "closed"
            ledger.at[idx, "close_time"] = trail.index[-1].isoformat()
            ledger.at[idx, "close_price"] = current_price
            ledger.at[idx, "realized_pnl"] = float(current_pnl)
            ledger.at[idx, "realized_pnl_pct"] = current_pct
            closed += 1
        elif holding_days >= float(max_holding_days):
            ledger.at[idx, "status"] = "expired"
            ledger.at[idx, "close_time"] = trail.index[-1].isoformat()
            ledger.at[idx, "close_price"] = current_price
            ledger.at[idx, "realized_pnl"] = float(current_pnl)
            ledger.at[idx, "realized_pnl_pct"] = current_pct
            expired += 1

    out_path = save_alert_ledger(ledger, ledger_path, account_id=account_id, db_path=db_path)
    open_remaining = int((ledger["status"].astype(str) == "open").sum()) if not ledger.empty else 0
    return {
        "updated": updated,
        "closed": closed,
        "expired": expired,
        "open_remaining": open_remaining,
        "ledger_path": str(out_path),
        "account_id": account_id,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return default
    return float(num)


def _parse_windows(raw_windows: list[int] | tuple[int, ...] | None) -> list[int]:
    if not raw_windows:
        return [7, 30, 60]
    windows = sorted({int(w) for w in raw_windows if int(w) > 0})
    return windows or [7, 30, 60]


def _format_alert_report_markdown(rows: pd.DataFrame, as_of: pd.Timestamp) -> str:
    lines = ["# Signal Pilot 观察报告", "", f"- as_of={as_of.isoformat()}", ""]
    if rows.empty:
        lines.append("暂无可用 alert 数据。")
        return "\n".join(lines) + "\n"
    lines.append("| 窗口(天) | 标的 | 策略 | 信号数 | 胜率 | 平均收益率 | 最大盈利 | 最大亏损 | 平均持有天数 | 平均 MFE | 平均 MAE |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in rows.sort_values(["window_days", "symbol", "strategy"]).iterrows():
        lines.append(
            f"| {int(r['window_days'])} | {r['symbol']} | {r['strategy']} | {int(r['signal_count'])} | "
            f"{float(r['win_rate']):.4f} | {float(r['avg_return_pct']):.4f} | {float(r['max_profit_pct']):.4f} | "
            f"{float(r['max_loss_pct']):.4f} | {float(r['avg_holding_days']):.2f} | "
            f"{float(r['avg_mfe']):.4f} | {float(r['avg_mae']):.4f} |"
        )
    lines.append("")
    return "\n".join(lines)


def report_alerts(
    *,
    ledger_path: str | Path | None = None,
    as_of: str | None = None,
    windows: list[int] | tuple[int, ...] | None = None,
    output_prefix: str = "signal_pilot_alert_report",
    output_dir: Path | None = None,
    account_id: str = "default",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    ledger = load_alert_ledger(ledger_path, account_id=account_id, db_path=db_path)
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(datetime.now(timezone.utc))
    if as_of_ts.tzinfo is None:
        as_of_ts = as_of_ts.tz_localize("UTC")
    else:
        as_of_ts = as_of_ts.tz_convert("UTC")
    window_list = _parse_windows(windows)
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if ledger.empty:
        rows = pd.DataFrame(
            columns=[
                "window_days",
                "symbol",
                "strategy",
                "signal_count",
                "win_rate",
                "avg_return_pct",
                "max_profit_pct",
                "max_loss_pct",
                "avg_holding_days",
                "avg_mfe",
                "avg_mae",
            ]
        )
    else:
        frame = ledger.copy()
        frame["created_at_ts"] = pd.to_datetime(frame["created_at"], utc=True, errors="coerce")
        frame = frame.dropna(subset=["created_at_ts"])
        frame["effective_return_pct"] = frame["realized_pnl_pct"]
        missing_realized = frame["effective_return_pct"].isna()
        frame.loc[missing_realized, "effective_return_pct"] = frame.loc[missing_realized, "current_pnl_pct"]
        frame["effective_return_pct"] = pd.to_numeric(frame["effective_return_pct"], errors="coerce").fillna(0.0)
        frame["holding_days"] = pd.to_numeric(frame["holding_days"], errors="coerce").fillna(0.0)
        frame["max_favorable_excursion"] = pd.to_numeric(frame["max_favorable_excursion"], errors="coerce").fillna(0.0)
        frame["max_adverse_excursion"] = pd.to_numeric(frame["max_adverse_excursion"], errors="coerce").fillna(0.0)

        report_rows: list[dict[str, Any]] = []
        for window in window_list:
            start_ts = as_of_ts - timedelta(days=window)
            subset = frame[frame["created_at_ts"] >= start_ts]
            if subset.empty:
                continue
            grouped = subset.groupby(["symbol", "strategy"], dropna=False)
            for (symbol, strategy), group in grouped:
                ret = group["effective_return_pct"].astype(float)
                report_rows.append(
                    {
                        "window_days": int(window),
                        "symbol": str(symbol),
                        "strategy": str(strategy),
                        "signal_count": int(len(group)),
                        "win_rate": float((ret > 0).mean()) if len(ret) > 0 else 0.0,
                        "avg_return_pct": float(ret.mean()) if len(ret) > 0 else 0.0,
                        "max_profit_pct": float(ret.max()) if len(ret) > 0 else 0.0,
                        "max_loss_pct": float(ret.min()) if len(ret) > 0 else 0.0,
                        "avg_holding_days": float(group["holding_days"].mean()),
                        "avg_mfe": float(group["max_favorable_excursion"].mean()),
                        "avg_mae": float(group["max_adverse_excursion"].mean()),
                    }
                )
        rows = pd.DataFrame(report_rows)

    ts = as_of_ts.strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"{output_prefix}_{ts}.csv"
    json_path = out_dir / f"{output_prefix}_{ts}.json"
    md_path = out_dir / f"{output_prefix}_{ts}.md"

    rows.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps(
            {
                "as_of": as_of_ts.isoformat(),
                "windows": window_list,
                "rows": rows.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text(_format_alert_report_markdown(rows, as_of_ts), encoding="utf-8")
    return {
        "as_of": as_of_ts.isoformat(),
        "windows": window_list,
        "row_count": int(len(rows)),
        "account_id": account_id,
        "csv_file": str(csv_path),
        "json_file": str(json_path),
        "markdown_file": str(md_path),
    }
