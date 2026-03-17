from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from app.core.models import RunInstance, RunInstancePayload, RunStatus


class RunInstanceService:
    def __init__(self) -> None:
        self._instances: dict[str, RunInstance] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(tz=timezone.utc).isoformat()

    def list(self) -> list[RunInstance]:
        return sorted(self._instances.values(), key=lambda item: item.updated_at, reverse=True)

    def get(self, instance_id: str) -> RunInstance | None:
        return self._instances.get(instance_id)

    def create(self, payload: RunInstancePayload) -> RunInstance:
        now = self._now()
        instance = RunInstance(
            id=uuid.uuid4().hex[:10],
            status=RunStatus.PENDING,
            created_at=now,
            updated_at=now,
            payload=payload,
        )
        self._instances[instance.id] = instance
        return instance

    def update(self, instance_id: str, payload: RunInstancePayload) -> RunInstance:
        instance = self.get(instance_id)
        if not instance:
            raise KeyError(instance_id)
        updated = instance.model_copy(update={"payload": payload, "updated_at": self._now()})
        self._instances[instance_id] = updated
        return updated

    def copy(self, instance_id: str) -> RunInstance:
        instance = self.get(instance_id)
        if not instance:
            raise KeyError(instance_id)
        payload = copy.deepcopy(instance.payload)
        payload.name = f"{payload.name}-副本"
        return self.create(payload)

    def delete(self, instance_id: str) -> None:
        self._instances.pop(instance_id, None)

    def set_status(self, instance_id: str, status: RunStatus) -> RunInstance:
        instance = self.get(instance_id)
        if not instance:
            raise KeyError(instance_id)
        updated = instance.model_copy(update={"status": status, "updated_at": self._now()})
        self._instances[instance_id] = updated
        return updated

    def batch_set_status(self, status: RunStatus, ids: list[str] | None = None, group_name: str = "") -> list[RunInstance]:
        targets: list[RunInstance] = []
        id_set = set(ids or [])
        for instance in self._instances.values():
            if id_set and instance.id not in id_set:
                continue
            if group_name and instance.payload.group_name != group_name:
                continue
            targets.append(instance)

        updated: list[RunInstance] = []
        for instance in targets:
            updated.append(self.set_status(instance.id, status))
        return updated

    def group_summary(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for instance in self._instances.values():
            group = instance.payload.group_name or "default"
            result[group] = result.get(group, 0) + 1
        return result
