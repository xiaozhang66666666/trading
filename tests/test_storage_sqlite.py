import sqlite3

from market_signal_system.storage import SQLiteStore


def test_sqlite_store_upserts_alerts_per_account(tmp_path):
    store = SQLiteStore(tmp_path / "pilot.db")
    store.upsert_signal_alerts(
        "acct_a",
        [
            {
                "alert_id": "a1",
                "created_at": "2026-03-16T00:00:00+00:00",
                "symbol": "QQQ",
                "strategy": "score_regime",
                "strategy_params": "{}",
                "interval": "1d",
                "side": "long",
                "alert_price": 100.0,
                "alert_reason": "x",
                "status": "open",
                "notification_sent": False,
                "notification_fail_count": 0,
            }
        ],
    )
    store.upsert_signal_alerts(
        "acct_b",
        [
            {
                "alert_id": "a1",
                "created_at": "2026-03-16T00:00:00+00:00",
                "symbol": "ETH",
                "strategy": "score_regime",
                "strategy_params": "{}",
                "interval": "1d",
                "side": "short",
                "alert_price": 200.0,
                "alert_reason": "y",
                "status": "open",
                "notification_sent": False,
                "notification_fail_count": 0,
            }
        ],
    )

    a = store.list_signal_alerts("acct_a")
    b = store.list_signal_alerts("acct_b")
    assert len(a) == 1
    assert len(b) == 1
    assert a.iloc[0]["symbol"] == "QQQ"
    assert b.iloc[0]["symbol"] == "ETH"


def test_sqlite_store_records_dispatch_and_sim_meta(tmp_path):
    db_path = tmp_path / "pilot.db"
    store = SQLiteStore(db_path)
    store.append_dispatch_records(
        "acct_a",
        [
            {
                "alert_id": "a1",
                "event_time": "2026-03-16T00:00:00+00:00",
                "channel": "local_file",
                "status": "sent",
                "payload": {"alert_id": "a1"},
                "retry_count": 0,
            }
        ],
    )
    store.upsert_sim_state_meta(
        account_id="acct_a",
        state_key="simulate:QQQ:score_regime",
        state_path="acct_a__paper_broker.json",
        meta={"symbol": "QQQ"},
    )

    with sqlite3.connect(db_path) as conn:
        dispatch_count = conn.execute(
            "SELECT COUNT(1) FROM notification_dispatch_records WHERE account_id='acct_a'"
        ).fetchone()[0]
        sim_row = conn.execute(
            "SELECT state_path FROM sim_state_meta WHERE account_id='acct_a' AND state_key='simulate:QQQ:score_regime'"
        ).fetchone()
    assert int(dispatch_count) == 1
    assert sim_row is not None
    assert str(sim_row[0]) == "acct_a__paper_broker.json"
