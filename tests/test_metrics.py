import pandas as pd

from market_signal_system.backtest.metrics import compute_max_drawdown, summarize_metrics


def test_compute_max_drawdown_negative():
    equity = pd.Series([1.0, 1.1, 0.9, 0.95])
    mdd = compute_max_drawdown(equity)
    assert mdd < 0


def test_summarize_metrics_trade_count():
    returns = pd.Series([0.0, 0.01, -0.02, 0.03])
    equity = (1 + returns).cumprod()
    metrics = summarize_metrics(returns, equity, [0.1, -0.05, 0.02])
    assert metrics["trade_count"] == 3.0


def test_summarize_metrics_with_benchmark_fields():
    returns = pd.Series([0.0, 0.01, -0.005, 0.02])
    equity = (1 + returns).cumprod()
    benchmark_returns = pd.Series([0.0, 0.005, -0.002, 0.01])
    benchmark_equity = (1 + benchmark_returns).cumprod()

    metrics = summarize_metrics(
        returns,
        equity,
        [0.03, -0.01],
        benchmark_returns=benchmark_returns,
        benchmark_equity_curve=benchmark_equity,
    )

    assert "benchmark_total_return" in metrics
    assert "excess_total_return" in metrics
    assert "information_ratio" in metrics
