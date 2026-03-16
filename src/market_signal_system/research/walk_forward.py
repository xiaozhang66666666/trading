"""Parameter search and walk-forward evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.backtest.metrics import summarize_metrics
from market_signal_system.strategies import get_strategy


def _expand_grid(grid: dict[str, list[object]]) -> list[dict[str, object]]:
    if not grid:
        return [{}]
    keys = sorted(grid.keys())
    values = [grid[k] for k in keys]
    combos = []
    for row in product(*values):
        combos.append({k: v for k, v in zip(keys, row)})
    return combos


def default_param_grid(strategy_name: str) -> dict[str, list[object]]:
    key = strategy_name.lower()
    if key == "ma_cross":
        return {"fast_window": [30, 50, 80], "slow_window": [120, 180, 250]}
    if key == "donchian":
        return {"lookback": [40, 55, 80], "exit_lookback": [15, 20, 30]}
    if key == "momentum":
        return {
            "momentum_window": [84, 126, 168],
            "volatility_window": [20, 40],
            "momentum_threshold": [0.05, 0.08],
            "volatility_cap": [0.45, 0.6],
        }
    if key == "regime":
        return {
            "momentum_window": [84, 126],
            "regime_window": [150, 200],
            "volatility_window": [42, 63],
            "momentum_threshold": [0.02, 0.03, 0.05],
        }
    raise ValueError(f"Unknown strategy: {strategy_name}")


@dataclass(frozen=True)
class WindowSplit:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def _build_splits(
    index: pd.Index,
    train_bars: int,
    test_bars: int,
    step_bars: int,
) -> list[WindowSplit]:
    if train_bars < 50 or test_bars < 20:
        raise ValueError("train_bars/test_bars too small for robust walk-forward.")
    if step_bars <= 0:
        raise ValueError("step_bars must be > 0.")

    n = len(index)
    splits: list[WindowSplit] = []
    cursor = train_bars
    while cursor + test_bars <= n:
        train_slice = index[cursor - train_bars : cursor]
        test_slice = index[cursor : cursor + test_bars]
        splits.append(
            WindowSplit(
                train_start=train_slice[0],
                train_end=train_slice[-1],
                test_start=test_slice[0],
                test_end=test_slice[-1],
            )
        )
        cursor += step_bars
    return splits


def run_grid_search(
    data: pd.DataFrame,
    strategy_name: str,
    symbol: str,
    engine: BacktestEngine,
    param_grid: dict[str, list[object]] | None = None,
    objective: str = "sharpe",
) -> pd.DataFrame:
    grid = param_grid or default_param_grid(strategy_name)
    rows: list[dict[str, object]] = []
    for params in _expand_grid(grid):
        strategy = get_strategy(strategy_name, **params)
        result = engine.run(data=data, strategy=strategy, symbol=symbol)
        row = {"strategy": strategy_name, "params": params}
        row.update(result.metrics)
        rows.append(row)

    report = pd.DataFrame(rows)
    if report.empty:
        return report
    if objective not in report.columns:
        raise ValueError(f"Unknown objective: {objective}")
    return report.sort_values(by=objective, ascending=False).reset_index(drop=True)


def run_walk_forward(
    data: pd.DataFrame,
    strategy_name: str,
    symbol: str,
    engine: BacktestEngine,
    param_grid: dict[str, list[object]] | None = None,
    objective: str = "sharpe",
    train_bars: int = 504,
    test_bars: int = 126,
    step_bars: int | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    if len(data) < train_bars + test_bars:
        raise ValueError("Not enough bars for walk-forward.")

    step = step_bars or test_bars
    splits = _build_splits(data.index, train_bars=train_bars, test_bars=test_bars, step_bars=step)
    grid = param_grid or default_param_grid(strategy_name)
    all_test_returns: list[pd.Series] = []
    rows: list[dict[str, object]] = []

    for i, split in enumerate(splits, start=1):
        train = data.loc[(data.index >= split.train_start) & (data.index <= split.train_end)]
        test = data.loc[(data.index >= split.test_start) & (data.index <= split.test_end)]

        grid_report = run_grid_search(
            data=train,
            strategy_name=strategy_name,
            symbol=symbol,
            engine=engine,
            param_grid=grid,
            objective=objective,
        )
        if grid_report.empty:
            continue

        best = grid_report.iloc[0]
        params = dict(best["params"])
        strategy = get_strategy(strategy_name, **params)
        test_result = engine.run(data=test, strategy=strategy, symbol=symbol)
        all_test_returns.append(test_result.returns.rename(f"window_{i}"))

        rows.append(
            {
                "window": i,
                "train_start": split.train_start,
                "train_end": split.train_end,
                "test_start": split.test_start,
                "test_end": split.test_end,
                "selected_params": params,
                "train_objective": float(best[objective]),
                "test_sharpe": float(test_result.metrics["sharpe"]),
                "test_calmar": float(test_result.metrics["calmar"]),
                "test_total_return": float(test_result.metrics["total_return"]),
                "test_max_drawdown": float(test_result.metrics["max_drawdown"]),
                "test_trade_count": float(test_result.metrics["trade_count"]),
            }
        )

    if not rows:
        raise RuntimeError("No valid walk-forward windows produced.")

    detail = pd.DataFrame(rows)
    stitched_returns = pd.concat(all_test_returns, axis=0).sort_index()
    stitched_returns = stitched_returns[~stitched_returns.index.duplicated(keep="last")]
    stitched_equity = (1.0 + stitched_returns).cumprod()
    summary = summarize_metrics(
        returns=stitched_returns,
        equity_curve=stitched_equity,
        trade_pnls=[],
        bars_per_year=engine.config.bars_per_year,
    )
    summary["window_count"] = float(len(detail))
    summary["avg_test_sharpe"] = float(detail["test_sharpe"].mean())
    summary["avg_test_total_return"] = float(detail["test_total_return"].mean())
    summary["avg_test_max_drawdown"] = float(detail["test_max_drawdown"].mean())
    return summary, detail
