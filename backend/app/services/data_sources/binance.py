from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.models import DataSnapshot, DataState, Kline, MarketQuote
from app.services.data_sources.base import BaseDataSource


class BinanceDataSource(BaseDataSource):
    name = "binance"
    _BASE_URL = "https://api.binance.com"

    @staticmethod
    def _map_symbol(symbol: str) -> str:
        return "ETHUSDT" if symbol.upper() == "ETH" else symbol.upper()

    @staticmethod
    def _interval_map(interval: str) -> str:
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
        }
        return mapping.get(interval, "15m")

    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        pair = self._map_symbol(symbol)
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

    async def fetch_quote(self, symbol: str) -> MarketQuote:
        pair = self._map_symbol(symbol)
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self._BASE_URL}/api/v3/ticker/24hr", params={"symbol": pair})
                response.raise_for_status()
                payload = response.json()
            return MarketQuote(
                symbol=symbol.upper(),
                last=float(payload["lastPrice"]),
                change=float(payload["priceChange"]),
                change_percent=float(payload["priceChangePercent"]),
                high=float(payload["highPrice"]),
                low=float(payload["lowPrice"]),
                volume=float(payload["volume"]),
                timestamp=now,
                state=DataState.REALTIME,
                detail="Binance 实时 24h",
            )
        except Exception as exc:  # noqa: BLE001
            return MarketQuote(
                symbol=symbol.upper(),
                last=0.0,
                change=0.0,
                change_percent=0.0,
                high=0.0,
                low=0.0,
                volume=0.0,
                timestamp=now,
                state=DataState.DISCONNECTED,
                detail=f"Binance 行情失败: {exc}",
            )

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Kline]:
        pair = self._map_symbol(symbol)
        mapped_interval = self._interval_map(interval)
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                response = await client.get(
                    f"{self._BASE_URL}/api/v3/klines",
                    params={"symbol": pair, "interval": mapped_interval, "limit": min(max(limit, 30), 500)},
                )
                response.raise_for_status()
                payload = response.json()

            candles: list[Kline] = []
            for row in payload:
                open_time = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).isoformat()
                close_time = datetime.fromtimestamp(row[6] / 1000, tz=timezone.utc).isoformat()
                candles.append(
                    Kline(
                        open_time=open_time,
                        close_time=close_time,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )
            return candles
        except Exception:
            return []
