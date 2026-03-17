from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_notification_service,
    get_run_instance_service,
    get_signal_engine_service,
    get_strategy_service,
    get_symbol_service,
    get_trade_ledger_service,
)
from app.core.models import SignalRecord
from app.services.run_instance_service import RunInstanceService
from app.services.signal_engine_service import SignalEngineService
from app.services.strategy_service import StrategyService
from app.services.symbol_service import SymbolService
from app.services.notification_service import NotificationService
from app.services.trade_ledger_service import TradeLedgerService

router = APIRouter(prefix="/api/v1/signal-engine", tags=["signal-engine"])


@router.post("/tick", response_model=list[SignalRecord])
async def tick_signal_engine(
    run_service: RunInstanceService = Depends(get_run_instance_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    symbol_service: SymbolService = Depends(get_symbol_service),
    engine_service: SignalEngineService = Depends(get_signal_engine_service),
    notification_service: NotificationService = Depends(get_notification_service),
    ledger_service: TradeLedgerService = Depends(get_trade_ledger_service),
) -> list[SignalRecord]:
    runs = run_service.list()
    strategies = {item.id: item for item in strategy_service.list()}
    symbols = {item.code: item for item in symbol_service.search("")}
    created = await engine_service.tick(runs=runs, strategy_map=strategies, symbol_map=symbols)
    for signal in created:
        notification_service.add_signal(signal)
        ledger_service.process_signal(signal)
    return created


@router.get("/signals", response_model=list[SignalRecord])
def list_signals(engine_service: SignalEngineService = Depends(get_signal_engine_service)) -> list[SignalRecord]:
    return engine_service.list_signals()
