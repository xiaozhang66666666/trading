from __future__ import annotations

from functools import lru_cache

from app.services.data_source_registry import DataSourceRegistry
from app.services.market_session import MarketSessionService
from app.services.symbol_service import SymbolService
from app.services.symbol_view_assembler import SymbolViewAssembler
from app.services.watchlist_service import WatchlistService


@lru_cache
def get_registry() -> DataSourceRegistry:
    return DataSourceRegistry()


@lru_cache
def get_symbol_service() -> SymbolService:
    return SymbolService(registry=get_registry())


@lru_cache
def get_watchlist_service() -> WatchlistService:
    return WatchlistService()


@lru_cache
def get_symbol_view_assembler() -> SymbolViewAssembler:
    return SymbolViewAssembler(registry=get_registry(), session_service=MarketSessionService())
