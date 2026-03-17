import unittest

from app.core.models import RunInstancePayload, RunStatus
from app.services.run_instance_service import RunInstanceService


class RunInstanceServiceTest(unittest.TestCase):
    def test_create_copy_and_status(self) -> None:
        service = RunInstanceService()
        payload = RunInstancePayload(
            name="ETH 15m + 策略A",
            strategy_id="s1",
            symbol="ETH",
            interval="15m",
            fee_rate=0.0005,
            slippage_rate=0.0005,
            risk_limit=0.2,
            notify_in_app=True,
        )
        instance = service.create(payload)
        self.assertEqual(instance.status, "PENDING")

        running = service.set_status(instance.id, RunStatus.RUNNING)
        self.assertEqual(running.status, RunStatus.RUNNING)

        copied = service.copy(instance.id)
        self.assertIn("副本", copied.payload.name)

    def test_batch_status_and_group(self) -> None:
        service = RunInstanceService()
        payload_a = RunInstancePayload(
            name="A",
            strategy_id="s1",
            symbol="ETH",
            interval="15m",
            fee_rate=0.0005,
            slippage_rate=0.0005,
            risk_limit=0.2,
            group_name="g1",
        )
        payload_b = RunInstancePayload(
            name="B",
            strategy_id="s1",
            symbol="QQQ",
            interval="15m",
            fee_rate=0.0005,
            slippage_rate=0.0005,
            risk_limit=0.2,
            group_name="g2",
        )
        service.create(payload_a)
        service.create(payload_b)

        updated = service.batch_set_status(RunStatus.RUNNING, group_name="g1")
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].status, RunStatus.RUNNING)
        self.assertEqual(service.group_summary()["g1"], 1)


if __name__ == "__main__":
    unittest.main()
