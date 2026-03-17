from __future__ import annotations

from app.core.models import Kline, MarketOverview, Symbol
from app.services.data_source_registry import DataSourceRegistry
from app.services.market_session import MarketSessionService


class MarketDataService:
    def __init__(self, registry: DataSourceRegistry, session_service: MarketSessionService) -> None:
        self._registry = registry
        self._session_service = session_service

    async def get_overview(self, symbol: Symbol) -> MarketOverview:
        source = self._registry.get(symbol.datasource)
        session = self._session_service.get_session(symbol.market)
        quote = await source.fetch_quote(symbol.code)
        return MarketOverview(
            symbol=symbol.code,
            market=symbol.market,
            session=session.session,
            session_label=session.label,
            quote=quote,
        )

    async def get_klines(self, symbol: Symbol, interval: str, limit: int) -> list[Kline]:
        source = self._registry.get(symbol.datasource)
        return await source.fetch_klines(symbol.code, interval, limit)
