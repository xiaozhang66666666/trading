"""SQLite storage backend for multi-account isolation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.utils.paths import STATE_DIR, ensure_runtime_dirs

DEFAULT_DB_FILE = "market_signal_system.db"
DEFAULT_ACCOUNT_ID = "default"
ALERT_TABLE_COLUMNS = [
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


def normalize_account_id(account_id: str | None) -> str:
    value = str(account_id or DEFAULT_ACCOUNT_ID).strip()
    return value or DEFAULT_ACCOUNT_ID


def normalize_db_path(db_path: str | Path | None = None) -> Path:
    ensure_runtime_dirs()
    if db_path is None:
        return STATE_DIR / DEFAULT_DB_FILE
    path = Path(db_path)
    if path.is_absolute():
        return path
    return STATE_DIR / path


class SQLiteStore:
    """Small repository wrapper for project-level SQLite persistence."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = normalize_db_path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    namespace TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    meta_json TEXT
                );

                CREATE TABLE IF NOT EXISTS signal_alerts (
                    account_id TEXT NOT NULL,
                    alert_id TEXT NOT NULL,
                    created_at TEXT,
                    symbol TEXT,
                    strategy TEXT,
                    strategy_params TEXT,
                    interval TEXT,
                    side TEXT,
                    alert_price REAL,
                    alert_reason TEXT,
                    status TEXT,
                    close_time TEXT,
                    close_price REAL,
                    realized_pnl REAL,
                    realized_pnl_pct REAL,
                    current_price REAL,
                    current_pnl REAL,
                    current_pnl_pct REAL,
                    max_favorable_excursion REAL,
                    max_adverse_excursion REAL,
                    holding_bars INTEGER,
                    holding_days REAL,
                    notification_sent INTEGER,
                    notification_channel TEXT,
                    notification_last_attempt_at TEXT,
                    notification_last_sent_at TEXT,
                    notification_fail_count INTEGER,
                    PRIMARY KEY (account_id, alert_id),
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_signal_alerts_account_status
                ON signal_alerts(account_id, status);

                CREATE INDEX IF NOT EXISTS idx_signal_alerts_account_created
                ON signal_alerts(account_id, created_at);

                CREATE TABLE IF NOT EXISTS notification_dispatch_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    alert_id TEXT,
                    event_time TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_type TEXT,
                    error_message TEXT,
                    used_retry INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_dispatch_records_account_time
                ON notification_dispatch_records(account_id, event_time);

                CREATE TABLE IF NOT EXISTS sim_state_meta (
                    account_id TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    state_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    meta_json TEXT,
                    PRIMARY KEY (account_id, state_key),
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );
                """
            )

    def ensure_account(self, account_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        aid = normalize_account_id(account_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts(account_id, created_at, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (aid, now, now),
            )

    def list_signal_alerts(self, account_id: str) -> pd.DataFrame:
        aid = normalize_account_id(account_id)
        self.ensure_account(aid)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    alert_id, created_at, symbol, strategy, strategy_params, interval, side, alert_price, alert_reason,
                    status, close_time, close_price, realized_pnl, realized_pnl_pct, current_price, current_pnl,
                    current_pnl_pct, max_favorable_excursion, max_adverse_excursion, holding_bars, holding_days,
                    notification_sent, notification_channel, notification_last_attempt_at, notification_last_sent_at,
                    notification_fail_count
                FROM signal_alerts
                WHERE account_id = ?
                ORDER BY created_at, alert_id
                """,
                (aid,),
            ).fetchall()
        if not rows:
            return pd.DataFrame(columns=ALERT_TABLE_COLUMNS)
        frame = pd.DataFrame([dict(row) for row in rows], columns=ALERT_TABLE_COLUMNS)
        frame["notification_sent"] = frame["notification_sent"].map(lambda x: bool(int(x)) if pd.notna(x) else False)
        return frame

    def upsert_signal_alerts(self, account_id: str, rows: list[dict[str, Any]]) -> None:
        aid = normalize_account_id(account_id)
        self.ensure_account(aid)
        if not rows:
            return
        payloads: list[tuple[Any, ...]] = []
        for row in rows:
            payloads.append(
                (
                    aid,
                    row.get("alert_id"),
                    row.get("created_at"),
                    row.get("symbol"),
                    row.get("strategy"),
                    row.get("strategy_params"),
                    row.get("interval"),
                    row.get("side"),
                    row.get("alert_price"),
                    row.get("alert_reason"),
                    row.get("status"),
                    row.get("close_time"),
                    row.get("close_price"),
                    row.get("realized_pnl"),
                    row.get("realized_pnl_pct"),
                    row.get("current_price"),
                    row.get("current_pnl"),
                    row.get("current_pnl_pct"),
                    row.get("max_favorable_excursion"),
                    row.get("max_adverse_excursion"),
                    row.get("holding_bars"),
                    row.get("holding_days"),
                    1 if bool(row.get("notification_sent", False)) else 0,
                    row.get("notification_channel"),
                    row.get("notification_last_attempt_at"),
                    row.get("notification_last_sent_at"),
                    row.get("notification_fail_count", 0),
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signal_alerts(
                    account_id, alert_id, created_at, symbol, strategy, strategy_params, interval, side, alert_price, alert_reason,
                    status, close_time, close_price, realized_pnl, realized_pnl_pct, current_price, current_pnl, current_pnl_pct,
                    max_favorable_excursion, max_adverse_excursion, holding_bars, holding_days, notification_sent, notification_channel,
                    notification_last_attempt_at, notification_last_sent_at, notification_fail_count
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, alert_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    symbol=excluded.symbol,
                    strategy=excluded.strategy,
                    strategy_params=excluded.strategy_params,
                    interval=excluded.interval,
                    side=excluded.side,
                    alert_price=excluded.alert_price,
                    alert_reason=excluded.alert_reason,
                    status=excluded.status,
                    close_time=excluded.close_time,
                    close_price=excluded.close_price,
                    realized_pnl=excluded.realized_pnl,
                    realized_pnl_pct=excluded.realized_pnl_pct,
                    current_price=excluded.current_price,
                    current_pnl=excluded.current_pnl,
                    current_pnl_pct=excluded.current_pnl_pct,
                    max_favorable_excursion=excluded.max_favorable_excursion,
                    max_adverse_excursion=excluded.max_adverse_excursion,
                    holding_bars=excluded.holding_bars,
                    holding_days=excluded.holding_days,
                    notification_sent=excluded.notification_sent,
                    notification_channel=excluded.notification_channel,
                    notification_last_attempt_at=excluded.notification_last_attempt_at,
                    notification_last_sent_at=excluded.notification_last_sent_at,
                    notification_fail_count=excluded.notification_fail_count
                """,
                payloads,
            )

    def append_dispatch_records(self, account_id: str, rows: list[dict[str, Any]]) -> None:
        aid = normalize_account_id(account_id)
        self.ensure_account(aid)
        if not rows:
            return
        now = datetime.now(timezone.utc).isoformat()
        payloads: list[tuple[Any, ...]] = []
        for row in rows:
            payloads.append(
                (
                    aid,
                    row.get("alert_id"),
                    row.get("event_time", now),
                    row.get("channel", "unknown"),
                    row.get("status", "unknown"),
                    row.get("error_type"),
                    row.get("error_message"),
                    1 if bool(row.get("used_retry", False)) else 0,
                    int(row.get("retry_count", 0) or 0),
                    json.dumps(row.get("payload", {}), ensure_ascii=False),
                    now,
                )
            )
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO notification_dispatch_records(
                    account_id, alert_id, event_time, channel, status, error_type, error_message, used_retry, retry_count,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )

    def list_dispatch_records(
        self,
        account_id: str,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> pd.DataFrame:
        aid = normalize_account_id(account_id)
        self.ensure_account(aid)
        where = ["account_id = ?"]
        params: list[Any] = [aid]
        if start_time:
            where.append("event_time >= ?")
            params.append(start_time)
        if end_time:
            where.append("event_time <= ?")
            params.append(end_time)
        where_sql = " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT alert_id, event_time, channel, status, error_type, error_message, used_retry, retry_count, payload_json
                FROM notification_dispatch_records
                WHERE {where_sql}
                ORDER BY event_time ASC, id ASC
                """,
                params,
            ).fetchall()
        if not rows:
            return pd.DataFrame(
                columns=[
                    "alert_id",
                    "event_time",
                    "channel",
                    "status",
                    "error_type",
                    "error_message",
                    "used_retry",
                    "retry_count",
                    "payload_json",
                ]
            )
        frame = pd.DataFrame([dict(row) for row in rows])
        frame["used_retry"] = frame["used_retry"].map(lambda x: bool(int(x)) if pd.notna(x) else False).astype(bool)
        frame["retry_count"] = pd.to_numeric(frame["retry_count"], errors="coerce").fillna(0).astype(int)
        return frame

    def upsert_sim_state_meta(
        self,
        *,
        account_id: str,
        state_key: str,
        state_path: str,
        backend: str = "json_file",
        meta: dict[str, Any] | None = None,
    ) -> None:
        aid = normalize_account_id(account_id)
        self.ensure_account(aid)
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sim_state_meta(account_id, state_key, backend, state_path, updated_at, meta_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, state_key) DO UPDATE SET
                    backend=excluded.backend,
                    state_path=excluded.state_path,
                    updated_at=excluded.updated_at,
                    meta_json=excluded.meta_json
                """,
                (aid, state_key, backend, state_path, now, meta_json),
            )
