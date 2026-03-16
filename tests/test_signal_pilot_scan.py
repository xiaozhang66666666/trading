import json

import pandas as pd

from market_signal_system.signal_pilot.pilot import scan_alerts


class _FakeDM:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_history(self, **kwargs) -> pd.DataFrame:  # noqa: ANN003
        return self._frame


class _LongStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        sig = pd.Series([0] * (len(data) - 1) + [1], index=data.index)
        return pd.DataFrame({"signal": sig, "reason": ["flat"] * (len(data) - 1) + ["long_breakout"]}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.explain(data)["signal"]


class _FlatStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        sig = pd.Series([0] * len(data), index=data.index)
        return pd.DataFrame({"signal": sig, "reason": ["flat"] * len(data)}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.explain(data)["signal"]


def test_scan_alerts_creates_new_alert_and_dedups_same_side(tmp_path, monkeypatch):
    index = pd.date_range("2026-03-01", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100, 101, 102, 103, 104],
            "volume": [1000] * 5,
        },
        index=index,
    )
    monkeypatch.setattr("market_signal_system.signal_pilot.pilot.get_strategy", lambda name, **kwargs: _LongStrategy())

    ledger_path = tmp_path / "alerts.csv"
    notification_path = tmp_path / "notify.jsonl"
    dm = _FakeDM(frame)

    first = scan_alerts(
        symbols=["QQQ"],
        strategy_name="score_regime",
        interval="1d",
        strategy_params={"a": 1},
        ledger_path=ledger_path,
        notification_file=notification_path,
        data_manager=dm,
    )
    second = scan_alerts(
        symbols=["QQQ"],
        strategy_name="score_regime",
        interval="1d",
        strategy_params={"a": 1},
        ledger_path=ledger_path,
        notification_file=notification_path,
        data_manager=dm,
    )

    assert first["new_alerts"] == 1
    assert second["new_alerts"] == 0
    lines = notification_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["symbol"] == "QQQ"
    assert payload["side"] == "long"


def test_scan_alerts_skip_flat_signal(tmp_path, monkeypatch):
    index = pd.date_range("2026-03-01", periods=3, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [10, 10, 10],
            "high": [10, 10, 10],
            "low": [10, 10, 10],
            "close": [10, 10, 10],
            "volume": [1, 1, 1],
        },
        index=index,
    )
    monkeypatch.setattr("market_signal_system.signal_pilot.pilot.get_strategy", lambda name, **kwargs: _FlatStrategy())

    summary = scan_alerts(
        symbols=["ETH"],
        strategy_name="score_regime",
        interval="1d",
        ledger_path=tmp_path / "alerts.csv",
        notification_file=tmp_path / "notify.jsonl",
        db_path=tmp_path / "pilot.db",
        data_manager=_FakeDM(frame),
    )
    assert summary["new_alerts"] == 0


def test_scan_alerts_isolated_by_account_id(tmp_path, monkeypatch):
    index = pd.date_range("2026-03-01", periods=5, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100, 101, 102, 103, 104],
            "volume": [1000] * 5,
        },
        index=index,
    )
    monkeypatch.setattr("market_signal_system.signal_pilot.pilot.get_strategy", lambda name, **kwargs: _LongStrategy())
    db_path = tmp_path / "pilot.db"
    ledger_path = tmp_path / "alerts.csv"

    first = scan_alerts(
        symbols=["QQQ"],
        strategy_name="score_regime",
        interval="1d",
        strategy_params={"a": 1},
        ledger_path=ledger_path,
        notification_file=tmp_path / "n1.jsonl",
        account_id="acct_a",
        db_path=db_path,
        data_manager=_FakeDM(frame),
    )
    second = scan_alerts(
        symbols=["QQQ"],
        strategy_name="score_regime",
        interval="1d",
        strategy_params={"a": 1},
        ledger_path=ledger_path,
        notification_file=tmp_path / "n2.jsonl",
        account_id="acct_b",
        db_path=db_path,
        data_manager=_FakeDM(frame),
    )

    assert first["new_alerts"] == 1
    assert second["new_alerts"] == 1
    assert first["account_id"] == "acct_a"
    assert second["account_id"] == "acct_b"
