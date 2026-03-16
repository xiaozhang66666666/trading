from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from market_signal_system.appdb.models import Account, SignalAlertView
from market_signal_system.appdb.repositories import AuthRepository, SignalPilotRepository

_PASSWORD_ALGO = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 310000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, *, iterations: int = _PASSWORD_ITERATIONS) -> str:
    if not password:
        raise ValueError("password 不能为空")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(dk).decode("ascii")
    return f"{_PASSWORD_ALGO}${iterations}${salt_b64}${hash_b64}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_raw, salt_b64, hash_b64 = encoded.split("$", 3)
    except ValueError:
        return False
    if algo != _PASSWORD_ALGO:
        return False
    try:
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


@dataclass(frozen=True)
class LoginResult:
    session_id: str
    account: Account
    expires_at: datetime


class AuthService:
    def __init__(self, repo: AuthRepository) -> None:
        self.repo = repo

    def seed_account(self, *, account_id: str, username: str, password: str, display_name: str) -> Account:
        account = self.repo.upsert_account(
            account_id=account_id.strip(),
            username=username.strip().lower(),
            display_name=display_name.strip() or username.strip(),
            is_active=True,
        )
        encoded = hash_password(password)
        self.repo.upsert_credential(account_id=account.account_id, password_hash=encoded, password_algo=_PASSWORD_ALGO)
        return account

    def login(
        self,
        *,
        username: str,
        password: str,
        ttl_seconds: int = 3600 * 12,
        user_agent: str | None = None,
        ip_addr: str | None = None,
    ) -> LoginResult | None:
        account = self.repo.get_account_by_username(username.strip().lower())
        if account is None or not account.is_active:
            return None
        cred = self.repo.get_credential(account.account_id)
        if cred is None:
            return None
        if not verify_password(password, cred.password_hash):
            return None

        now = _utcnow()
        expires_at = now + timedelta(seconds=max(60, int(ttl_seconds)))
        session_id = secrets.token_urlsafe(32)
        self.repo.create_session(
            session_id=session_id,
            account_id=account.account_id,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_addr=ip_addr,
        )
        return LoginResult(session_id=session_id, account=account, expires_at=expires_at)

    def get_account_by_session(self, session_id: str, *, extend_ttl_seconds: int | None = 3600 * 12) -> Account | None:
        session = self.repo.get_session(session_id)
        if session is None:
            return None
        now = _utcnow()
        self.repo.delete_expired_sessions(now)
        session = self.repo.get_session(session_id)
        if session is None or session.expires_at <= now:
            return None

        account = self.repo.get_account_by_id(session.account_id)
        if account is None or not account.is_active:
            return None

        if extend_ttl_seconds is not None:
            next_expire = now + timedelta(seconds=max(60, int(extend_ttl_seconds)))
            self.repo.touch_session(session_id, expires_at=next_expire)
        else:
            self.repo.touch_session(session_id)
        return account

    def logout(self, session_id: str) -> None:
        self.repo.delete_session(session_id)


class SignalPilotService:
    def __init__(self, repo: SignalPilotRepository) -> None:
        self.repo = repo

    def list_recent_alerts(self, *, account_id: str, limit: int = 100, status: str | None = None) -> list[SignalAlertView]:
        return self.repo.list_signal_alerts(account_id=account_id, limit=limit, status=status)

    def count_alert_status(self, *, account_id: str) -> dict[str, int]:
        return self.repo.count_alert_status(account_id=account_id)
