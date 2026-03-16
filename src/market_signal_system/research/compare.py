"""Cross-strategy comparison and leaderboard scoring."""

from __future__ import annotations

import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.data.manager import DataManager
from market_signal_system.strategies import get_strategy


def _add_rank_score(df: pd.DataFrame, column: str, ascending: bool) -> pd.Series:
    # rank 从 1 开始，转换为 [0, 1] 分数，越大越好。
    rank = df[column].rank(method="average", ascending=ascending)
    n = len(df)
    if n <= 1:
        return pd.Series([1.0] * n, index=df.index)
    return (n - rank) / (n - 1)


def build_leaderboard(
    data_manager: DataManager,
    engine: BacktestEngine,
    symbols: list[str],
    strategies: list[str],
    start: str,
    end: str,
    interval: str = "1d",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        data = data_manager.get_history(symbol=symbol, start=start, end=end, interval=interval)
        for strategy_name in strategies:
            strategy = get_strategy(strategy_name)
            result = engine.run(data=data, strategy=strategy, symbol=symbol)
            row = {"symbol": symbol, "strategy": strategy_name}
            row.update(result.metrics)
            rows.append(row)

    report = pd.DataFrame(rows)
    if report.empty:
        return report

    report["score_sharpe"] = _add_rank_score(report, "sharpe", ascending=False)
    report["score_calmar"] = _add_rank_score(report, "calmar", ascending=False)
    report["score_return"] = _add_rank_score(report, "total_return", ascending=False)
    report["score_excess_return"] = _add_rank_score(report, "excess_total_return", ascending=False)
    report["score_drawdown"] = _add_rank_score(report, "max_drawdown", ascending=True)
    report["composite_score"] = (
        report["score_sharpe"] * 0.30
        + report["score_calmar"] * 0.20
        + report["score_return"] * 0.20
        + report["score_excess_return"] * 0.20
        + report["score_drawdown"] * 0.10
    )
    return report.sort_values(by="composite_score", ascending=False).reset_index(drop=True)


def build_symbol_leaderboard(leaderboard: pd.DataFrame) -> pd.DataFrame:
    """按 symbol 分组排序并生成组内排名，便于同资产内横向比较。"""
    if leaderboard.empty:
        return leaderboard.copy()

    grouped = (
        leaderboard.copy()
        .sort_values(
            by=["symbol", "composite_score", "score_excess_return", "score_sharpe", "strategy"],
            ascending=[True, False, False, False, True],
        )
        .reset_index(drop=True)
    )
    grouped["symbol_rank"] = grouped.groupby("symbol").cumcount() + 1
    grouped["symbol_strategy_count"] = grouped.groupby("symbol")["strategy"].transform("count").astype(int)
    return grouped
