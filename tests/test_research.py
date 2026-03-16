import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.research.walk_forward import run_grid_search, run_walk_forward


def build_df(n: int = 1200) -> pd.DataFrame:
    idx = pd.date_range("2018-01-01", periods=n, freq="D", tz="UTC")
    base = pd.Series(range(200, 200 + n), index=idx, dtype=float)
    wave = (pd.Series(range(n), index=idx) % 50).astype(float) * 0.3
    close = base + wave
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


def test_run_grid_search_outputs_ranked_report():
    data = build_df()
    engine = BacktestEngine()
    report = run_grid_search(
        data=data,
        strategy_name="ma_cross",
        symbol="QQQ",
        engine=engine,
        param_grid={"fast_window": [30, 40], "slow_window": [120, 180]},
        objective="sharpe",
    )
    assert not report.empty
    assert "params" in report.columns
    assert report.iloc[0]["sharpe"] >= report.iloc[-1]["sharpe"]


def test_run_walk_forward_returns_summary_and_detail():
    data = build_df()
    engine = BacktestEngine()
    summary, detail = run_walk_forward(
        data=data,
        strategy_name="donchian",
        symbol="QQQ",
        engine=engine,
        param_grid={"lookback": [40, 55], "exit_lookback": [15, 20]},
        train_bars=504,
        test_bars=126,
        step_bars=126,
    )
    assert "avg_test_sharpe" in summary
    assert summary["window_count"] >= 1
    assert not detail.empty
    assert "selected_params" in detail.columns
