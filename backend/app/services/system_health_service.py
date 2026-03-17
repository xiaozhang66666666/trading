from __future__ import annotations

from app.core.models import RunStatus, SystemHealth
from app.services.run_instance_service import RunInstanceService
from app.services.symbol_service import SymbolService


class SystemHealthService:
    def __init__(self, symbol_service: SymbolService, run_service: RunInstanceService) -> None:
        self._symbol_service = symbol_service
        self._run_service = run_service

    async def check(self) -> SystemHealth:
        statuses = await self._symbol_service.datasource_status()
        runs = self._run_service.list()
        errors = []
        for status in statuses:
            if status.state in {"DISCONNECTED", "RESERVED"}:
                errors.append(f"数据源异常: {status.name} - {status.detail}")

        return SystemHealth(
            api_status="ok",
            data_sources=statuses,
            running_instances=sum(1 for item in runs if item.status == RunStatus.RUNNING),
            paused_instances=sum(1 for item in runs if item.status == RunStatus.PAUSED),
            stopped_instances=sum(1 for item in runs if item.status == RunStatus.STOPPED),
            errors=errors,
        )
