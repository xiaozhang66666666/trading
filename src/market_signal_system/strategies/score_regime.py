"""Weighted multi-factor score strategy with regime-volatility filters."""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_signal_system.strategies.base import Strategy


class ScoreRegimeStrategy(Strategy):
    """Combine momentum/trend/mean-reversion into a single long-short score."""

    def __init__(
        self,
        momentum_window: int = 126,
        trend_window: int = 200,
        mean_revert_window: int = 20,
        volatility_window: int = 63,
        score_threshold: float = 0.25,
        momentum_weight: float = 0.4,
        trend_weight: float = 0.35,
        mean_revert_weight: float = 0.25,
        weights: list[float] | tuple[float, float, float] | None = None,
    ) -> None:
        if momentum_window < 5 or trend_window < 20 or mean_revert_window < 5 or volatility_window < 10:
            raise ValueError("窗口参数过小，无法用于中长线评分策略。")
        if score_threshold <= 0:
            raise ValueError("score_threshold 必须大于 0。")
        # Backward compatibility for old templates: weights=[momentum, trend, mean_revert]
        if weights is not None:
            if len(weights) != 3:
                raise ValueError("weights 必须包含 3 个元素：[momentum, trend, mean_revert]。")
            momentum_weight, trend_weight, mean_revert_weight = float(weights[0]), float(weights[1]), float(weights[2])

        if min(momentum_weight, trend_weight, mean_revert_weight) < 0:
            raise ValueError("权重不能为负。")
        total_weight = momentum_weight + trend_weight + mean_revert_weight
        if total_weight <= 0:
            raise ValueError("权重总和必须大于 0。")

        self.momentum_window = momentum_window
        self.trend_window = trend_window
        self.mean_revert_window = mean_revert_window
        self.volatility_window = volatility_window
        self.score_threshold = score_threshold
        self.momentum_weight = momentum_weight / total_weight
        self.trend_weight = trend_weight / total_weight
        self.mean_revert_weight = mean_revert_weight / total_weight
        self.name = "score_regime"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        explain = self.explain(data)
        return explain["signal"].astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"].astype(float)
        momentum_raw = close.pct_change(self.momentum_window)
        trend_ma = close.rolling(self.trend_window).mean()
        trend_raw = close / trend_ma - 1.0
        mean_ma = close.rolling(self.mean_revert_window).mean()
        mean_revert_raw = (mean_ma - close) / close

        momentum_score = np.tanh(momentum_raw / 0.10)
        trend_score = np.tanh(trend_raw / 0.05)
        mean_revert_score = np.tanh(mean_revert_raw / 0.03)

        weighted_score = (
            self.momentum_weight * momentum_score
            + self.trend_weight * trend_score
            + self.mean_revert_weight * mean_revert_score
        )

        annualized_vol = close.pct_change().rolling(self.volatility_window).std() * np.sqrt(252)
        vol_cap = annualized_vol.rolling(self.trend_window).quantile(0.7).shift(1)
        vol_ok = annualized_vol < vol_cap

        long_cond = (weighted_score > self.score_threshold) & vol_ok
        short_cond = (weighted_score < -self.score_threshold) & vol_ok
        signal = np.where(long_cond, 1, np.where(short_cond, -1, 0))
        signal_series = pd.Series(signal, index=data.index, name="signal").fillna(0).astype(int)
        reason = np.where(
            signal_series == 1,
            "score_long_with_vol_ok",
            np.where(signal_series == -1, "score_short_with_vol_ok", "score_or_vol_filter_blocked"),
        )

        return pd.DataFrame(
            {
                "signal": signal_series,
                "score": weighted_score,
                "momentum_score": momentum_score,
                "trend_score": trend_score,
                "mean_revert_score": mean_revert_score,
                "annualized_vol": annualized_vol,
                "vol_cap": vol_cap,
                "vol_ok": vol_ok.astype(int),
                "reason": reason,
            },
            index=data.index,
        )
