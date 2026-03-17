from __future__ import annotations

from app.core.models import Symbol, SymbolView
from app.services.data_source_registry import DataSourceRegistry
from app.services.market_session import MarketSessionService


class SymbolViewAssembler:
    def __init__(self, registry: DataSourceRegistry, session_service: MarketSessionService) -> None:
        self._registry = registry
        self._session_service = session_service

    async def build(self, symbol: Symbol) -> SymbolView:
        session_result = self._session_service.get_session(symbol.market)
        snapshot = await self._registry.get(symbol.datasource).fetch_snapshot(symbol.code)
        return SymbolView(
            code=symbol.code,
            name=symbol.name,
            market=symbol.market,
            datasource=symbol.datasource,
            data_state=snapshot.state,
            data_detail=snapshot.detail,
            session=session_result.session,
            session_label=session_result.label,
        )

    async def build_many(self, symbols: list[Symbol]) -> list[SymbolView]:
        results: list[SymbolView] = []
        for symbol in symbols:
            results.append(await self.build(symbol))
        return results
