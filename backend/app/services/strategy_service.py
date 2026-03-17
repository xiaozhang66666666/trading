from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone

from app.core.models import StrategyPayload, StrategyRecord, StrategyTemplate, StrategyVersion


class StrategyValidationError(Exception):
    pass


class StrategyService:
    """策略中心内存服务：T1 先完成闭环，后续切数据库。"""

    def __init__(self) -> None:
        self._records: dict[str, StrategyRecord] = {}

    @staticmethod
    def templates() -> list[dict[str, str]]:
        return [
            {"code": StrategyTemplate.MA_CROSS, "name": "MA 均线交叉"},
            {"code": StrategyTemplate.RSI_REVERSAL, "name": "RSI 超买超卖"},
            {"code": StrategyTemplate.MACD_TREND, "name": "MACD 趋势"},
            {"code": StrategyTemplate.BOLL_BREAKOUT, "name": "布林带突破/回归"},
            {"code": StrategyTemplate.RANGE_BREAKOUT, "name": "区间突破"},
        ]

    @staticmethod
    def validate_payload(payload: StrategyPayload) -> None:
        if payload.template not in StrategyTemplate:
            raise StrategyValidationError("不支持的策略模板")

        if payload.take_profit <= 0 or payload.stop_loss <= 0 or payload.position_size <= 0:
            raise StrategyValidationError("止盈/止损/仓位参数必须大于 0")

        try:
            parsed = json.loads(payload.json_dsl)
        except json.JSONDecodeError as exc:
            raise StrategyValidationError(f"JSON DSL 非法: {exc}") from exc

        required = [
            "strategy",
            "indicators",
            "conditions",
            "entry_long",
            "exit_long",
            "entry_short",
            "exit_short",
            "risk",
        ]
        missing = [key for key in required if key not in parsed]
        if missing:
            raise StrategyValidationError(f"JSON DSL 缺少字段: {', '.join(missing)}")

    def list(self) -> list[StrategyRecord]:
        return sorted(self._records.values(), key=lambda item: item.updated_at, reverse=True)

    def get(self, strategy_id: str) -> StrategyRecord | None:
        return self._records.get(strategy_id)

    def create(self, payload: StrategyPayload) -> StrategyRecord:
        self.validate_payload(payload)
        strategy_id = uuid.uuid4().hex[:10]
        created_at = datetime.now(tz=timezone.utc).isoformat()
        first_version = StrategyVersion(version=1, created_at=created_at, payload=payload)
        record = StrategyRecord(
            id=strategy_id,
            name=payload.name,
            current_version=1,
            updated_at=created_at,
            latest_payload=payload,
            versions=[first_version],
        )
        self._records[strategy_id] = record
        return record

    def update(self, strategy_id: str, payload: StrategyPayload) -> StrategyRecord:
        record = self._records.get(strategy_id)
        if not record:
            raise KeyError(strategy_id)

        self.validate_payload(payload)
        next_version = record.current_version + 1
        updated_at = datetime.now(tz=timezone.utc).isoformat()
        version = StrategyVersion(version=next_version, created_at=updated_at, payload=payload)
        versions = [*record.versions, version]
        updated = record.model_copy(
            update={
                "name": payload.name,
                "current_version": next_version,
                "updated_at": updated_at,
                "latest_payload": payload,
                "versions": versions,
            }
        )
        self._records[strategy_id] = updated
        return updated

    def delete(self, strategy_id: str) -> None:
        self._records.pop(strategy_id, None)

    def copy(self, strategy_id: str) -> StrategyRecord:
        record = self._records.get(strategy_id)
        if not record:
            raise KeyError(strategy_id)
        payload = copy.deepcopy(record.latest_payload)
        payload.name = f"{payload.name}-副本"
        return self.create(payload)
