from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_signal_system.appdb import (
    AuthService,
    SQLiteAuthRepository,
    SQLiteConnectionFactory,
    SQLiteSchemaManager,
)
from market_signal_system.appdb.services import hash_password, verify_password


def test_password_hash_and_verify() -> None:
    encoded = hash_password("p@ssw0rd")
    assert verify_password("p@ssw0rd", encoded)
    assert not verify_password("bad", encoded)


def test_auth_service_login_logout(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    factory = SQLiteConnectionFactory(db_path)
    SQLiteSchemaManager(factory).ensure_schema()
    repo = SQLiteAuthRepository(factory)
    svc = AuthService(repo)

    account = svc.seed_account(
        account_id="acct_demo",
        username="demo",
        password="demo123456",
        display_name="Demo User",
    )
    assert account.username == "demo"

    bad = svc.login(username="demo", password="wrong")
    assert bad is None

    ok = svc.login(username="demo", password="demo123456", ttl_seconds=120)
    assert ok is not None
    assert ok.account.account_id == "acct_demo"

    loaded = svc.get_account_by_session(ok.session_id)
    assert loaded is not None
    assert loaded.account_id == "acct_demo"

    svc.logout(ok.session_id)
    assert svc.get_account_by_session(ok.session_id) is None


def test_delete_expired_sessions(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    factory = SQLiteConnectionFactory(db_path)
    SQLiteSchemaManager(factory).ensure_schema()
    repo = SQLiteAuthRepository(factory)
    svc = AuthService(repo)
    svc.seed_account(account_id="acct_a", username="a", password="abc12345", display_name="A")

    session = repo.create_session(
        session_id="s1",
        account_id="acct_a",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        user_agent=None,
        ip_addr=None,
    )
    assert session.session_id == "s1"
    deleted = repo.delete_expired_sessions(datetime.now(timezone.utc))
    assert deleted == 1
