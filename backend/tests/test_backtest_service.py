import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.core.models import (
    BacktestCompareRequest,
    BacktestRequest,
    BacktestScanRequest,
    ScanRange,
    PortfolioBacktestRequest,
    Kline,
    MarketType,
    StrategyDirectionConfig,
    StrategyPayload,
    StrategyRecord,
    StrategyTemplate,
    StrategyVersion,
    Symbol,
)
from app.services.backtest_service import BacktestService


class _FakeMarketData:
    async def get_klines(self, symbol: Symbol, interval: str, limit: int) -> list[Kline]:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        items: list[Kline] = []
        price = 100.0
        for i in range(120):
            price += 0.6 if i < 60 else -0.45
            open_time = start + timedelta(minutes=i)
            close_time = open_time + timedelta(minutes=1)
            items.append(
                Kline(
                    open_time=open_time.isoformat(),
                    close_time=close_time.isoformat(),
                    open=price - 0.2,
                    high=price + 0.4,
                    low=price - 0.5,
                    close=price,
                    volume=1000 + i,
                )
            )
        return items


class BacktestServiceTest(unittest.TestCase):
    def test_run_backtest_returns_metrics(self) -> None:
        service = BacktestService(market_data=_FakeMarketData())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")
        payload = StrategyPayload(
            name="策略A",
            template=StrategyTemplate.MA_CROSS,
            interval="1m",
            open_condition="MA5 上穿 MA20",
            close_condition="MA5 下穿 MA20",
            take_profit=2,
            stop_loss=1,
            position_size=0.3,
            direction=StrategyDirectionConfig(allow_long=True, allow_short=True, include_extended_hours=False),
            json_dsl='{"strategy":{},"indicators":[],"conditions":{},"entry_long":{},"exit_long":{},"entry_short":{},"exit_short":{},"risk":{}}',
        )
        strategy = StrategyRecord(
            id="s1",
            name="策略A",
            current_version=1,
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
            latest_payload=payload,
            versions=[StrategyVersion(version=1, created_at=datetime.now(tz=timezone.utc).isoformat(), payload=payload)],
        )
        request = BacktestRequest(strategy_id="s1", symbol="ETH", interval="1m")

        result = asyncio.run(service.run(request, symbol=symbol, strategy=strategy))

        self.assertGreaterEqual(result.metrics.trade_count, 0)
        self.assertGreater(len(result.equity_curve), 0)

    def test_scan_and_compare(self) -> None:
        service = BacktestService(market_data=_FakeMarketData())
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")
        payload = StrategyPayload(
            name="策略A",
            template=StrategyTemplate.MA_CROSS,
            interval="1m",
            open_condition="MA5 上穿 MA20",
            close_condition="MA5 下穿 MA20",
            take_profit=2,
            stop_loss=1,
            position_size=0.3,
            direction=StrategyDirectionConfig(allow_long=True, allow_short=True, include_extended_hours=False),
            json_dsl='{"strategy":{},"indicators":[],"conditions":{},"entry_long":{},"exit_long":{},"entry_short":{},"exit_short":{},"risk":{}}',
        )
        strategy = StrategyRecord(
            id="s1",
            name="策略A",
            current_version=1,
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
            latest_payload=payload,
            versions=[StrategyVersion(version=1, created_at=datetime.now(tz=timezone.utc).isoformat(), payload=payload)],
        )

        scan = asyncio.run(
            service.scan(
                BacktestScanRequest(
                    strategy_id="s1",
                    symbol="ETH",
                    interval="1m",
                    fee_rate=ScanRange(start=0.0002, end=0.0004, step=0.0002),
                    slippage_rate=ScanRange(start=0.0002, end=0.0004, step=0.0002),
                    top_n=3,
                ),
                symbol=symbol,
                strategy=strategy,
            )
        )
        self.assertEqual(scan.scanned_count, 4)
        self.assertLessEqual(len(scan.items), 3)

        compare = asyncio.run(
            service.compare(
                BacktestCompareRequest(strategy_ids=["s1"], symbol="ETH", interval="1m"),
                symbol=symbol,
                strategies=[strategy],
            )
        )
        self.assertEqual(len(compare.items), 1)
        self.assertEqual(compare.items[0].strategy_id, "s1")

    def test_run_portfolio(self) -> None:
        service = BacktestService(market_data=_FakeMarketData())
        payload = StrategyPayload(
            name="策略A",
            template=StrategyTemplate.MA_CROSS,
            interval="1m",
            open_condition="MA5 上穿 MA20",
            close_condition="MA5 下穿 MA20",
            take_profit=2,
            stop_loss=1,
            position_size=0.3,
            direction=StrategyDirectionConfig(allow_long=True, allow_short=True, include_extended_hours=False),
            json_dsl='{"strategy":{},"indicators":[],"conditions":{},"entry_long":{},"exit_long":{},"entry_short":{},"exit_short":{},"risk":{}}',
        )
        strategy = StrategyRecord(
            id="s1",
            name="策略A",
            current_version=1,
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
            latest_payload=payload,
            versions=[StrategyVersion(version=1, created_at=datetime.now(tz=timezone.utc).isoformat(), payload=payload)],
        )
        symbols = [
            Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance"),
            Symbol(code="QQQ", name="QQQ", market=MarketType.US_EQUITY, datasource="us_equity_realtime"),
        ]

        result = asyncio.run(
            service.run_portfolio(
                PortfolioBacktestRequest(strategy_id="s1", symbols=["ETH", "QQQ"], interval="1m"),
                symbols=symbols,
                strategy=strategy,
            )
        )

        self.assertEqual(len(result.items), 2)
        self.assertGreaterEqual(len(result.portfolio_equity_curve), 0)


if __name__ == "__main__":
    unittest.main()
