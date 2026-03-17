from __future__ import annotations

from typing import Callable

from app.core.models import SystemSettings

from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.binance import BinanceDataSource
from app.services.data_sources.us_equity_placeholder import UsEquityRealtimePlaceholderDataSource


class DataSourceRegistry:
    def __init__(self, settings_getter: Callable[[], SystemSettings] | None = None) -> None:
        self._sources: dict[str, BaseDataSource] = {
            "binance": BinanceDataSource(),
            "us_equity_realtime": UsEquityRealtimePlaceholderDataSource(settings_getter=settings_getter),
        }

    def get(self, name: str) -> BaseDataSource:
        return self._sources[name]

    def all_sources(self) -> dict[str, BaseDataSource]:
        return self._sources
