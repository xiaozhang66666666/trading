from __future__ import annotations

from datetime import datetime
from typing import Protocol

from market_signal_system.appdb.models import Account, AccountCredential, SignalAlertView, WebSession


class AuthRepository(Protocol):
    def upsert_account(self, *, account_id: str, username: str, display_name: str, is_active: bool = True) -> Account:
        ...

    def get_account_by_username(self, username: str) -> Account | None:
        ...

    def get_account_by_id(self, account_id: str) -> Account | None:
        ...

    def upsert_credential(self, *, account_id: str, password_hash: str, password_algo: str) -> AccountCredential:
        ...

    def get_credential(self, account_id: str) -> AccountCredential | None:
        ...

    def create_session(
        self,
        *,
        session_id: str,
        account_id: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_addr: str | None,
    ) -> WebSession:
        ...

    def get_session(self, session_id: str) -> WebSession | None:
        ...

    def touch_session(self, session_id: str, *, expires_at: datetime | None = None) -> None:
        ...

    def delete_session(self, session_id: str) -> None:
        ...

    def delete_expired_sessions(self, now: datetime) -> int:
        ...


class SignalPilotRepository(Protocol):
    def list_signal_alerts(
        self,
        *,
        account_id: str,
        limit: int = 200,
        status: str | None = None,
    ) -> list[SignalAlertView]:
        ...

    def count_alert_status(self, *, account_id: str) -> dict[str, int]:
        ...
