"""Performance metrics for strategy backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    return float(drawdown.min())


def summarize_metrics(
    returns: pd.Series,
    equity_curve: pd.Series,
    trade_pnls: list[float],
    benchmark_returns: pd.Series | None = None,
    benchmark_equity_curve: pd.Series | None = None,
    bars_per_year: int = 252,
) -> dict[str, float]:
    mean_ret = returns.mean()
    std_ret = returns.std(ddof=0)

    total_return = float(equity_curve.iloc[-1] - 1.0)
    annual_return = float((equity_curve.iloc[-1] ** (bars_per_year / max(len(returns), 1))) - 1)
    sharpe = float((mean_ret / std_ret) * np.sqrt(bars_per_year)) if std_ret > 0 else 0.0
    max_drawdown = compute_max_drawdown(equity_curve)
    calmar = float(annual_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    win_rate = float(len(wins) / len(trade_pnls)) if trade_pnls else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    profit_factor = float(sum(wins) / abs(sum(losses))) if losses else float("inf") if wins else 0.0

    metrics = {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": float(max_drawdown),
        "calmar": calmar,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "trade_count": float(len(trade_pnls)),
    }

    if benchmark_returns is not None and benchmark_equity_curve is not None:
        benchmark_returns = benchmark_returns.reindex(returns.index).fillna(0.0)
        benchmark_equity_curve = benchmark_equity_curve.reindex(equity_curve.index).ffill().bfill().fillna(1.0)
        benchmark_total_return = float(benchmark_equity_curve.iloc[-1] - 1.0)
        benchmark_annual_return = float(
            (benchmark_equity_curve.iloc[-1] ** (bars_per_year / max(len(benchmark_returns), 1))) - 1
        )
        excess_returns = (returns - benchmark_returns).rename("excess_returns")
        tracking_error = excess_returns.std(ddof=0)
        information_ratio = (
            float((excess_returns.mean() / tracking_error) * np.sqrt(bars_per_year)) if tracking_error > 0 else 0.0
        )
        active_equity = (1.0 + excess_returns).cumprod()
        metrics.update(
            {
                "benchmark_total_return": benchmark_total_return,
                "benchmark_annual_return": benchmark_annual_return,
                "excess_total_return": float(total_return - benchmark_total_return),
                "excess_annual_return": float(annual_return - benchmark_annual_return),
                "information_ratio": information_ratio,
                "active_max_drawdown": float(compute_max_drawdown(active_equity)),
            }
        )

    return metrics
