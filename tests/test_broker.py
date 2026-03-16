import argparse
import json

import pandas as pd

from market_signal_system import cli
from market_signal_system.simulation.broker import PaperBroker


def test_broker_open_close_cycle(tmp_path):
    broker = PaperBroker(state_file="test_broker.json", initial_cash=1000)
    broker.state_path = tmp_path / "test_broker.json"

    broker.process_signal("QQQ", 1, 100.0, "2026-01-01T00:00:00Z", quantity=1)
    broker.mark_to_market("QQQ", 110.0)
    assert broker.floating_pnl > 0

    broker.process_signal("QQQ", 0, 110.0, "2026-01-02T00:00:00Z", quantity=1)
    assert broker.realized_pnl != 0
    assert broker.positions == {}


def test_broker_state_persistence(tmp_path):
    broker = PaperBroker(state_file="persist_broker.json", initial_cash=1000)
    broker.state_path = tmp_path / "persist_broker.json"
    broker.process_signal("ETH", 1, 2000.0, "2026-01-01T00:00:00Z", quantity=0.1)
    broker.mark_to_market("ETH", 2100.0)
    broker.save_state()

    loaded = PaperBroker(state_file="persist_broker.json", initial_cash=1)
    loaded.state_path = broker.state_path
    loaded.load_state()
    snap = loaded.snapshot()

    assert snap["trade_count"] >= 0
    assert "total_fees" in snap
    assert "total_slippage" in snap
    assert "return_pct" in snap


def test_broker_supports_shared_account_multi_symbols(tmp_path):
    broker = PaperBroker(state_file="portfolio_broker.json", initial_cash=1000)
    broker.state_path = tmp_path / "portfolio_broker.json"

    broker.process_signal("QQQ", 1, 100.0, "2026-01-01T00:00:00Z", quantity=1.0)
    broker.process_signal("ETH", -1, 200.0, "2026-01-01T00:00:00Z", quantity=0.5)

    broker.mark_to_market("QQQ", 110.0)  # long profit
    broker.mark_to_market("ETH", 180.0)  # short profit
    assert broker.floating_pnl > 0

    broker.process_signal("QQQ", 0, 110.0, "2026-01-02T00:00:00Z", quantity=0)
    broker.process_signal("ETH", 0, 180.0, "2026-01-02T00:00:00Z", quantity=0)
    snap = broker.snapshot()

    assert snap["trade_count"] == 2
    assert snap["positions"] == {}
    assert snap["cumulative_pnl"] == snap["realized_pnl"]


