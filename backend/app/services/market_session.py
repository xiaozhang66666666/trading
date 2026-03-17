from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from app.core.models import MarketType, SessionType

US_EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionResult:
    session: SessionType
    label: str


class MarketSessionService:
    # 美股首版时段规则：盘前 04:00-09:30，常规 09:30-16:00，盘后 16:00-20:00。
    PRE_START = time(hour=4, minute=0)
    REGULAR_START = time(hour=9, minute=30)
    REGULAR_END = time(hour=16, minute=0)
    AFTER_END = time(hour=20, minute=0)

    def get_session(self, market: MarketType, now_utc: datetime | None = None) -> SessionResult:
        if market == MarketType.CRYPTO:
            return SessionResult(SessionType.ALWAYS_OPEN, "7x24 连续交易")

        now_utc = now_utc or datetime.now(tz=timezone.utc)
        local_now = now_utc.astimezone(US_EASTERN)
        current = local_now.time()

        if self.PRE_START <= current < self.REGULAR_START:
            return SessionResult(SessionType.PRE_MARKET, "盘前")
        if self.REGULAR_START <= current < self.REGULAR_END:
            return SessionResult(SessionType.REGULAR, "正常盘")
        if self.REGULAR_END <= current < self.AFTER_END:
            return SessionResult(SessionType.AFTER_HOURS, "盘后")
        return SessionResult(SessionType.CLOSED, "休市")
