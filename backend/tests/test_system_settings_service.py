import unittest

from app.core.models import SystemSettings
from app.services.system_settings_service import SystemSettingsService


class SystemSettingsServiceTest(unittest.TestCase):
    def test_update_settings(self) -> None:
        service = SystemSettingsService()
        payload = SystemSettings(default_fee_rate=0.001, timezone="Asia/Shanghai")
        updated = service.update(payload)
        self.assertEqual(updated.default_fee_rate, 0.001)
        self.assertEqual(service.get().timezone, "Asia/Shanghai")


if __name__ == "__main__":
    unittest.main()
