"""Dual-horizon momentum with regime and volatility filters."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class DualMomentumStrategy(Strategy):
    """Combine short and long horizon momentum for lower-noise trend timing."""

    def __init__(
        self,
        fast_window: int = 63,
        slow_window: int = 252,
        regime_window: int = 200,
        volatility_window: int = 21,
        fast_threshold: float = 0.02,
        slow_threshold: float = 0.06,
        volatility_quantile: float = 0.8,
    ) -> None:
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.regime_window = regime_window
        self.volatility_window = volatility_window
        self.fast_threshold = fast_threshold
        self.slow_threshold = slow_threshold
        self.volatility_quantile = volatility_quantile
        self.name = "dual_momentum"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"].astype(float)
        fast_momentum = close.pct_change(self.fast_window)
        slow_momentum = close.pct_change(self.slow_window)

        regime_ma = close.rolling(self.regime_window).mean()
        trend_up = close > regime_ma
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252.0)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(self.volatility_quantile).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (
            (fast_momentum > self.fast_threshold)
            & (slow_momentum > self.slow_threshold)
            & trend_up
            & vol_ok
        )
        short_cond = (
            (fast_momentum < -self.fast_threshold)
            & (slow_momentum < -self.slow_threshold)
            & (~trend_up)
            & vol_ok
        )
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        return pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"].astype(float)
        fast_momentum = close.pct_change(self.fast_window)
        slow_momentum = close.pct_change(self.slow_window)
        regime_ma = close.rolling(self.regime_window).mean()
        trend_up = close > regime_ma
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252.0)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(self.volatility_quantile).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (
            (fast_momentum > self.fast_threshold)
            & (slow_momentum > self.slow_threshold)
            & trend_up
            & vol_ok
        )
        short_cond = (
            (fast_momentum < -self.fast_threshold)
            & (slow_momentum < -self.slow_threshold)
            & (~trend_up)
            & vol_ok
        )
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "dual_momentum_long",
            np.where(signal_series == -1, "dual_momentum_short", "dual_momentum_filter_blocked"),
        )
        return pd.DataFrame(
            {
                "signal": signal_series,
                "fast_momentum": fast_momentum,
                "slow_momentum": slow_momentum,
                "regime_ma": regime_ma,
                "trend_up": trend_up.astype(int),
                "annualized_vol": annualized_vol,
                "vol_cap": vol_cap,
                "vol_ok": vol_ok.astype(int),
                "reason": reason,
            },
            index=data.index,
        )