def test_cmd_simulate_can_resume_from_persisted_state(tmp_path, monkeypatch):
    idx_a = pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC")
    idx_b = pd.date_range("2026-01-03", periods=2, freq="D", tz="UTC")
    df_a = pd.DataFrame(
        {
            "open": [100.0, 104.0],
            "high": [101.0, 106.0],
            "low": [99.0, 103.0],
            "close": [100.0, 105.0],
            "volume": [1000.0, 1000.0],
            "signal": [1, 1],
        },
        index=idx_a,
    )
    df_b = pd.DataFrame(
        {
            "open": [108.0, 107.0],
            "high": [109.0, 108.0],
            "low": [107.0, 106.0],
            "close": [108.0, 107.0],
            "volume": [1000.0, 1000.0],
            "signal": [1, 0],
        },
        index=idx_b,
    )

    class FakeDataManager:
        def get_history(self, symbol: str, start: str, end: str, interval: str = "1d"):  # noqa: ARG002
            return df_a if str(start).startswith("2026-01-01") else df_b

    class FakeStrategy:
        def generate_signals(self, data: pd.DataFrame) -> pd.Series:
            return data["signal"].astype(int)

        def explain(self, data: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "signal": data["signal"].astype(int),
                    "reason": ["resume_test"] * len(data),
                },
                index=data.index,
            )

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    monkeypatch.setattr(cli, "get_strategy", lambda *_args, **_kwargs: FakeStrategy())
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr("market_signal_system.simulation.broker.STATE_DIR", tmp_path / "state")
    cli.ensure_runtime_dirs()
    (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    args_first = argparse.Namespace(
        symbol="ETH",
        strategy="momentum",
        params=None,
        start="2026-01-01",
        end="2026-01-02",
        interval="1d",
        state_file="resume_state.json",
        quantity=1.0,
    )
    cli.cmd_simulate(args_first)

    args_second = argparse.Namespace(
        symbol="ETH",
        strategy="momentum",
        params=None,
        start="2026-01-03",
        end="2026-01-04",
        interval="1d",
        state_file="resume_state.json",
        quantity=1.0,
    )
    cli.cmd_simulate(args_second)

    resumed = PaperBroker(state_file="resume_state.json", initial_cash=100000.0)
    resumed.state_path = tmp_path / "state" / "resume_state.json"
    resumed.load_state()
    snap = resumed.snapshot()

    assert snap["trade_count"] == 1
    assert snap["positions"] == {}
    assert snap["realized_pnl"] != 0


def test_cmd_simulate_supports_allocation_per_signal_dynamic_quantity(tmp_path, monkeypatch):
    idx = pd.date_range("2026-02-01", periods=2, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1000.0, 1000.0],
            "signal": [1, 0],
        },
        index=idx,
    )

    class FakeDataManager:
        def get_history(self, symbol: str, start: str, end: str, interval: str = "1d"):  # noqa: ARG002
            return df

    class FakeStrategy:
        def generate_signals(self, data: pd.DataFrame) -> pd.Series:
            return data["signal"].astype(int)

        def explain(self, data: pd.DataFrame) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "signal": data["signal"].astype(int),
                    "reason": ["alloc_test"] * len(data),
                },
                index=data.index,
            )

    monkeypatch.setattr(cli, "DataManager", FakeDataManager)
    monkeypatch.setattr(cli, "get_strategy", lambda *_args, **_kwargs: FakeStrategy())
    monkeypatch.setattr(cli, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr("market_signal_system.simulation.broker.STATE_DIR", tmp_path / "state")
    cli.ensure_runtime_dirs()
    (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        symbol="QQQ",
        strategy="momentum",
        params=None,
        start="2026-02-01",
        end="2026-02-02",
        interval="1d",
        state_file="alloc_state.json",
        quantity=1.0,
        allocation_per_signal=0.1,
        min_quantity=0.0,
        summary_file=None,
    )
    cli.cmd_simulate(args)
    equity_path = tmp_path / "outputs" / "sim_equity_QQQ_momentum.csv"
    summary_path = tmp_path / "outputs" / "sim_summary_QQQ_momentum.json"
    assert equity_path.exists()
    assert summary_path.exists()
    equity = pd.read_csv(equity_path)
    assert {
        "timestamp",
        "total_equity",
        "return_pct",
        "position_side",
        "position_quantity",
        "position_entry_price",
        "position_mark_price",
        "position_unrealized_pnl",
    }.issubset(set(equity.columns))
    assert len(equity) == 2
    assert int(equity.loc[0, "position_side"]) == 1
    assert float(equity.loc[0, "position_quantity"]) == 100.0
    assert int(equity.loc[1, "position_side"]) == 0
    assert float(equity.loc[1, "position_quantity"]) == 0.0
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["symbol"] == "QQQ"
    assert summary["strategy"] == "momentum"
    assert "snapshot" in summary
    assert summary["latest_position"] is None

    resumed = PaperBroker(state_file="alloc_state.json", initial_cash=100000.0)
    resumed.state_path = tmp_path / "state" / "alloc_state.json"
    resumed.load_state()
    assert resumed.trades
    trade = resumed.trades[0]
    # 10% of 100000 at entry price 100 => quantity ~= 100
    assert trade.quantity == 100.0
