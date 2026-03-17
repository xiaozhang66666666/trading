from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.models import DataSnapshot


class BaseDataSource(ABC):
    name: str

    @abstractmethod
    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        """读取单个标的的行情快照。"""

    @abstractmethod
    async def health_check(self) -> DataSnapshot:
        """用于状态面板的轻量健康检查。"""
