from __future__ import annotations

from app.core.models import SystemSettings


class SystemSettingsService:
    def __init__(self) -> None:
        self._settings = SystemSettings()

    def get(self) -> SystemSettings:
        return self._settings

    def update(self, payload: SystemSettings) -> SystemSettings:
        self._settings = payload
        return self._settings
