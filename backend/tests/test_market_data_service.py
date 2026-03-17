import asyncio
import unittest

from app.core.models import DataSnapshot, DataState, Kline, MarketQuote, MarketType, Symbol
from app.services.market_data_service import MarketDataService
from app.services.market_session import MarketSessionService


class _FakeSource:
    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        return DataSnapshot(state=DataState.REALTIME, detail="ok", last_price=100.0)

    async def health_check(self) -> DataSnapshot:
        return DataSnapshot(state=DataState.REALTIME, detail="ok")

    async def fetch_quote(self, symbol: str) -> MarketQuote:
        return MarketQuote(
            symbol=symbol,
            last=100.0,
            change=1.0,
            change_percent=1.0,
            high=101.0,
            low=99.0,
            volume=11.0,
            timestamp="2026-01-01T00:00:00+00:00",
            state=DataState.REALTIME,
            detail="ok",
        )

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Kline]:
        return [
            Kline(
                open_time="2026-01-01T00:00:00+00:00",
                close_time="2026-01-01T00:01:00+00:00",
                open=99.0,
                high=101.0,
                low=98.0,
                close=100.0,
                volume=10.0,
            )
        ]


class _GapSource(_FakeSource):
    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Kline]:
        return [
            Kline(
                open_time="2026-01-01T00:00:00+00:00",
                close_time="2026-01-01T00:01:00+00:00",
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=10.0,
            ),
            Kline(
                open_time="2026-01-01T00:03:00+00:00",
                close_time="2026-01-01T00:04:00+00:00",
                open=102.0,
                high=103.0,
                low=101.0,
                close=102.0,
                volume=10.0,
            ),
        ]


class _FakeRegistry:
    def __init__(self) -> None:
        self._sources = {
            "binance": _FakeSource(),
            "us_equity_realtime": _FakeSource(),
        }

    def get(self, name: str):
        return self._sources[name]


class _GapRegistry(_FakeRegistry):
    def __init__(self) -> None:
        self._sources = {
            "binance": _GapSource(),
            "us_equity_realtime": _GapSource(),
        }


class MarketDataServiceTest(unittest.TestCase):
    def test_overview_contains_session_and_quote(self) -> None:
        service = MarketDataService(registry=_FakeRegistry(), session_service=MarketSessionService())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")

        overview = asyncio.run(service.get_overview(symbol))

        self.assertEqual(overview.symbol, "ETH")
        self.assertEqual(overview.quote.last, 100.0)
        self.assertEqual(overview.session_label, "7x24 连续交易")

    def test_klines_returns_rows(self) -> None:
        service = MarketDataService(registry=_FakeRegistry(), session_service=MarketSessionService())
        symbol = Symbol(code="QQQ", name="QQQ", market=MarketType.US_EQUITY, datasource="us_equity_realtime")

        klines = asyncio.run(service.get_klines(symbol, "1m", 120))

        self.assertEqual(len(klines), 1)
        self.assertEqual(klines[0].close, 100.0)

    def test_klines_fill_missing_points(self) -> None:
        service = MarketDataService(registry=_GapRegistry(), session_service=MarketSessionService())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")

        klines = asyncio.run(service.get_klines(symbol, "1m", 120))

        self.assertEqual(len(klines), 4)
        self.assertEqual(klines[1].open_time, "2026-01-01T00:01:00+00:00")
        self.assertEqual(klines[2].open_time, "2026-01-01T00:02:00+00:00")

    def test_quality_report_detects_missing(self) -> None:
        service = MarketDataService(registry=_GapRegistry(), session_service=MarketSessionService())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")

        report = asyncio.run(service.get_kline_quality(symbol, "1m", 120))

        self.assertEqual(report.missing_points, 2)
        self.assertEqual(report.filled_points, 2)


if __name__ == "__main__":
    unittest.main()
