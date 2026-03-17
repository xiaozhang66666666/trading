from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_run_instance_service,
    get_signal_engine_service,
    get_strategy_service,
    get_symbol_service,
)
from app.core.models import SignalRecord
from app.services.run_instance_service import RunInstanceService
from app.services.signal_engine_service import SignalEngineService
from app.services.strategy_service import StrategyService
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/v1/signal-engine", tags=["signal-engine"])


@router.post("/tick", response_model=list[SignalRecord])
async def tick_signal_engine(
    run_service: RunInstanceService = Depends(get_run_instance_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    symbol_service: SymbolService = Depends(get_symbol_service),
    engine_service: SignalEngineService = Depends(get_signal_engine_service),
) -> list[SignalRecord]:
    runs = run_service.list()
    strategies = {item.id: item for item in strategy_service.list()}
    symbols = {item.code: item for item in symbol_service.search("")}
    return await engine_service.tick(runs=runs, strategy_map=strategies, symbol_map=symbols)


@router.get("/signals", response_model=list[SignalRecord])
def list_signals(engine_service: SignalEngineService = Depends(get_signal_engine_service)) -> list[SignalRecord]:
    return engine_service.list_signals()
