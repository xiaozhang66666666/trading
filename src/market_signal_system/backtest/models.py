"""Domain models for backtesting."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    fee_rate: float = 0.0008
    slippage_bps: float = 5.0
    bars_per_year: int = 252
    max_drawdown: float | None = None
    cooldown_bars: int = 20


@dataclass(frozen=True)
class TradeRecord:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int
    entry_price: float
    exit_price: float
    pnl: float


@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series
    signals: pd.Series
    signal_explain: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float]
