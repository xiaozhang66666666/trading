from datetime import datetime, timezone
import unittest

from app.core.models import MarketType, SessionType
from app.services.market_session import MarketSessionService


class MarketSessionTest(unittest.TestCase):
    def test_crypto_is_always_open(self) -> None:
        service = MarketSessionService()
        result = service.get_session(MarketType.CRYPTO)
        self.assertEqual(result.session, SessionType.ALWAYS_OPEN)

    def test_us_regular_session(self) -> None:
        service = MarketSessionService()
        # 2026-03-17 14:00 UTC == 10:00 美东，应该是正常盘。
        result = service.get_session(MarketType.US_EQUITY, datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc))
        self.assertEqual(result.session, SessionType.REGULAR)


if __name__ == "__main__":
    unittest.main()
