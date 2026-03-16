from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from market_signal_system.appdb import AuthService, SQLiteAuthRepository, SQLiteConnectionFactory, SQLiteSchemaManager
from market_signal_system.storage import SQLiteStore
from market_signal_system.web.app import create_app


def _fetch_csrf_token(client: TestClient) -> str:
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 200
    token = client.cookies.get("mss_csrf")
    assert token
    return str(token)


def _seed_account(db_path, account_id: str, username: str, password: str) -> None:
    factory = SQLiteConnectionFactory(db_path)
    SQLiteSchemaManager(factory).ensure_schema()
    svc = AuthService(SQLiteAuthRepository(factory))
    svc.seed_account(account_id=account_id, username=username, password=password, display_name=username)


def _seed_alert(db_path, account_id: str, symbol: str) -> None:
    store = SQLiteStore(db_path)
    store.upsert_signal_alerts(
        account_id,
        [
            {
                "alert_id": f"{account_id}-{symbol}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "strategy": "trend",
                "strategy_params": "{}",
                "interval": "1d",
                "side": "long",
                "alert_price": 100.0,
                "alert_reason": "test",
                "status": "open",
                "close_time": None,
                "close_price": None,
                "realized_pnl": None,
                "realized_pnl_pct": None,
                "current_price": 101.0,
                "current_pnl": 1.0,
                "current_pnl_pct": 0.01,
                "max_favorable_excursion": 0.02,
                "max_adverse_excursion": -0.01,
                "holding_bars": 1,
                "holding_days": 1.0,
                "notification_sent": False,
                "notification_channel": "local",
                "notification_last_attempt_at": None,
                "notification_last_sent_at": None,
                "notification_fail_count": 0,
            }
        ],
    )


def test_web_login_and_account_scope(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    _seed_account(db_path, "acct_a", "alice", "alice123456")
    _seed_account(db_path, "acct_b", "bob", "bob123456")
    _seed_alert(db_path, "acct_a", "QQQ")
    _seed_alert(db_path, "acct_b", "ETH")

    app = create_app(db_path=db_path)
    client = TestClient(app)

    csrf_a = _fetch_csrf_token(client)
    resp_login_a = client.post(
        "/login",
        data={"username": "alice", "password": "alice123456", "csrf_token": csrf_a},
        follow_redirects=True,
    )
    assert resp_login_a.status_code == 200
    assert "QQQ" in resp_login_a.text
    assert "ETH" not in resp_login_a.text
    api_a = client.get("/api/signal-pilot/alerts")
    assert api_a.status_code == 200
    payload_a = api_a.json()
    assert payload_a["account_id"] == "acct_a"
    assert len(payload_a["alerts"]) == 1
    assert payload_a["alerts"][0]["symbol"] == "QQQ"
    assert payload_a["status_counts"]["open"] == 1

    resp_logout = client.post("/logout", data={"csrf_token": csrf_a}, follow_redirects=False)
    assert resp_logout.status_code == 302

    csrf_b = _fetch_csrf_token(client)
    resp_login_b = client.post(
        "/login",
        data={"username": "bob", "password": "bob123456", "csrf_token": csrf_b},
        follow_redirects=True,
    )
    assert resp_login_b.status_code == 200
    assert "ETH" in resp_login_b.text
    assert "QQQ" not in resp_login_b.text
    api_b = client.get("/api/signal-pilot/alerts")
    assert api_b.status_code == 200
    payload_b = api_b.json()
    assert payload_b["account_id"] == "acct_b"
    assert len(payload_b["alerts"]) == 1
    assert payload_b["alerts"][0]["symbol"] == "ETH"


def test_web_requires_login(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    _seed_account(db_path, "acct_a", "alice", "alice123456")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    resp = client.get("/signal-pilot", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"
    api_resp = client.get("/api/me")
    assert api_resp.status_code == 401


def test_web_baseline_summary_api_is_account_scoped(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    _seed_account(db_path, "default", "alice", "alice123456")
    _seed_account(db_path, "prod", "bob", "bob123456")

    (output_dir / "baseline_daily_digest.default.json").write_text(
        json.dumps({"account_id": "default", "as_of": "2026-03-16T00:00:00+00:00", "alerts": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "baseline_daily_digest.prod.json").write_text(
        json.dumps({"account_id": "prod", "as_of": "2026-03-16T00:00:00+00:00", "alerts": [{"level": "watch"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    app = create_app(db_path=db_path, output_dir=output_dir)
    client = TestClient(app)

    unauth = client.get("/api/baseline-summary/latest")
    assert unauth.status_code == 401

    csrf_default = _fetch_csrf_token(client)
    resp_login_default = client.post(
        "/login",
        data={"username": "alice", "password": "alice123456", "csrf_token": csrf_default},
        follow_redirects=True,
    )
    assert resp_login_default.status_code == 200
    api_default = client.get("/api/baseline-summary/latest")
    assert api_default.status_code == 200
    payload_default = api_default.json()
    assert payload_default["account_id"] == "default"
    assert payload_default["found"] is True
    assert payload_default["source"] == "baseline_daily_digest.default.json"
    assert payload_default["summary"]["account_id"] == "default"

    client.post("/logout", data={"csrf_token": csrf_default}, follow_redirects=False)
    csrf_prod = _fetch_csrf_token(client)
    resp_login_prod = client.post(
        "/login",
        data={"username": "bob", "password": "bob123456", "csrf_token": csrf_prod},
        follow_redirects=True,
    )
    assert resp_login_prod.status_code == 200
    api_prod = client.get("/api/baseline-summary/latest")
    assert api_prod.status_code == 200
    payload_prod = api_prod.json()
    assert payload_prod["account_id"] == "prod"
    assert payload_prod["found"] is True
    assert payload_prod["source"] == "baseline_daily_digest.prod.json"
    assert payload_prod["summary"]["account_id"] == "prod"


def test_web_login_rate_limit_blocks_after_failures(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    _seed_account(db_path, "acct_a", "alice", "alice123456")
    app = create_app(
        db_path=db_path,
        login_rate_limit_max_attempts=2,
        login_rate_limit_window_seconds=300,
    )
    client = TestClient(app)

    csrf_token = _fetch_csrf_token(client)
    first = client.post(
        "/login",
        data={"username": "alice", "password": "bad", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert first.status_code == 401
    second = client.post(
        "/login",
        data={"username": "alice", "password": "bad", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert second.status_code == 401
    third = client.post(
        "/login",
        data={"username": "alice", "password": "alice123456", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert third.status_code == 429


def test_web_login_rejects_invalid_csrf(tmp_path) -> None:
    db_path = tmp_path / "web.db"
    _seed_account(db_path, "acct_a", "alice", "alice123456")
    app = create_app(db_path=db_path)
    client = TestClient(app)

    _fetch_csrf_token(client)
    bad = client.post(
        "/login",
        data={"username": "alice", "password": "alice123456", "csrf_token": "invalid"},
        follow_redirects=False,
    )
    assert bad.status_code == 400
