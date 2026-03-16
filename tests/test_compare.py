import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.research.compare import build_leaderboard, build_symbol_leaderboard


def build_df(n: int = 600, slope: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    base = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    close = base * slope
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


class FakeDataManager:
    def __init__(self):
        self.store = {"QQQ": build_df(600, slope=1.0), "ETH": build_df(600, slope=1.2)}

    def get_history(self, symbol: str, start: str, end: str, interval: str = "1d"):
        frame = self.store[symbol]
        return frame.loc[(frame.index >= pd.Timestamp(start, tz="UTC")) & (frame.index <= pd.Timestamp(end, tz="UTC"))]


def test_build_leaderboard_has_composite_score():
    dm = FakeDataManager()
    engine = BacktestEngine()
    report = build_leaderboard(
        data_manager=dm,
        engine=engine,
        symbols=["QQQ", "ETH"],
        strategies=["ma_cross", "donchian", "momentum"],
        start="2021-01-01",
        end="2022-06-30",
    )
    assert not report.empty
    assert "composite_score" in report.columns
    assert "score_excess_return" in report.columns
    assert "excess_total_return" in report.columns
    assert report.iloc[0]["composite_score"] >= report.iloc[-1]["composite_score"]


def test_build_symbol_leaderboard_adds_group_rank():
    leaderboard = pd.DataFrame(
        [
            {"symbol": "QQQ", "strategy": "s1", "composite_score": 0.9, "score_excess_return": 0.8, "score_sharpe": 0.7},
            {"symbol": "ETH", "strategy": "s1", "composite_score": 0.5, "score_excess_return": 0.4, "score_sharpe": 0.3},
            {"symbol": "QQQ", "strategy": "s2", "composite_score": 0.7, "score_excess_return": 0.6, "score_sharpe": 0.5},
            {"symbol": "ETH", "strategy": "s2", "composite_score": 0.8, "score_excess_return": 0.9, "score_sharpe": 0.6},
        ]
    )

    grouped = build_symbol_leaderboard(leaderboard)

    assert list(grouped["symbol"]) == ["ETH", "ETH", "QQQ", "QQQ"]
    assert list(grouped[grouped["symbol"] == "ETH"]["strategy"]) == ["s2", "s1"]
    assert list(grouped[grouped["symbol"] == "QQQ"]["strategy"]) == ["s1", "s2"]
    assert list(grouped[grouped["symbol"] == "ETH"]["symbol_rank"]) == [1, 2]
    assert list(grouped[grouped["symbol"] == "QQQ"]["symbol_rank"]) == [1, 2]
    assert set(grouped["symbol_strategy_count"].tolist()) == {2}
