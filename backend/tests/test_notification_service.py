import unittest

from app.core.models import SignalRecord, SignalType, SystemSettings
from app.services.notification_service import NotificationService
from app.services.system_settings_service import SystemSettingsService


class _FakeSettingsService(SystemSettingsService):
    def __init__(self, settings: SystemSettings) -> None:
        super().__init__()
        self._settings = settings


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

    def test_feishu_signal_throttle(self) -> None:
        sent: list[tuple[str, dict]] = []
        settings = SystemSettings(
            feishu_enabled=True,
            feishu_webhook_url="https://example.test/webhook",
            feishu_notify_signal=True,
            feishu_notify_system=True,
            feishu_throttle_seconds=60,
        )
        service = NotificationService(
            settings_service=_FakeSettingsService(settings),
            sender=lambda url, payload: sent.append((url, payload)),
        )
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
        service.add_signal(
            signal.model_copy(
                update={
                    "id": "sig2",
                    "trigger_time": "2026-01-01T00:15:00+00:00",
                    "trigger_price": 102.0,
                }
            )
        )
        self.assertEqual(len(sent), 1)

    def test_feishu_system_switch(self) -> None:
        sent: list[tuple[str, dict]] = []
        settings = SystemSettings(
            feishu_enabled=True,
            feishu_webhook_url="https://example.test/webhook",
            feishu_notify_signal=False,
            feishu_notify_system=False,
            feishu_throttle_seconds=0,
        )
        service = NotificationService(
            settings_service=_FakeSettingsService(settings),
            sender=lambda url, payload: sent.append((url, payload)),
        )
        service.add_system(title="数据源异常：Binance", content="断连", dedup_key="datasource:binance:down")
        self.assertEqual(len(sent), 0)


if __name__ == "__main__":
    unittest.main()
