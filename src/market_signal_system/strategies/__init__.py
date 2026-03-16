"""Strategy registry."""

from __future__ import annotations

from market_signal_system.strategies.atr_regime import AtrRegimeStrategy
from market_signal_system.strategies.donchian import DonchianBreakoutStrategy
from market_signal_system.strategies.dual_momentum import DualMomentumStrategy
from market_signal_system.strategies.macd_regime import MacdRegimeStrategy
from market_signal_system.strategies.momentum import MomentumVolatilityStrategy
from market_signal_system.strategies.momentum_regime import RegimeMomentumStrategy
from market_signal_system.strategies.score_regime import ScoreRegimeStrategy
from market_signal_system.strategies.trend import MovingAverageCrossStrategy


def get_strategy(name: str, **kwargs):
    key = name.lower()
    if key == "ma_cross":
        return MovingAverageCrossStrategy(**kwargs)
    if key == "donchian":
        return DonchianBreakoutStrategy(**kwargs)
    if key == "momentum":
        return MomentumVolatilityStrategy(**kwargs)
    if key == "regime":
        return RegimeMomentumStrategy(**kwargs)
    if key == "macd_regime":
        return MacdRegimeStrategy(**kwargs)
    if key == "atr_regime":
        return AtrRegimeStrategy(**kwargs)
    if key == "score_regime":
        return ScoreRegimeStrategy(**kwargs)
    if key == "dual_momentum":
        return DualMomentumStrategy(**kwargs)
    raise ValueError(f"Unknown strategy: {name}")


__all__ = [
    "MovingAverageCrossStrategy",
    "DonchianBreakoutStrategy",
    "MomentumVolatilityStrategy",
    "RegimeMomentumStrategy",
    "MacdRegimeStrategy",
    "AtrRegimeStrategy",
    "ScoreRegimeStrategy",
    "DualMomentumStrategy",
    "get_strategy",
]
