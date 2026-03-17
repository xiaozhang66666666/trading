from __future__ import annotations

from app.core.models import DataSnapshot, DataState
from app.services.data_sources.base import BaseDataSource


class UsEquityRealtimePlaceholderDataSource(BaseDataSource):
    name = "us_equity_realtime"

    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        # 仅保留真实时行情源接入位，不在 T1-01 里实现具体供应商。
        return DataSnapshot(
            state=DataState.RESERVED,
            detail=f"{symbol} 美股真实时行情源接入位已预留，待配置供应商",
            last_price=None,
        )

    async def health_check(self) -> DataSnapshot:
        return DataSnapshot(
            state=DataState.RESERVED,
            detail="美股真实时行情源接入位已创建（待接 Polygon/IEX/Alpaca 等）",
            last_price=None,
        )
