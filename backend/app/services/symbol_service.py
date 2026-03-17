from __future__ import annotations

from datetime import datetime, timezone

from app.core.models import DataSourceStatus, MarketType, Symbol
from app.services.data_source_registry import DataSourceRegistry


class SymbolService:
    # 首期标的池只放验收范围，避免越界实现后续功能。
    _CATALOG = [
        Symbol(
            code="QQQ",
            name="Invesco QQQ Trust",
            market=MarketType.US_EQUITY,
            datasource="us_equity_realtime",
        ),
        Symbol(
            code="TQQQ",
            name="ProShares UltraPro QQQ",
            market=MarketType.US_EQUITY,
            datasource="us_equity_realtime",
        ),
        Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance"),
    ]

    def __init__(self, registry: DataSourceRegistry) -> None:
        self._registry = registry

    def search(self, query: str) -> list[Symbol]:
        keyword = query.strip().upper()
        if not keyword:
            return self._CATALOG
        return [
            symbol
            for symbol in self._CATALOG
            if keyword in symbol.code.upper() or keyword in symbol.name.upper()
        ]

    def get_symbol(self, code: str) -> Symbol | None:
        normalized = code.strip().upper()
        for symbol in self._CATALOG:
            if symbol.code == normalized:
                return symbol
        return None

    async def datasource_status(self) -> list[DataSourceStatus]:
        items = []
        checked_at = datetime.now(tz=timezone.utc).isoformat()
        for source_name, source in self._registry.all_sources().items():
            snapshot = await source.health_check()
            items.append(
                DataSourceStatus(
                    name=source_name,
                    state=snapshot.state,
                    detail=snapshot.detail,
                    checked_at=checked_at,
                )
            )
        return items
