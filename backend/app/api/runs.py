from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_run_instance_service
from app.core.models import RunInstance, RunInstancePayload, RunStatus
from app.services.run_instance_service import RunInstanceService

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("", response_model=list[RunInstance])
def list_runs(service: RunInstanceService = Depends(get_run_instance_service)) -> list[RunInstance]:
    return service.list()


@router.post("", response_model=RunInstance)
def create_run(payload: RunInstancePayload, service: RunInstanceService = Depends(get_run_instance_service)) -> RunInstance:
    return service.create(payload)


@router.put("/{instance_id}", response_model=RunInstance)
def update_run(
    instance_id: str,
    payload: RunInstancePayload,
    service: RunInstanceService = Depends(get_run_instance_service),
) -> RunInstance:
    try:
        return service.update(instance_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行实例不存在") from exc


@router.post("/{instance_id}/copy", response_model=RunInstance)
def copy_run(instance_id: str, service: RunInstanceService = Depends(get_run_instance_service)) -> RunInstance:
    try:
        return service.copy(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行实例不存在") from exc


@router.post("/{instance_id}/start", response_model=RunInstance)
def start_run(instance_id: str, service: RunInstanceService = Depends(get_run_instance_service)) -> RunInstance:
    try:
        return service.set_status(instance_id, RunStatus.RUNNING)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行实例不存在") from exc


@router.post("/{instance_id}/pause", response_model=RunInstance)
def pause_run(instance_id: str, service: RunInstanceService = Depends(get_run_instance_service)) -> RunInstance:
    try:
        return service.set_status(instance_id, RunStatus.PAUSED)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行实例不存在") from exc


@router.post("/{instance_id}/stop", response_model=RunInstance)
def stop_run(instance_id: str, service: RunInstanceService = Depends(get_run_instance_service)) -> RunInstance:
    try:
        return service.set_status(instance_id, RunStatus.STOPPED)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="运行实例不存在") from exc


@router.delete("/{instance_id}")
def delete_run(instance_id: str, service: RunInstanceService = Depends(get_run_instance_service)) -> dict[str, str]:
    service.delete(instance_id)
    return {"status": "ok"}
