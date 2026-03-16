"""Research utilities for parameter search and walk-forward validation."""

from market_signal_system.research.walk_forward import (
    default_param_grid,
    run_grid_search,
    run_walk_forward,
)
from market_signal_system.research.compare import build_leaderboard, build_symbol_leaderboard
from market_signal_system.research.baseline_summary import build_baseline_daily_summary
from market_signal_system.research.portfolio import (
    run_equal_weight_portfolio,
    run_portfolio_backtest,
    run_portfolio_backtest_detailed,
)
from market_signal_system.research.reporting import build_report_index, export_champion_switch_trend_csv
from market_signal_system.research.stability import analyze_walk_forward_stability
from market_signal_system.research.preset_compare import compare_presets

__all__ = [
    "default_param_grid",
    "run_grid_search",
    "run_walk_forward",
    "build_leaderboard",
    "build_symbol_leaderboard",
    "build_baseline_daily_summary",
    "run_equal_weight_portfolio",
    "run_portfolio_backtest",
    "run_portfolio_backtest_detailed",
    "build_report_index",
    "export_champion_switch_trend_csv",
    "analyze_walk_forward_stability",
    "compare_presets",
]
