import argparse
from pathlib import Path

import pandas as pd

import market_signal_system.cli as cli
from market_signal_system.simulation.broker import PaperBroker


def _build_frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


class FakeDataManager:
    def __init__(self, store: dict[str, pd.DataFrame]) -> None:
        self.store = store

    def get_history(self, symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
        frame = self.store[symbol]
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        return frame.loc[(frame.index >= start_ts) & (frame.index <= end_ts)]


class AlwaysLongStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"signal": 1, "reason": "always_long"}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=data.index, dtype=int)


class FlipFlopStrategy:
    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        seq = [1 if i % 2 == 0 else -1 for i in range(len(data.index))]
        return pd.DataFrame({"signal": seq, "reason": "flip_flop"}, index=data.index)

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return self.explain(data)["signal"].astype(int)


def test_simulate_portfolio_drawdown_flatten_and_cooldown(monkeypatch, tmp_path):
    dm = FakeDataManager(
        {
            "QQQ": _build_frame([100, 100, 40, 42]),
            "ETH": _build_frame([200, 200, 80, 82]),
        }
    )
    broker = PaperBroker(state_file="unit_portfolio_risk.json", initial_cash=100000.0, fee_rate=0.0, slippage_bps=0.0)
    broker.state_path = tmp_path / "unit_portfolio_risk.json"

    monkeypatch.setattr(cli, "DataManager", lambda: dm)
    monkeypatch.setattr(cli, "get_strategy", lambda *args, **kwargs: AlwaysLongStrategy())
    monkeypatch.setattr(cli, "create_broker", lambda *args, **kwargs: broker)
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path)

    args = argparse.Namespace(
        symbols="QQQ,ETH",
        strategy="momentum",
        params=None,
        start="2024-01-01",
        end="2024-01-04",
        interval="1d",
        state_file="unit_portfolio_risk.json",
        allocation_per_signal=0.3,
        max_symbol_allocation=0.4,
        max_total_allocation=1.0,
        initial_margin_rate=1.0,
        cash_reserve_ratio=0.05,
        max_portfolio_drawdown=0.2,
        risk_cooldown_bars=2,
    )
    cli.cmd_simulate_portfolio(args)

    signal_file = Path(tmp_path) / "sim_portfolio_signals_QQQ_ETH_momentum.csv"
    signals = pd.read_csv(signal_file)
    assert signals["reason"].str.contains("risk_drawdown_flatten", regex=False).any()
    assert signals["reason"].str.contains("risk_cooldown_block", regex=False).any()
    capital_file = Path(tmp_path) / "sim_portfolio_capital_QQQ_ETH_momentum.csv"
    capital = pd.read_csv(capital_file)
    assert {"used_margin", "available_margin", "reserve_cash", "gross_exposure_ratio"}.issubset(capital.columns)
    assert broker.snapshot()["trade_count"] >= 2


def test_simulate_portfolio_blocks_when_total_allocation_exhausted(monkeypatch, tmp_path):
    dm = FakeDataManager(
        {
            "QQQ": _build_frame([100, 101, 102, 103]),
            "ETH": _build_frame([200, 201, 202, 203]),
        }
    )
    broker = PaperBroker(
        state_file="unit_portfolio_alloc.json",
        initial_cash=100000.0,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    broker.state_path = tmp_path / "unit_portfolio_alloc.json"

    monkeypatch.setattr(cli, "DataManager", lambda: dm)
    monkeypatch.setattr(cli, "get_strategy", lambda *args, **kwargs: AlwaysLongStrategy())
    monkeypatch.setattr(cli, "create_broker", lambda *args, **kwargs: broker)
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path)

    args = argparse.Namespace(
        symbols="QQQ,ETH",
        strategy="momentum",
        params=None,
        start="2024-01-01",
        end="2024-01-04",
        interval="1d",
        state_file="unit_portfolio_alloc.json",
        allocation_per_signal=0.8,
        max_symbol_allocation=0.5,
        max_total_allocation=0.5,
        initial_margin_rate=1.0,
        cash_reserve_ratio=0.05,
        max_portfolio_drawdown=None,
        risk_cooldown_bars=0,
    )
    cli.cmd_simulate_portfolio(args)

    signal_file = Path(tmp_path) / "sim_portfolio_signals_QQQ_ETH_momentum.csv"
    signals = pd.read_csv(signal_file)
    blocked = signals[(signals["symbol"] == "ETH") & signals["reason"].str.contains("risk_notional_block", regex=False)]
    assert not blocked.empty


def test_simulate_portfolio_handles_continuous_reversal(monkeypatch, tmp_path):
    dm = FakeDataManager({"QQQ": _build_frame([100, 99, 101, 98, 102])})
    broker = PaperBroker(
        state_file="unit_portfolio_reversal.json",
        initial_cash=100000.0,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    broker.state_path = tmp_path / "unit_portfolio_reversal.json"

    monkeypatch.setattr(cli, "DataManager", lambda: dm)
    monkeypatch.setattr(cli, "get_strategy", lambda *args, **kwargs: FlipFlopStrategy())
    monkeypatch.setattr(cli, "create_broker", lambda *args, **kwargs: broker)
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path)

    args = argparse.Namespace(
        symbols="QQQ",
        strategy="momentum",
        params=None,
        start="2024-01-01",
        end="2024-01-05",
        interval="1d",
        state_file="unit_portfolio_reversal.json",
        allocation_per_signal=0.3,
        max_symbol_allocation=0.5,
        max_total_allocation=0.6,
        initial_margin_rate=1.0,
        cash_reserve_ratio=0.05,
        max_portfolio_drawdown=None,
        risk_cooldown_bars=0,
    )
    cli.cmd_simulate_portfolio(args)

    assert broker.snapshot()["trade_count"] >= 4
    signal_file = Path(tmp_path) / "sim_portfolio_signals_QQQ_momentum.csv"
    signals = pd.read_csv(signal_file)
    assert not signals["reason"].str.contains("risk_notional_block", regex=False).any()


def test_simulate_portfolio_blocks_when_margin_or_reserve_exhausted(monkeypatch, tmp_path):
    dm = FakeDataManager(
        {
            "QQQ": _build_frame([100, 101, 102]),
            "ETH": _build_frame([200, 201, 202]),
        }
    )
    broker = PaperBroker(
        state_file="unit_portfolio_margin.json",
        initial_cash=100000.0,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    broker.state_path = tmp_path / "unit_portfolio_margin.json"

    monkeypatch.setattr(cli, "DataManager", lambda: dm)
    monkeypatch.setattr(cli, "get_strategy", lambda *args, **kwargs: AlwaysLongStrategy())
    monkeypatch.setattr(cli, "create_broker", lambda *args, **kwargs: broker)
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path)

    args = argparse.Namespace(
        symbols="QQQ,ETH",
        strategy="momentum",
        params=None,
        start="2024-01-01",
        end="2024-01-03",
        interval="1d",
        state_file="unit_portfolio_margin.json",
        allocation_per_signal=0.7,
        max_symbol_allocation=0.8,
        max_total_allocation=2.0,
        initial_margin_rate=1.0,
        cash_reserve_ratio=0.4,
        max_portfolio_drawdown=None,
        risk_cooldown_bars=0,
    )
    cli.cmd_simulate_portfolio(args)

    signal_file = Path(tmp_path) / "sim_portfolio_signals_QQQ_ETH_momentum.csv"
    signals = pd.read_csv(signal_file)
    blocked = signals[(signals["symbol"] == "ETH") & signals["reason"].str.contains("risk_margin_block", regex=False)]
    assert not blocked.empty
