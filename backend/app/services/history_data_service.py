from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.models import HistoryDataset, Kline, MarketType, Symbol
from app.services.market_data_service import MarketDataService


@dataclass
class _HistoryCacheItem:
    symbol: str
    interval: str
    source: str
    updated_at: str
    missing_points: int
    candles: list[Kline]


class HistoryDataService:
    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data
        self._cache: dict[tuple[str, str], _HistoryCacheItem] = {}

    @staticmethod
    def _interval_seconds(interval: str) -> int:
        mapping = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return mapping.get(interval, 900)

    def _calc_missing_points(self, candles: list[Kline], interval: str) -> int:
        if len(candles) < 2:
            return 0

        expected = self._interval_seconds(interval)
        missing = 0
        for i in range(1, len(candles)):
            prev = datetime.fromisoformat(candles[i - 1].open_time.replace("Z", "+00:00"))
            curr = datetime.fromisoformat(candles[i].open_time.replace("Z", "+00:00"))
            actual_seconds = int((curr - prev).total_seconds())
            if actual_seconds > expected:
                missing += max(actual_seconds // expected - 1, 0)
        return missing

    async def fetch_history(self, symbol: Symbol, interval: str, limit: int, force_refresh: bool = False) -> HistoryDataset:
        key = (symbol.code, interval)
        if not force_refresh and key in self._cache:
            cached = self._cache[key]
            return HistoryDataset(
                symbol=cached.symbol,
                interval=cached.interval,
                source=cached.source,
                updated_at=cached.updated_at,
                missing_points=cached.missing_points,
                has_missing=cached.missing_points > 0,
                candles=cached.candles,
            )

        candles = await self._market_data.get_klines(symbol=symbol, interval=interval, limit=min(max(limit, 30), 500))
        missing = self._calc_missing_points(candles, interval)
        source = "Binance" if symbol.market == MarketType.CRYPTO else "Alpaca/TwelveData"
        item = _HistoryCacheItem(
            symbol=symbol.code,
            interval=interval,
            source=source,
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
            missing_points=missing,
            candles=candles,
        )
        self._cache[key] = item
        return HistoryDataset(
            symbol=item.symbol,
            interval=item.interval,
            source=item.source,
            updated_at=item.updated_at,
            missing_points=item.missing_points,
            has_missing=item.missing_points > 0,
            candles=item.candles,
        )

    @staticmethod
    def to_csv_bytes(dataset: HistoryDataset) -> bytes:
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["open_time", "close_time", "open", "high", "low", "close", "volume"])
        for candle in dataset.candles:
            writer.writerow(
                [
                    candle.open_time,
                    candle.close_time,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ]
            )
        return stream.getvalue().encode("utf-8")

    @staticmethod
    def to_parquet_bytes(dataset: HistoryDataset) -> bytes:
        # 采用 pandas + pyarrow 写 parquet；环境缺失时抛错由 API 返回可读提示。
        import pandas as pd

        rows = [
            {
                "open_time": candle.open_time,
                "close_time": candle.close_time,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in dataset.candles
        ]
        frame = pd.DataFrame(rows)
        buffer = io.BytesIO()
        frame.to_parquet(buffer, index=False)
        return buffer.getvalue()
