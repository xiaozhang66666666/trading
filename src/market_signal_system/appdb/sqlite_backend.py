from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from market_signal_system.appdb.models import Account, AccountCredential, SignalAlertView, WebSession
from market_signal_system.appdb.repositories import AuthRepository, SignalPilotRepository
from market_signal_system.storage import normalize_db_path


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _parse_iso(raw: str | None) -> datetime:
    if not raw:
        return _utcnow()
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SQLiteConnectionFactory:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = normalize_db_path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


class SQLiteSchemaManager:
    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def _has_column(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(r[1]) == column for r in rows)

    def ensure_schema(self) -> None:
        with self.factory.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    username TEXT,
                    display_name TEXT,
                    namespace TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    meta_json TEXT
                );

                CREATE TABLE IF NOT EXISTS account_credentials (
                    account_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    password_algo TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS web_sessions (
                    session_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    user_agent TEXT,
                    ip_addr TEXT,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_web_sessions_expires_at
                ON web_sessions(expires_at);

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
                """
            )
            if not self._has_column(conn, "accounts", "username"):
                conn.execute("ALTER TABLE accounts ADD COLUMN username TEXT")
            if not self._has_column(conn, "accounts", "is_active"):
                conn.execute("ALTER TABLE accounts ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            conn.execute(
                "UPDATE accounts SET username = COALESCE(NULLIF(username, ''), account_id) WHERE username IS NULL OR username = ''"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username)"
            )


class SQLiteAuthRepository(AuthRepository):
    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def upsert_account(self, *, account_id: str, username: str, display_name: str, is_active: bool = True) -> Account:
        now = _utcnow()
        with self.factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts(account_id, username, display_name, is_active, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    username=excluded.username,
                    display_name=excluded.display_name,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (account_id, username, display_name, 1 if is_active else 0, _to_iso(now), _to_iso(now)),
            )
        account = self.get_account_by_id(account_id)
        if account is None:
            raise RuntimeError("upsert_account failed")
        return account

    def get_account_by_username(self, username: str) -> Account | None:
        with self.factory.connect() as conn:
            row = conn.execute(
                """
                SELECT account_id, username, display_name, is_active, created_at, updated_at
                FROM accounts
                WHERE LOWER(username) = LOWER(?)
                """,
                (username,),
            ).fetchone()
        return _row_to_account(row)

    def get_account_by_id(self, account_id: str) -> Account | None:
        with self.factory.connect() as conn:
            row = conn.execute(
                """
                SELECT account_id, username, display_name, is_active, created_at, updated_at
                FROM accounts WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
        return _row_to_account(row)

    def upsert_credential(self, *, account_id: str, password_hash: str, password_algo: str) -> AccountCredential:
        now = _utcnow()
        with self.factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_credentials(account_id, password_hash, password_algo, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    password_algo=excluded.password_algo,
                    updated_at=excluded.updated_at
                """,
                (account_id, password_hash, password_algo, _to_iso(now)),
            )
        cred = self.get_credential(account_id)
        if cred is None:
            raise RuntimeError("upsert_credential failed")
        return cred

    def get_credential(self, account_id: str) -> AccountCredential | None:
        with self.factory.connect() as conn:
            row = conn.execute(
                """
                SELECT account_id, password_hash, password_algo, updated_at
                FROM account_credentials WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return AccountCredential(
            account_id=str(row["account_id"]),
            password_hash=str(row["password_hash"]),
            password_algo=str(row["password_algo"]),
            updated_at=_parse_iso(str(row["updated_at"])),
        )

    def create_session(
        self,
        *,
        session_id: str,
        account_id: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_addr: str | None,
    ) -> WebSession:
        now = _utcnow()
        with self.factory.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO web_sessions(
                    session_id, account_id, created_at, expires_at, last_seen_at, user_agent, ip_addr
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, account_id, _to_iso(now), _to_iso(expires_at), _to_iso(now), user_agent, ip_addr),
            )
        session = self.get_session(session_id)
        if session is None:
            raise RuntimeError("create_session failed")
        return session

    def get_session(self, session_id: str) -> WebSession | None:
        with self.factory.connect() as conn:
            row = conn.execute(
                """
                SELECT session_id, account_id, created_at, expires_at, last_seen_at, user_agent, ip_addr
                FROM web_sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return WebSession(
            session_id=str(row["session_id"]),
            account_id=str(row["account_id"]),
            created_at=_parse_iso(str(row["created_at"])),
            expires_at=_parse_iso(str(row["expires_at"])),
            last_seen_at=_parse_iso(str(row["last_seen_at"])),
            user_agent=(None if row["user_agent"] is None else str(row["user_agent"])),
            ip_addr=(None if row["ip_addr"] is None else str(row["ip_addr"])),
        )

    def touch_session(self, session_id: str, *, expires_at: datetime | None = None) -> None:
        now = _utcnow()
        with self.factory.connect() as conn:
            if expires_at is None:
                conn.execute(
                    "UPDATE web_sessions SET last_seen_at = ? WHERE session_id = ?",
                    (_to_iso(now), session_id),
                )
            else:
                conn.execute(
                    "UPDATE web_sessions SET last_seen_at = ?, expires_at = ? WHERE session_id = ?",
                    (_to_iso(now), _to_iso(expires_at), session_id),
                )

    def delete_session(self, session_id: str) -> None:
        with self.factory.connect() as conn:
            conn.execute("DELETE FROM web_sessions WHERE session_id = ?", (session_id,))

    def delete_expired_sessions(self, now: datetime) -> int:
        with self.factory.connect() as conn:
            cur = conn.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (_to_iso(now),))
            return int(cur.rowcount or 0)


class SQLiteSignalPilotRepository(SignalPilotRepository):
    def __init__(self, factory: SQLiteConnectionFactory) -> None:
        self.factory = factory

    def list_signal_alerts(
        self,
        *,
        account_id: str,
        limit: int = 200,
        status: str | None = None,
    ) -> list[SignalAlertView]:
        query = (
            "SELECT account_id, alert_id, created_at, symbol, strategy, side, status, "
            "alert_price, current_pnl_pct, realized_pnl_pct, alert_reason "
            "FROM signal_alerts WHERE account_id = ?"
        )
        args: list[object] = [account_id]
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC, alert_id DESC LIMIT ?"
        args.append(max(1, int(limit)))

        with self.factory.connect() as conn:
            rows = conn.execute(query, tuple(args)).fetchall()

        alerts: list[SignalAlertView] = []
        for row in rows:
            created_raw = row["created_at"]
            alerts.append(
                SignalAlertView(
                    account_id=str(row["account_id"]),
                    alert_id=str(row["alert_id"]),
                    created_at=_parse_iso(str(created_raw)) if created_raw else None,
                    symbol=str(row["symbol"] or ""),
                    strategy=str(row["strategy"] or ""),
                    side=str(row["side"] or ""),
                    status=str(row["status"] or ""),
                    alert_price=(None if row["alert_price"] is None else float(row["alert_price"])),
                    current_pnl_pct=(None if row["current_pnl_pct"] is None else float(row["current_pnl_pct"])),
                    realized_pnl_pct=(None if row["realized_pnl_pct"] is None else float(row["realized_pnl_pct"])),
                    alert_reason=str(row["alert_reason"] or ""),
                )
            )
        return alerts

    def count_alert_status(self, *, account_id: str) -> dict[str, int]:
        with self.factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(1) AS cnt
                FROM signal_alerts
                WHERE account_id = ?
                GROUP BY status
                """,
                (account_id,),
            ).fetchall()
        out = {"open": 0, "closed": 0, "expired": 0, "other": 0}
        for row in rows:
            status = str(row["status"] or "other").strip().lower()
            count = int(row["cnt"] or 0)
            if status in out:
                out[status] += count
            else:
                out["other"] += count
        return out


def _row_to_account(row: sqlite3.Row | None) -> Account | None:
    if row is None:
        return None
    return Account(
        account_id=str(row["account_id"]),
        username=str(row["username"] or ""),
        display_name=str(row["display_name"] or row["account_id"]),
        is_active=bool(int(row["is_active"] if row["is_active"] is not None else 1)),
        created_at=_parse_iso(str(row["created_at"])),
        updated_at=_parse_iso(str(row["updated_at"])),
    )
