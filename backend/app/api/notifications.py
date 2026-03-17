from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_notification_service, get_symbol_service
from app.core.models import MarkReadPayload, NotificationRecord
from app.services.notification_service import NotificationService
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRecord])
def list_notifications(service: NotificationService = Depends(get_notification_service)) -> list[NotificationRecord]:
    return service.list()


@router.get("/unread-count")
def unread_count(service: NotificationService = Depends(get_notification_service)) -> dict[str, int]:
    return {"unread": service.unread_count()}


@router.post("/mark-read")
def mark_read(payload: MarkReadPayload, service: NotificationService = Depends(get_notification_service)) -> dict[str, str]:
    service.mark_read(payload.ids)
    return {"status": "ok"}


@router.post("/check-datasource")
async def check_datasource_status(
    symbol_service: SymbolService = Depends(get_symbol_service),
    service: NotificationService = Depends(get_notification_service),
) -> dict[str, int]:
    statuses = await symbol_service.datasource_status()
    created = 0
    for status in statuses:
        if status.state in {"DISCONNECTED", "RESERVED"}:
            note = service.add_system(
                title=f"数据源异常：{status.name}",
                content=status.detail,
                dedup_key=f"datasource:{status.name}:{status.state}",
            )
            if note:
                created += 1
    return {"created": created}
