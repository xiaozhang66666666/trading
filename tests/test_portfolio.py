import pandas as pd

from market_signal_system.research.portfolio import (
    run_equal_weight_portfolio,
    run_portfolio_backtest,
    run_portfolio_backtest_detailed,
)


def build_df(n: int = 320, offset: float = 0.0) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(range(100, 100 + n), index=idx, dtype=float) + offset
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
    def __init__(self) -> None:
        self.store = {"QQQ": build_df(offset=0.0), "ETH": build_df(offset=10.0)}

    def get_history(self, symbol: str, start: str, end: str, interval: str = "1d"):
        frame = self.store[symbol]
        return frame.loc[(frame.index >= pd.Timestamp(start, tz="UTC")) & (frame.index <= pd.Timestamp(end, tz="UTC"))]


def test_equal_weight_portfolio_outputs_metrics_and_positions():
    dm = FakeDataManager()
    metrics, equity, positions = run_equal_weight_portfolio(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="ma_cross",
        start="2020-01-01",
        end="2020-10-01",
    )
    assert not equity.empty
    assert "QQQ_position" in positions.columns
    assert "ETH_position" in positions.columns
    assert "QQQ_weight" in positions.columns
    assert "ETH_weight" in positions.columns
    assert "sharpe" in metrics
    assert "benchmark_total_return" in metrics
    assert "excess_total_return" in metrics


def test_portfolio_supports_risk_parity_and_vol_target():
    dm = FakeDataManager()
    _, _, rp = run_portfolio_backtest(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="ma_cross",
        start="2020-01-01",
        end="2020-10-01",
        allocation_mode="risk_parity",
        vol_window=15,
    )
    _, _, vt = run_portfolio_backtest(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="ma_cross",
        start="2020-01-01",
        end="2020-10-01",
        allocation_mode="vol_target",
        vol_window=15,
        target_vol=0.2,
        max_leverage=2.0,
    )
    assert rp.filter(like="_weight").abs().sum(axis=1).max() <= 1.000001
    assert vt.filter(like="_weight").abs().sum(axis=1).max() <= 2.000001


def test_portfolio_supports_covariance_modes():
    dm = FakeDataManager()
    _, _, crp = run_portfolio_backtest(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="ma_cross",
        start="2020-01-01",
        end="2020-10-01",
        allocation_mode="cov_risk_parity",
        vol_window=15,
    )
    _, _, cvt = run_portfolio_backtest(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="ma_cross",
        start="2020-01-01",
        end="2020-10-01",
        allocation_mode="cov_vol_target",
        vol_window=15,
        target_vol=0.2,
        max_leverage=2.0,
    )
    assert crp.filter(like="_weight").abs().sum(axis=1).max() <= 1.000001
    assert cvt.filter(like="_weight").abs().sum(axis=1).max() <= 2.000001


def test_portfolio_detailed_outputs_contribution_tables():
    dm = FakeDataManager()
    _, _, _, detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
    )
    assert not detail["net_contrib"].empty
    assert {"symbol", "total_contribution", "annualized_vol_contribution"}.issubset(detail["attribution"].columns)
    assert {"pair", "corr", "crowding_score", "alert_level"}.issubset(detail["alerts"].columns)
    assert "QQQ_weight" in detail["weights"].columns
    assert {"QQQ_target_weight", "QQQ_drifted_weight", "QQQ_weight_gap", "abs_weight_gap_sum", "drift_alert_level"}.issubset(
        detail["drift"].columns
    )


def test_portfolio_alert_thresholds_are_configurable():
    dm = FakeDataManager()
    _, _, _, base_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        corr_watch_threshold=0.6,
        crowding_watch_threshold=0.05,
    )
    _, _, _, strict_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        corr_watch_threshold=0.99,
        corr_high_threshold=0.995,
        crowding_watch_threshold=0.95,
        crowding_high_threshold=0.99,
    )
    assert len(base_detail["alerts"]) >= len(strict_detail["alerts"])


def test_portfolio_drift_alert_thresholds_are_configurable():
    dm = FakeDataManager()
    _, _, _, base_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        drift_watch_threshold=0.02,
        drift_high_threshold=0.04,
    )
    _, _, _, strict_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        drift_watch_threshold=0.9,
        drift_high_threshold=0.95,
    )
    base_alerts = base_detail["drift"]["drift_alert_level"].isin(["watch", "high"]).sum()
    strict_alerts = strict_detail["drift"]["drift_alert_level"].isin(["watch", "high"]).sum()
    assert base_alerts >= strict_alerts


def test_portfolio_drift_rebalance_cost_injection():
    dm = FakeDataManager()
    base_metrics, _, _, base_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        drift_watch_threshold=0.0,
        drift_high_threshold=0.0,
        rebalance_on_drift=False,
    )
    rebalance_metrics, _, _, rebalance_detail = run_portfolio_backtest_detailed(
        data_manager=dm,
        symbols=["QQQ", "ETH"],
        strategy_name="momentum",
        start="2020-01-01",
        end="2020-10-01",
        drift_watch_threshold=0.0,
        drift_high_threshold=0.0,
        rebalance_on_drift=True,
        rebalance_trigger="watch",
        rebalance_scale=1.0,
    )
    assert rebalance_metrics["drift_rebalance_event_count"] > 0
    assert rebalance_metrics["drift_rebalance_turnover_total"] > 0
    assert rebalance_metrics["drift_rebalance_cost_total"] > 0
    assert rebalance_metrics["total_return"] <= base_metrics["total_return"]
    assert "rebalance" in rebalance_detail
    assert int(rebalance_detail["rebalance"]["triggered"].sum()) > 0
    assert int(base_detail["rebalance"]["triggered"].sum()) == 0
