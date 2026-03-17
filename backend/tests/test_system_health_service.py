import asyncio
import unittest

from app.core.models import DataSourceStatus, DataState, RunInstance, RunInstancePayload, RunStatus
from app.services.system_health_service import SystemHealthService


class _FakeSymbolService:
    async def datasource_status(self):
        return [
            DataSourceStatus(name="binance", state=DataState.REALTIME, detail="ok", checked_at="2026-01-01")
        ]


class _FakeRunService:
    def list(self):
        return [
            RunInstance(
                id="r1",
                status=RunStatus.RUNNING,
                created_at="2026-01-01",
                updated_at="2026-01-01",
                payload=RunInstancePayload(
                    name="x",
                    strategy_id="s1",
                    symbol="ETH",
                    interval="15m",
                    fee_rate=0,
                    slippage_rate=0,
                    risk_limit=0.1,
                    notify_in_app=True,
                ),
            )
        ]


class SystemHealthServiceTest(unittest.TestCase):
    def test_health_summary(self) -> None:
        service = SystemHealthService(symbol_service=_FakeSymbolService(), run_service=_FakeRunService())
        result = asyncio.run(service.check())
        self.assertEqual(result.api_status, "ok")
        self.assertEqual(result.running_instances, 1)


if __name__ == "__main__":
    unittest.main()
