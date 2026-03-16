"""Momentum + regime + volatility filter strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class RegimeMomentumStrategy(Strategy):
    """Use long/short momentum only when regime and volatility filters agree."""

    def __init__(
        self,
        momentum_window: int = 126,
        regime_window: int = 200,
        volatility_window: int = 63,
        momentum_threshold: float = 0.03,
    ) -> None:
        self.momentum_window = momentum_window
        self.regime_window = regime_window
        self.volatility_window = volatility_window
        self.momentum_threshold = momentum_threshold
        self.name = "regime_momentum"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        momentum = close.pct_change(self.momentum_window)

        trend_filter = close > close.rolling(self.regime_window).mean()
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(0.7).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (momentum > self.momentum_threshold) & trend_filter & vol_ok
        short_cond = (momentum < -self.momentum_threshold) & (~trend_filter) & vol_ok

        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        return pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"]
        momentum = close.pct_change(self.momentum_window)
        trend_filter = close > close.rolling(self.regime_window).mean()
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(0.7).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (momentum > self.momentum_threshold) & trend_filter & vol_ok
        short_cond = (momentum < -self.momentum_threshold) & (~trend_filter) & vol_ok
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "regime_long_with_vol_ok",
            np.where(signal_series == -1, "regime_short_with_vol_ok", "regime_or_vol_filter_blocked"),
        )
        return pd.DataFrame(
            {
                "signal": signal_series,
                "momentum": momentum,
                "trend_filter": trend_filter.astype(int),
                "annualized_vol": annualized_vol,
                "vol_cap": vol_cap,
                "vol_ok": vol_ok.astype(int),
                "reason": reason,
            },
            index=data.index,
        )
