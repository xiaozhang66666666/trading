from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_system_health_service, get_system_settings_service
from app.core.models import SystemHealth, SystemSettings
from app.services.system_health_service import SystemHealthService
from app.services.system_settings_service import SystemSettingsService

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/settings", response_model=SystemSettings)
def get_settings(service: SystemSettingsService = Depends(get_system_settings_service)) -> SystemSettings:
    return service.get()


@router.put("/settings", response_model=SystemSettings)
def update_settings(
    payload: SystemSettings,
    service: SystemSettingsService = Depends(get_system_settings_service),
) -> SystemSettings:
    return service.update(payload)


@router.get("/health", response_model=SystemHealth)
async def health_check(service: SystemHealthService = Depends(get_system_health_service)) -> SystemHealth:
    return await service.check()
