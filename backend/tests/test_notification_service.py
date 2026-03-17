import unittest

from app.core.models import SignalRecord, SignalType
from app.services.notification_service import NotificationService


class NotificationServiceTest(unittest.TestCase):
    def test_add_signal_and_mark_read(self) -> None:
        service = NotificationService()
        signal = SignalRecord(
            id="sig1",
            run_instance_id="r1",
            strategy_id="s1",
            symbol="ETH",
            interval="15m",
            signal_type=SignalType.OPEN_LONG,
            trigger_time="2026-01-01T00:00:00+00:00",
            trigger_price=100.0,
            reason_snapshot="{}",
        )
        service.add_signal(signal)
        items = service.list()
        self.assertEqual(len(items), 1)
        self.assertEqual(service.unread_count(), 1)

        service.mark_read([items[0].id])
        self.assertEqual(service.unread_count(), 0)


if __name__ == "__main__":
    unittest.main()
