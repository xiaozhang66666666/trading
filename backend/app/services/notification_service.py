from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.models import NotificationRecord, NotificationType, SignalRecord


class NotificationService:
    def __init__(self) -> None:
        self._items: list[NotificationRecord] = []
        self._dedup: set[str] = set()

    @staticmethod
    def _now() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def list(self) -> list[NotificationRecord]:
        return list(reversed(self._items))

    def unread_count(self) -> int:
        return sum(1 for item in self._items if not item.read)

    def mark_read(self, ids: list[str]) -> None:
        id_set = set(ids)
        for idx, item in enumerate(self._items):
            if item.id in id_set:
                self._items[idx] = item.model_copy(update={"read": True})

    def add_signal(self, signal: SignalRecord) -> NotificationRecord | None:
        key = f"signal:{signal.id}"
        if key in self._dedup:
            return None
        self._dedup.add(key)
        item = NotificationRecord(
            id=uuid.uuid4().hex[:12],
            type=NotificationType.SIGNAL,
            title=f"{signal.signal_type} 信号",
            content=(
                f"策略 {signal.strategy_id} | 标的 {signal.symbol} | 周期 {signal.interval} | "
                f"时间 {signal.trigger_time} | 价格 {signal.trigger_price:.4f}"
            ),
            created_at=self._now(),
            read=False,
        )
        self._items.append(item)
        return item

    def add_system(self, title: str, content: str, dedup_key: str) -> NotificationRecord | None:
        if dedup_key in self._dedup:
            return None
        self._dedup.add(dedup_key)
        item_type = NotificationType.DATASOURCE if "datasource" in dedup_key else NotificationType.SYSTEM
        item = NotificationRecord(
            id=uuid.uuid4().hex[:12],
            type=item_type,
            title=title,
            content=content,
            created_at=self._now(),
            read=False,
        )
        self._items.append(item)
        return item
