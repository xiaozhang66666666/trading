from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_strategy_service
from app.core.models import StrategyPayload, StrategyRecord
from app.services.strategy_service import StrategyService, StrategyValidationError

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("/templates")
def list_templates(service: StrategyService = Depends(get_strategy_service)) -> list[dict[str, str]]:
    return service.templates()


@router.get("", response_model=list[StrategyRecord])
def list_strategies(service: StrategyService = Depends(get_strategy_service)) -> list[StrategyRecord]:
    return service.list()


@router.post("", response_model=StrategyRecord)
def create_strategy(payload: StrategyPayload, service: StrategyService = Depends(get_strategy_service)) -> StrategyRecord:
    try:
        return service.create(payload)
    except StrategyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/{strategy_id}", response_model=StrategyRecord)
def update_strategy(
    strategy_id: str,
    payload: StrategyPayload,
    service: StrategyService = Depends(get_strategy_service),
) -> StrategyRecord:
    try:
        return service.update(strategy_id, payload)
    except StrategyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="策略不存在") from exc


@router.post("/{strategy_id}/copy", response_model=StrategyRecord)
def copy_strategy(strategy_id: str, service: StrategyService = Depends(get_strategy_service)) -> StrategyRecord:
    try:
        return service.copy(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="策略不存在") from exc


@router.get("/{strategy_id}/versions")
def list_versions(strategy_id: str, service: StrategyService = Depends(get_strategy_service)):
    record = service.get(strategy_id)
    if not record:
        raise HTTPException(status_code=404, detail="策略不存在")
    return record.versions


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str, service: StrategyService = Depends(get_strategy_service)) -> dict[str, str]:
    service.delete(strategy_id)
    return {"status": "ok"}
