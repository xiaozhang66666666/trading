from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Account:
    account_id: str
    username: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AccountCredential:
    account_id: str
    password_hash: str
    password_algo: str
    updated_at: datetime


@dataclass(frozen=True)
class WebSession:
    session_id: str
    account_id: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    ip_addr: str | None


@dataclass(frozen=True)
class SignalAlertView:
    account_id: str
    alert_id: str
    created_at: datetime | None
    symbol: str
    strategy: str
    side: str
    status: str
    alert_price: float | None
    current_pnl_pct: float | None
    realized_pnl_pct: float | None
    alert_reason: str
