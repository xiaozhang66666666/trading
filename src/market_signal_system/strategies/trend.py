"""Trend-following strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class MovingAverageCrossStrategy(Strategy):
    """Long/short by fast-slow moving average crossover."""

    def __init__(self, fast_window: int = 50, slow_window: int = 200) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window.")
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.name = f"ma_cross_{fast_window}_{slow_window}"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        fast = close.rolling(self.fast_window).mean()
        slow = close.rolling(self.slow_window).mean()
        signal = np.where(fast > slow, 1, np.where(fast < slow, -1, 0))
        return pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"]
        fast = close.rolling(self.fast_window).mean()
        slow = close.rolling(self.slow_window).mean()
        signal = np.where(fast > slow, 1, np.where(fast < slow, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "fast_above_slow",
            np.where(signal_series == -1, "fast_below_slow", "ma_overlap_or_warmup"),
        )
        return pd.DataFrame(
            {
                "signal": signal_series,
                "fast_ma": fast,
                "slow_ma": slow,
                "ma_spread": (fast - slow),
                "reason": reason,
            },
            index=data.index,
        )
