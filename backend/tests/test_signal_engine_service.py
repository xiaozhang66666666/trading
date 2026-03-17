import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.core.models import (
    Kline,
    MarketType,
    RunInstance,
    RunInstancePayload,
    RunStatus,
    StrategyDirectionConfig,
    StrategyPayload,
    StrategyRecord,
    StrategyTemplate,
    StrategyVersion,
    Symbol,
)
from app.services.signal_engine_service import SignalEngineService


class _FakeMarketData:
    async def get_klines(self, symbol: Symbol, interval: str, limit: int) -> list[Kline]:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles: list[Kline] = []
        price = 100.0
        for i in range(80):
            price += 1.2 if i < 50 else -0.9
            open_time = start + timedelta(minutes=i)
            candles.append(
                Kline(
                    open_time=open_time.isoformat(),
                    close_time=(open_time + timedelta(minutes=1)).isoformat(),
                    open=price - 0.3,
                    high=price + 0.5,
                    low=price - 0.6,
                    close=price,
                    volume=1000,
                )
            )
        return candles


class SignalEngineServiceTest(unittest.TestCase):
    def test_dedup_and_stop_status(self) -> None:
        engine = SignalEngineService(market_data=_FakeMarketData())
        payload = StrategyPayload(
            name="策略A",
            template=StrategyTemplate.MA_CROSS,
            interval="1m",
            open_condition="x",
            close_condition="y",
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
        run = RunInstance(
            id="r1",
            status=RunStatus.RUNNING,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
            payload=RunInstancePayload(
                name="run",
                strategy_id="s1",
                symbol="ETH",
                interval="1m",
                fee_rate=0.0,
                slippage_rate=0.0,
                risk_limit=0.2,
                notify_in_app=True,
            ),
        )
        symbol = Symbol(code="ETH", name="Ethereum", market=MarketType.CRYPTO, datasource="binance")

        first = asyncio.run(engine.tick([run], {"s1": strategy}, {"ETH": symbol}))
        second = asyncio.run(engine.tick([run], {"s1": strategy}, {"ETH": symbol}))

        self.assertGreaterEqual(len(first), 0)
        self.assertEqual(len(second), 0)

        run_stopped = run.model_copy(update={"status": RunStatus.STOPPED})
        third = asyncio.run(engine.tick([run_stopped], {"s1": strategy}, {"ETH": symbol}))
        self.assertEqual(len(third), 0)


if __name__ == "__main__":
    unittest.main()
