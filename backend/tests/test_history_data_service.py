import asyncio
import unittest

from app.core.models import Kline, MarketType, Symbol
from app.services.history_data_service import HistoryDataService


class _FakeMarketData:
    async def get_klines(self, symbol: Symbol, interval: str, limit: int) -> list[Kline]:
        return [
            Kline(
                open_time="2026-01-01T00:00:00+00:00",
                close_time="2026-01-01T00:01:00+00:00",
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=12,
            ),
            Kline(
                open_time="2026-01-01T00:01:00+00:00",
                close_time="2026-01-01T00:02:00+00:00",
                open=100.5,
                high=102,
                low=100,
                close=101,
                volume=10,
            ),
        ]


class HistoryDataServiceTest(unittest.TestCase):
    def test_fetch_history_and_csv(self) -> None:
        service = HistoryDataService(market_data=_FakeMarketData())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")

        dataset = asyncio.run(service.fetch_history(symbol=symbol, interval="1m", limit=100))

        self.assertEqual(dataset.symbol, "ETH")
        self.assertEqual(dataset.source, "Binance")
        self.assertEqual(dataset.missing_points, 0)

        csv_bytes = service.to_csv_bytes(dataset)
        text = csv_bytes.decode("utf-8")
        self.assertIn("open_time", text)
        self.assertIn("2026-01-01T00:01:00+00:00", text)


if __name__ == "__main__":
    unittest.main()
