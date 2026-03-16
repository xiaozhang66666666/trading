from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from market_signal_system.appdb.models import Account, AccountCredential, SignalAlertView, WebSession
from market_signal_system.appdb.repositories import AuthRepository, SignalPilotRepository


@dataclass(frozen=True)
class PostgresConnectionFactory:
    """Placeholder connection config for future PostgreSQL migration."""

    dsn: str

    def connect(self) -> Any:
        raise NotImplementedError("PostgreSQL backend is not implemented yet. Please use SQLite backend for now.")


class PostgresSchemaManager:
    """Placeholder schema manager for PostgreSQL."""

    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self.factory = factory

    def ensure_schema(self) -> None:
        raise NotImplementedError("PostgreSQL schema migration is not implemented yet.")


class _PostgresNotImplementedMixin:
    @staticmethod
    def _raise() -> None:
        raise NotImplementedError("PostgreSQL repository is not implemented yet.")


class PostgresAuthRepository(_PostgresNotImplementedMixin, AuthRepository):
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self.factory = factory

    def upsert_account(self, *, account_id: str, username: str, display_name: str, is_active: bool = True) -> Account:
        self._raise()

    def get_account_by_username(self, username: str) -> Account | None:
        self._raise()

    def get_account_by_id(self, account_id: str) -> Account | None:
        self._raise()

    def upsert_credential(self, *, account_id: str, password_hash: str, password_algo: str) -> AccountCredential:
        self._raise()

    def get_credential(self, account_id: str) -> AccountCredential | None:
        self._raise()

    def create_session(
        self,
        *,
        session_id: str,
        account_id: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_addr: str | None,
    ) -> WebSession:
        self._raise()

    def get_session(self, session_id: str) -> WebSession | None:
        self._raise()

    def touch_session(self, session_id: str, *, expires_at: datetime | None = None) -> None:
        self._raise()

    def delete_session(self, session_id: str) -> None:
        self._raise()

    def delete_expired_sessions(self, now: datetime) -> int:
        self._raise()


class PostgresSignalPilotRepository(_PostgresNotImplementedMixin, SignalPilotRepository):
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self.factory = factory

    def list_signal_alerts(
        self,
        *,
        account_id: str,
        limit: int = 200,
        status: str | None = None,
    ) -> list[SignalAlertView]:
        self._raise()

    def count_alert_status(self, *, account_id: str) -> dict[str, int]:
        self._raise()
