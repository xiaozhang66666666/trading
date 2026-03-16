import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.strategies.base import Strategy


class AlwaysLongStrategy(Strategy):
    name = "always_long"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=data.index, name="signal")


def build_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=16, freq="D", tz="UTC")
    close = pd.Series(
        [100, 100, 100, 100, 100, 75, 74, 73, 72, 71, 70, 69, 68, 67, 66, 65],
        index=idx,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


def test_backtest_drawdown_guard_forces_flat_after_trigger():
    data = build_df()
    result = BacktestEngine(
        fee_rate=0.0,
        slippage_bps=0.0,
        max_drawdown=0.2,
        cooldown_bars=3,
    ).run(data=data, strategy=AlwaysLongStrategy(), symbol="QQQ")

    # 大跌后会触发风控，后续至少 3 根 bar 被强制空仓。
    flat_mask = result.positions.iloc[7:11]
    assert (flat_mask == 0).all()
    assert "reason" in result.signal_explain.columns


def test_backtest_invalid_drawdown_guard_config_raises():
    data = build_df()
    engine = BacktestEngine(max_drawdown=1.2)
    try:
        engine.run(data=data, strategy=AlwaysLongStrategy(), symbol="QQQ")
    except ValueError as exc:
        assert "max_drawdown" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_backtest_includes_benchmark_comparison_metrics():
    data = build_df()
    result = BacktestEngine(fee_rate=0.0, slippage_bps=0.0).run(
        data=data,
        strategy=AlwaysLongStrategy(),
        symbol="QQQ",
    )

    assert "benchmark_total_return" in result.metrics
    assert "excess_total_return" in result.metrics
    assert abs(result.metrics["excess_total_return"]) < 1e-9
