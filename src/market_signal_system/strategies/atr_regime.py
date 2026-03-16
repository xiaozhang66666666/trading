"""ATR-normalized regime strategy for medium/long horizon."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class AtrRegimeStrategy(Strategy):
    """Use ATR-normalized trend strength with volatility cap for long/short timing."""

    def __init__(
        self,
        atr_window: int = 20,
        trend_window: int = 180,
        strength_threshold: float = 1.0,
        atr_cap_quantile: float = 0.8,
    ) -> None:
        if atr_window < 5:
            raise ValueError("atr_window must be >= 5.")
        if trend_window < 60:
            raise ValueError("trend_window must be >= 60.")
        if strength_threshold <= 0:
            raise ValueError("strength_threshold must be > 0.")
        if not 0.5 <= atr_cap_quantile <= 0.99:
            raise ValueError("atr_cap_quantile must be between 0.5 and 0.99.")

        self.atr_window = atr_window
        self.trend_window = trend_window
        self.strength_threshold = strength_threshold
        self.atr_cap_quantile = atr_cap_quantile
        self.name = "atr_regime"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        explain = self.explain(data)
        return explain["signal"].astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"].astype(float)
        high = data["high"].astype(float)
        low = data["low"].astype(float)
        prev_close = close.shift(1)

        true_range = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = true_range.rolling(self.atr_window).mean()
        trend_ma = close.rolling(self.trend_window).mean()
        atr_safe = atr.replace(0.0, np.nan)
        trend_strength = (close - trend_ma) / atr_safe

        atr_ratio = atr / close.replace(0.0, np.nan)
        atr_cap = atr_ratio.rolling(self.trend_window).quantile(self.atr_cap_quantile).shift(1)
        vol_ok = atr_ratio < atr_cap

        long_cond = (trend_strength > self.strength_threshold) & (close > trend_ma) & vol_ok
        short_cond = (trend_strength < -self.strength_threshold) & (close < trend_ma) & vol_ok
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "atr_strength_long_with_vol_ok",
            np.where(
                signal_series == -1,
                "atr_strength_short_with_vol_ok",
                "atr_strength_or_vol_filter_blocked",
            ),
        )

        return pd.DataFrame(
            {
                "signal": signal_series,
                "true_range": true_range,
                "atr": atr,
                "trend_ma": trend_ma,
                "trend_strength": trend_strength,
                "atr_ratio": atr_ratio,
                "atr_cap": atr_cap,
                "vol_ok": vol_ok.astype(int),
                "reason": reason,
            },
            index=data.index,
        )
