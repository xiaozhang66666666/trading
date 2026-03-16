"""Data provider abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Abstract market data provider."""

    @abstractmethod
    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return OHLCV dataframe indexed by UTC timestamp."""
