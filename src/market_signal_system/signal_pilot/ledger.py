"""Persistent ledger helpers for signal pilot alerts."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.storage import DEFAULT_ACCOUNT_ID, SQLiteStore, normalize_account_id
from market_signal_system.utils.paths import STATE_DIR, ensure_runtime_dirs

ALERT_LEDGER_COLUMNS = [
    "alert_id",
    "created_at",
    "symbol",
    "strategy",
    "strategy_params",
    "interval",
    "side",
    "alert_price",
    "alert_reason",
    "status",
    "close_time",
    "close_price",
    "realized_pnl",
    "realized_pnl_pct",
    "current_price",
    "current_pnl",
    "current_pnl_pct",
    "max_favorable_excursion",
    "max_adverse_excursion",
    "holding_bars",
    "holding_days",
    "notification_sent",
    "notification_channel",
    "notification_last_attempt_at",
    "notification_last_sent_at",
    "notification_fail_count",
]


def _safe_account_suffix(account_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", account_id)


def _normalize_ledger_path(path: str | Path | None) -> Path:
    ensure_runtime_dirs()
    if path is None:
        return STATE_DIR / "signal_alert_ledger.csv"
    p = Path(path)
    if p.is_absolute():
        return p
    return STATE_DIR / p


def _resolve_account_ledger_path(path: str | Path | None, account_id: str) -> Path:
    base = _normalize_ledger_path(path)
    aid = normalize_account_id(account_id)
    if aid == DEFAULT_ACCOUNT_ID:
        return base
    suffix = base.suffix or ".csv"
    stem = base.stem if base.suffix else base.name
    return base.with_name(f"{stem}.{_safe_account_suffix(aid)}{suffix}")


def _resolve_effective_db_path(path: str | Path | None, db_path: str | Path | None) -> str | Path | None:
    if db_path is not None:
        return db_path
    if path is None:
        return None
    return _normalize_ledger_path(path).parent / "market_signal_system.db"


def _ensure_ledger_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    for col in ALERT_LEDGER_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    frame = frame[ALERT_LEDGER_COLUMNS]
    if not frame.empty:
        frame["notification_sent"] = frame["notification_sent"].map(
            lambda v: bool(v) if pd.notna(v) else False
        ).astype(bool)
        frame["notification_channel"] = frame["notification_channel"].astype("object")
        frame["notification_last_attempt_at"] = frame["notification_last_attempt_at"].astype("object")
        frame["notification_last_sent_at"] = frame["notification_last_sent_at"].astype("object")
        frame["notification_fail_count"] = pd.to_numeric(frame["notification_fail_count"], errors="coerce").fillna(0).astype(int)
    return frame


def ensure_alert_ledger(path: str | Path | None = None, account_id: str = DEFAULT_ACCOUNT_ID) -> Path:
    ledger_path = _resolve_account_ledger_path(path, account_id=account_id)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        pd.DataFrame(columns=ALERT_LEDGER_COLUMNS).to_csv(ledger_path, index=False)
    return ledger_path


def _load_alert_ledger_csv(path: str | Path | None, account_id: str) -> pd.DataFrame:
    ledger_path = ensure_alert_ledger(path, account_id=account_id)
    df = pd.read_csv(ledger_path)
    if df.empty:
        return pd.DataFrame(columns=ALERT_LEDGER_COLUMNS)
    return _ensure_ledger_columns(df)


def load_alert_ledger(
    path: str | Path | None = None,
    *,
    account_id: str = DEFAULT_ACCOUNT_ID,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    account = normalize_account_id(account_id)
    store = SQLiteStore(db_path=_resolve_effective_db_path(path, db_path))
    db_frame = _ensure_ledger_columns(store.list_signal_alerts(account))
    if not db_frame.empty:
        return db_frame

    # Backward compatibility: seed SQLite from legacy CSV when DB is empty.
    csv_frame = _load_alert_ledger_csv(path, account_id=account)
    if not csv_frame.empty:
        store.upsert_signal_alerts(account, csv_frame.to_dict(orient="records"))
    return csv_frame


def save_alert_ledger(
    df: pd.DataFrame,
    path: str | Path | None = None,
    *,
    account_id: str = DEFAULT_ACCOUNT_ID,
    db_path: str | Path | None = None,
) -> Path:
    account = normalize_account_id(account_id)
    normalized = _ensure_ledger_columns(df)
    store = SQLiteStore(db_path=_resolve_effective_db_path(path, db_path))
    store.upsert_signal_alerts(account, normalized.to_dict(orient="records"))
    ledger_path = ensure_alert_ledger(path, account_id=account)
    normalized.to_csv(ledger_path, index=False)
    return ledger_path


def upsert_alert_rows(
    rows: list[dict[str, Any]],
    path: str | Path | None = None,
    *,
    account_id: str = DEFAULT_ACCOUNT_ID,
    db_path: str | Path | None = None,
) -> tuple[pd.DataFrame, Path]:
    current = load_alert_ledger(path, account_id=account_id, db_path=db_path)
    if not rows:
        out = save_alert_ledger(current, path, account_id=account_id, db_path=db_path)
        return current, out
    incoming = _ensure_ledger_columns(pd.DataFrame(rows))
    if current.empty:
        merged = incoming.copy()
    else:
        merged = pd.concat([current, incoming], axis=0, ignore_index=True)
    merged = merged.drop_duplicates(subset=["alert_id"], keep="last").reset_index(drop=True)
    out = save_alert_ledger(merged, path, account_id=account_id, db_path=db_path)
    return merged, out


def normalize_strategy_params(params: dict[str, Any] | None) -> str:
    payload = params or {}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_alert_row(
    *,
    symbol: str,
    strategy: str,
    interval: str,
    side: str,
    alert_price: float,
    alert_reason: str,
    strategy_params: dict[str, Any] | None = None,
    created_at: str | None = None,
    alert_id: str | None = None,
    status: str = "open",
    notification_sent: bool = False,
    notification_channel: str | None = None,
    notification_last_attempt_at: str | None = None,
    notification_last_sent_at: str | None = None,
    notification_fail_count: int = 0,
) -> dict[str, Any]:
    ts = created_at or datetime.now(timezone.utc).isoformat()
    return {
        "alert_id": alert_id or uuid.uuid4().hex,
        "created_at": ts,
        "symbol": symbol.upper(),
        "strategy": strategy.lower(),
        "strategy_params": normalize_strategy_params(strategy_params),
        "interval": interval,
        "side": side,
        "alert_price": float(alert_price),
        "alert_reason": alert_reason,
        "status": status,
        "close_time": None,
        "close_price": None,
        "realized_pnl": None,
        "realized_pnl_pct": None,
        "current_price": None,
        "current_pnl": None,
        "current_pnl_pct": None,
        "max_favorable_excursion": None,
        "max_adverse_excursion": None,
        "holding_bars": 0,
        "holding_days": 0.0,
        "notification_sent": bool(notification_sent),
        "notification_channel": notification_channel,
        "notification_last_attempt_at": notification_last_attempt_at,
        "notification_last_sent_at": notification_last_sent_at,
        "notification_fail_count": max(0, int(notification_fail_count)),
    }
