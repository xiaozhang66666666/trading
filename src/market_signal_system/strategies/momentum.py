"""Low-frequency momentum + volatility filter strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class MomentumVolatilityStrategy(Strategy):
    """Trade only when medium-term momentum is clear and volatility is acceptable."""

    def __init__(
        self,
        momentum_window: int = 126,
        volatility_window: int = 20,
        momentum_threshold: float = 0.08,
        volatility_cap: float = 0.6,
        lookback: int | None = None,
        vol_window: int | None = None,
        volatility_limit: float | None = None,
    ) -> None:
        # Backward compatibility for old templates.
        if lookback is not None:
            momentum_window = int(lookback)
        if vol_window is not None:
            volatility_window = int(vol_window)
        if volatility_limit is not None:
            volatility_cap = float(volatility_limit)
        self.momentum_window = momentum_window
        self.volatility_window = volatility_window
        self.momentum_threshold = momentum_threshold
        self.volatility_cap = volatility_cap
        self.name = "momentum_vol_filter"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        momentum = close.pct_change(self.momentum_window)
        vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)

        signal = np.where(
            (momentum > self.momentum_threshold) & (vol < self.volatility_cap),
            1,
            np.where(
                (momentum < -self.momentum_threshold) & (vol < self.volatility_cap),
                -1,
                0,
            ),
        )
        return pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"]
        momentum = close.pct_change(self.momentum_window)
        vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        signal = np.where(
            (momentum > self.momentum_threshold) & (vol < self.volatility_cap),
            1,
            np.where(
                (momentum < -self.momentum_threshold) & (vol < self.volatility_cap),
                -1,
                0,
            ),
        )
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "momentum_up_and_vol_ok",
            np.where(
                signal_series == -1,
                "momentum_down_and_vol_ok",
                "momentum_or_vol_filter_blocked",
            ),
        )
        return pd.DataFrame(
            {
                "signal": signal_series,
                "momentum": momentum,
                "annualized_vol": vol,
                "reason": reason,
            },
            index=data.index,
        )
