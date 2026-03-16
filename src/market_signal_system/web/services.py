"""Service layer for web authentication and account-scoped signal data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from market_signal_system.persistence import (
    SessionRepository,
    SignalAlertRepository,
    User,
    UserRepository,
)
from market_signal_system.web.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    username: str
    account_id: str
    display_name: str | None


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        session_ttl_hours: int = 24,
    ) -> None:
        self.users = users
        self.sessions = sessions
        self.session_ttl_hours = max(1, int(session_ttl_hours))

    def create_or_update_user(
        self,
        *,
        username: str,
        password: str,
        account_id: str,
        display_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        return self.users.upsert_user(
            username=username,
            account_id=account_id,
            password_hash=hash_password(password),
            display_name=display_name,
            is_active=is_active,
        )

    def login(self, *, username: str, password: str) -> tuple[str, AuthContext] | None:
        user = self.users.get_by_username(username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        token = generate_session_token()
        token_hash = hash_session_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.session_ttl_hours)
        self.sessions.create_session(user_id=user.user_id, token_hash=token_hash, expires_at=expires_at)
        return token, AuthContext(
            user_id=user.user_id,
            username=user.username,
            account_id=user.account_id,
            display_name=user.display_name,
        )

    def authenticate(self, token: str | None) -> AuthContext | None:
        if not token:
            return None
        now = datetime.now(timezone.utc)
        session = self.sessions.get_active_session(hash_session_token(token), now)
        if session is None:
            return None
        user = self.users.get_by_id(session.user_id)
        if user is None or not user.is_active:
            return None
        return AuthContext(
            user_id=user.user_id,
            username=user.username,
            account_id=user.account_id,
            display_name=user.display_name,
        )

    def logout(self, token: str | None) -> None:
        if not token:
            return
        now = datetime.now(timezone.utc)
        self.sessions.revoke_session(hash_session_token(token), now)


class SignalPilotService:
    def __init__(self, alerts: SignalAlertRepository) -> None:
        self.alerts = alerts

    def get_dashboard_data(self, *, account_id: str, limit: int = 100) -> dict[str, object]:
        rows = self.alerts.list_recent_alerts(account_id=account_id, limit=limit)
        status_counts = self.alerts.count_by_status(account_id=account_id)
        serialized = [
            {
                "account_id": item.account_id,
                "alert_id": item.alert_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "symbol": item.symbol,
                "strategy": item.strategy,
                "side": item.side,
                "status": item.status,
                "alert_price": item.alert_price,
                "current_pnl_pct": item.current_pnl_pct,
                "realized_pnl_pct": item.realized_pnl_pct,
                "alert_reason": item.alert_reason,
            }
            for item in rows
        ]
        return {
            "account_id": account_id,
            "status_counts": status_counts,
            "alerts": serialized,
            "alert_count": len(serialized),
        }
