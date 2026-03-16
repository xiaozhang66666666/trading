import json

from market_signal_system.signal_pilot.ledger import (
    ALERT_LEDGER_COLUMNS,
    create_alert_row,
    ensure_alert_ledger,
    load_alert_ledger,
    save_alert_ledger,
    upsert_alert_rows,
)


def test_alert_ledger_create_and_load_empty(tmp_path):
    ledger_path = ensure_alert_ledger(tmp_path / "alerts.csv")
    assert ledger_path.exists()
    df = load_alert_ledger(ledger_path)
    assert list(df.columns) == ALERT_LEDGER_COLUMNS
    assert df.empty


def test_alert_ledger_upsert_and_persist(tmp_path):
    ledger_path = tmp_path / "alerts.csv"
    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=500.0,
        alert_reason="trend_up",
        strategy_params={"lookback": 120},
        alert_id="a1",
        created_at="2026-03-16T00:00:00+00:00",
    )
    df, out_path = upsert_alert_rows([row], ledger_path)
    assert out_path.exists()
    assert len(df) == 1
    assert df.iloc[0]["alert_id"] == "a1"
    assert df.iloc[0]["symbol"] == "QQQ"
    assert json.loads(df.iloc[0]["strategy_params"]) == {"lookback": 120}

    row_update = row.copy()
    row_update["status"] = "closed"
    row_update["realized_pnl_pct"] = 0.05
    df2, _ = upsert_alert_rows([row_update], ledger_path)
    assert len(df2) == 1
    assert df2.iloc[0]["status"] == "closed"
    assert float(df2.iloc[0]["realized_pnl_pct"]) == 0.05

    save_alert_ledger(df2, ledger_path)
    loaded = load_alert_ledger(ledger_path)
    assert len(loaded) == 1
    assert loaded.iloc[0]["notification_sent"] in (False, 0)


def test_alert_ledger_isolated_by_account_id(tmp_path):
    ledger_path = tmp_path / "alerts.csv"
    row_a = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=500.0,
        alert_reason="trend_up",
        strategy_params={},
        alert_id="shared",
        created_at="2026-03-16T00:00:00+00:00",
    )
    row_b = create_alert_row(
        symbol="ETH",
        strategy="score_regime",
        interval="1d",
        side="short",
        alert_price=2500.0,
        alert_reason="trend_down",
        strategy_params={},
        alert_id="shared",
        created_at="2026-03-16T00:00:00+00:00",
    )

    upsert_alert_rows([row_a], ledger_path, account_id="acct_a")
    upsert_alert_rows([row_b], ledger_path, account_id="acct_b")

    a = load_alert_ledger(ledger_path, account_id="acct_a")
    b = load_alert_ledger(ledger_path, account_id="acct_b")
    assert len(a) == 1 and len(b) == 1
    assert a.iloc[0]["symbol"] == "QQQ"
    assert b.iloc[0]["symbol"] == "ETH"
