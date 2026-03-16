"""Strategy abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Strategy should output position signal in {-1, 0, 1}."""

    name: str

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Return target position series indexed as data."""

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return per-bar explain dataframe; must include signal and reason."""
        signals = self.generate_signals(data).astype(int)
        reason = signals.map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})
        return pd.DataFrame({"signal": signals, "reason": reason}, index=data.index)
