"""MACD trend-following strategy with regime and volatility filters."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class MacdRegimeStrategy(Strategy):
    """Use medium-long MACD confirmation plus regime/vol filters for long-short timing."""

    def __init__(
        self,
        fast_span: int = 24,
        slow_span: int = 52,
        signal_span: int = 18,
        regime_window: int = 200,
        volatility_window: int = 63,
        macd_ratio_threshold: float = 0.001,
    ) -> None:
        if fast_span >= slow_span:
            raise ValueError("fast_span must be smaller than slow_span.")
        if signal_span < 2:
            raise ValueError("signal_span must be >= 2.")
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.signal_span = signal_span
        self.regime_window = regime_window
        self.volatility_window = volatility_window
        self.macd_ratio_threshold = macd_ratio_threshold
        self.name = "macd_regime"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"].astype(float)
        fast_ema = close.ewm(span=self.fast_span, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow_span, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=self.signal_span, adjust=False).mean()
        macd_ratio = (macd_line / close).replace([np.inf, -np.inf], np.nan)

        trend_filter = close > close.rolling(self.regime_window).mean()
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(0.7).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (
            (macd_line > signal_line)
            & (macd_ratio > self.macd_ratio_threshold)
            & trend_filter
            & vol_ok
        )
        short_cond = (
            (macd_line < signal_line)
            & (macd_ratio < -self.macd_ratio_threshold)
            & (~trend_filter)
            & vol_ok
        )
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        return pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"].astype(float)
        fast_ema = close.ewm(span=self.fast_span, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow_span, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=self.signal_span, adjust=False).mean()
        macd_hist = macd_line - signal_line
        macd_ratio = (macd_line / close).replace([np.inf, -np.inf], np.nan)

        trend_filter = close > close.rolling(self.regime_window).mean()
        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        vol_cap = annualized_vol.rolling(self.regime_window).quantile(0.7).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (
            (macd_line > signal_line)
            & (macd_ratio > self.macd_ratio_threshold)
            & trend_filter
            & vol_ok
        )
        short_cond = (
            (macd_line < signal_line)
            & (macd_ratio < -self.macd_ratio_threshold)
            & (~trend_filter)
            & vol_ok
        )
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "macd_long_with_regime_and_vol_ok",
            np.where(
                signal_series == -1,
                "macd_short_with_regime_and_vol_ok",
                "macd_or_regime_or_vol_blocked",
            ),
        )
        return pd.DataFrame(
            {
                "signal": signal_series,
                "fast_ema": fast_ema,
                "slow_ema": slow_ema,
                "macd_line": macd_line,
                "macd_signal": signal_line,
                "macd_hist": macd_hist,
                "macd_ratio": macd_ratio,
                "trend_filter": trend_filter.astype(int),
                "annualized_vol": annualized_vol,
                "vol_cap": vol_cap,
                "vol_ok": vol_ok.astype(int),
                "reason": reason,
            },
            index=data.index,
        )
