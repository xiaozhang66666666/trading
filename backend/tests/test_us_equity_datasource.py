import asyncio
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.models import DataState, Kline, MarketQuote, SystemSettings
from app.services.data_sources.us_equity_placeholder import UsEquityRealtimePlaceholderDataSource


@dataclass
class _FakeProvider:
    provider_key: str
    configured: bool = True
    fail_quote_times: int = 0
    fail_kline_times: int = 0

    def __post_init__(self) -> None:
        self.quote_calls = 0
        self.kline_calls = 0

    async def quote(self, symbol: str) -> MarketQuote | None:
        self.quote_calls += 1
        if self.quote_calls <= self.fail_quote_times:
            raise RuntimeError(f"{self.provider_key} quote failed")
        return MarketQuote(
            symbol=symbol,
            last=123.4 if self.provider_key == "twelve_data" else 125.6,
            change=0.0,
            change_percent=0.0,
            high=126.0,
            low=122.0,
            volume=1.0,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            state=DataState.DELAYED if self.provider_key == "twelve_data" else DataState.REALTIME,
            detail=self.provider_key,
        )

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline] | None:
        self.kline_calls += 1
        if self.kline_calls <= self.fail_kline_times:
            raise RuntimeError(f"{self.provider_key} kline failed")
        return [
            Kline(
                open_time="2026-01-01T00:00:00+00:00",
                close_time="2026-01-01T00:01:00+00:00",
                open=1.0,
                high=1.1,
                low=0.9,
                close=1.0,
                volume=10.0,
            )
        ]


class UsEquityDataSourceTest(unittest.TestCase):
    def test_switch_to_fallback_provider(self) -> None:
        preferred = _FakeProvider(provider_key="twelve_data", fail_quote_times=3)
        fallback = _FakeProvider(provider_key="alpaca", fail_quote_times=0)
        datasource = UsEquityRealtimePlaceholderDataSource(
            settings_getter=lambda: SystemSettings(preferred_us_provider="twelve_data", fallback_us_provider="alpaca")
        )
        datasource._providers = {"twelve_data": preferred, "alpaca": fallback}  # type: ignore[attr-defined]

        quote = asyncio.run(datasource.fetch_quote("QQQ"))

        self.assertEqual(quote.detail, "alpaca")
        self.assertEqual(preferred.quote_calls, 3)
        self.assertEqual(fallback.quote_calls, 1)

    def test_retry_then_success(self) -> None:
        preferred = _FakeProvider(provider_key="alpaca", fail_kline_times=2)
        datasource = UsEquityRealtimePlaceholderDataSource(
            settings_getter=lambda: SystemSettings(preferred_us_provider="alpaca", fallback_us_provider="twelve_data")
        )
        datasource._providers = {"alpaca": preferred}  # type: ignore[attr-defined]

        candles = asyncio.run(datasource.fetch_klines("QQQ", "1m", 30))

        self.assertEqual(len(candles), 1)
        self.assertEqual(preferred.kline_calls, 3)


if __name__ == "__main__":
    unittest.main()
