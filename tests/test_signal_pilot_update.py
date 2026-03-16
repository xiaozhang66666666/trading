import pandas as pd

from market_signal_system.signal_pilot.ledger import create_alert_row, save_alert_ledger
from market_signal_system.signal_pilot.pilot import update_alerts


class _FakeDM:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_history(self, **kwargs) -> pd.DataFrame:  # noqa: ANN003
        return self._frame


class _ShortStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        sig = pd.Series([0] * (len(data) - 1) + [-1], index=data.index)
        return pd.DataFrame({"signal": sig, "reason": ["flat"] * (len(data) - 1) + ["reverse_short"]}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.explain(data)["signal"]


class _HoldStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        sig = pd.Series([1] * len(data), index=data.index)
        return pd.DataFrame({"signal": sig, "reason": ["hold_long"] * len(data)}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.explain(data)["signal"]


class _NeverCallDM:
    def get_history(self, **kwargs) -> pd.DataFrame:  # noqa: ANN003
        raise AssertionError("get_history should not be called when end <= created_at")


def test_update_alerts_close_on_reverse_signal(tmp_path, monkeypatch):
    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="long_breakout",
        strategy_params={"x": 1},
        created_at="2026-03-01T00:00:00+00:00",
        alert_id="a1",
    )
    ledger_path = tmp_path / "alerts.csv"
    save_alert_ledger(pd.DataFrame([row]), ledger_path)

    index = pd.date_range("2026-03-01", periods=4, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {"open": [100, 101, 102, 104], "high": [100, 101, 102, 104], "low": [100, 101, 102, 104], "close": [100, 101, 102, 104], "volume": [1, 1, 1, 1]},
        index=index,
    )
    monkeypatch.setattr("market_signal_system.signal_pilot.pilot.get_strategy", lambda name, **kwargs: _ShortStrategy())

    summary = update_alerts(ledger_path=ledger_path, data_manager=_FakeDM(frame), max_holding_days=60, close_on_reverse=True)
    updated = pd.read_csv(ledger_path)
    assert summary["updated"] == 1
    assert summary["closed"] == 1
    assert updated.iloc[0]["status"] == "closed"
    assert float(updated.iloc[0]["realized_pnl_pct"]) > 0


def test_update_alerts_expire_when_holding_days_exceeded(tmp_path, monkeypatch):
    row = create_alert_row(
        symbol="ETH",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=200.0,
        alert_reason="long_breakout",
        strategy_params={},
        created_at="2026-01-01T00:00:00+00:00",
        alert_id="a2",
    )
    ledger_path = tmp_path / "alerts.csv"
    save_alert_ledger(pd.DataFrame([row]), ledger_path)

    index = pd.date_range("2026-01-01", periods=70, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [200 + i for i in range(70)],
            "high": [200 + i for i in range(70)],
            "low": [200 + i for i in range(70)],
            "close": [200 + i for i in range(70)],
            "volume": [1] * 70,
        },
        index=index,
    )
    monkeypatch.setattr("market_signal_system.signal_pilot.pilot.get_strategy", lambda name, **kwargs: _HoldStrategy())

    summary = update_alerts(ledger_path=ledger_path, data_manager=_FakeDM(frame), max_holding_days=30, close_on_reverse=True)
    updated = pd.read_csv(ledger_path)
    assert summary["expired"] == 1
    assert updated.iloc[0]["status"] == "expired"
    assert float(updated.iloc[0]["holding_days"]) >= 30.0


def test_update_alerts_skips_when_end_not_after_created_at(tmp_path):
    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="long_breakout",
        strategy_params={},
        created_at="2026-03-16T00:00:00+00:00",
        alert_id="a3",
    )
    ledger_path = tmp_path / "alerts.csv"
    save_alert_ledger(pd.DataFrame([row]), ledger_path)

    summary = update_alerts(
        ledger_path=ledger_path,
        end="2026-03-16T00:00:00+00:00",
        data_manager=_NeverCallDM(),
        max_holding_days=60,
        close_on_reverse=True,
    )
    assert summary["updated"] == 0
    assert summary["closed"] == 0
    assert summary["expired"] == 0
