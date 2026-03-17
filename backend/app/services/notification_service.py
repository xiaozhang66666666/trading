from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable
from urllib import request

from app.core.models import NotificationRecord, NotificationType, SignalRecord
from app.services.system_settings_service import SystemSettingsService


class NotificationService:
    def __init__(
        self,
        settings_service: SystemSettingsService | None = None,
        sender: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._items: list[NotificationRecord] = []
        self._dedup: set[str] = set()
        self._settings_service = settings_service
        self._sender = sender or self._default_sender
        self._throttle_marks: dict[str, float] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    @staticmethod
    def _default_sender(webhook_url: str, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=5) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                raise RuntimeError(f"飞书 webhook 响应异常: {status}")

    @staticmethod
    def _format_signal_content(signal: SignalRecord) -> str:
        return (
            f"策略 {signal.strategy_id} | 标的 {signal.symbol} | 周期 {signal.interval} | "
            f"时间 {signal.trigger_time} | 价格 {signal.trigger_price:.4f}"
        )

    def _build_feishu_payload(self, title: str, content: str) -> dict:
        return {
            "msg_type": "text",
            "content": {
                "text": f"{title}\n{content}\n发送时间：{self._now()}",
            },
        }

    def _allow_feishu(self, category: str, throttle_key: str) -> bool:
        if not self._settings_service:
            return False
        settings = self._settings_service.get()
        if not settings.feishu_enabled or not settings.feishu_webhook_url.strip():
            return False
        if category == "signal" and not settings.feishu_notify_signal:
            return False
        if category in {"system", "datasource"} and not settings.feishu_notify_system:
            return False

        now = time.time()
        last_sent = self._throttle_marks.get(throttle_key)
        if last_sent is not None and now - last_sent < max(settings.feishu_throttle_seconds, 0):
            return False
        self._throttle_marks[throttle_key] = now
        return True

    def _try_push_feishu(self, *, category: str, title: str, content: str, dedup_key: str, throttle_key: str) -> None:
        if not self._allow_feishu(category, throttle_key):
            return
        assert self._settings_service is not None
        webhook_url = self._settings_service.get().feishu_webhook_url.strip()
        try:
            self._sender(webhook_url, self._build_feishu_payload(title=title, content=content))
        except Exception as exc:  # noqa: BLE001
            self.add_system(
                title="飞书通知发送失败",
                content=f"{title} 推送失败：{exc}",
                dedup_key=f"feishu-send-error:{dedup_key}",
            )

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
        title = f"{signal.signal_type} 信号"
        content = self._format_signal_content(signal)
        item = NotificationRecord(
            id=uuid.uuid4().hex[:12],
            type=NotificationType.SIGNAL,
            title=title,
            content=content,
            created_at=self._now(),
            read=False,
        )
        self._items.append(item)
        self._try_push_feishu(
            category="signal",
            title=f"【开平仓信号】{title}",
            content=content,
            dedup_key=key,
            throttle_key=f"signal:{signal.run_instance_id}:{signal.signal_type}",
        )
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
        if not dedup_key.startswith("feishu-send-error:"):
            category = "datasource" if item_type == NotificationType.DATASOURCE else "system"
            self._try_push_feishu(
                category=category,
                title=f"【系统异常】{title}",
                content=content,
                dedup_key=dedup_key,
                throttle_key=f"{category}:{title}",
            )
        return item
