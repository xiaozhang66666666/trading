from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.models import DataSnapshot, DataState
from app.services.data_sources.base import BaseDataSource


class BinanceDataSource(BaseDataSource):
    name = "binance"
    _BASE_URL = "https://api.binance.com"

    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        # Binance 使用 ETHUSDT，前端传 ETH 时在这里做映射。
        pair = "ETHUSDT" if symbol.upper() == "ETH" else symbol.upper()
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self._BASE_URL}/api/v3/ticker/price", params={"symbol": pair})
                response.raise_for_status()
                payload = response.json()
            price = float(payload["price"])
            return DataSnapshot(state=DataState.REALTIME, detail="Binance 实时", last_price=price)
        except Exception as exc:  # noqa: BLE001
            return DataSnapshot(state=DataState.DISCONNECTED, detail=f"Binance 不可用: {exc}")

    async def health_check(self) -> DataSnapshot:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._BASE_URL}/api/v3/time")
                response.raise_for_status()
            return DataSnapshot(
                state=DataState.REALTIME,
                detail=f"Binance 在线，检查时间 {datetime.now(tz=timezone.utc).isoformat()}",
            )
        except Exception as exc:  # noqa: BLE001
            return DataSnapshot(state=DataState.DISCONNECTED, detail=f"Binance 健康检查失败: {exc}")
