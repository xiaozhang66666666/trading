from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_signal_engine_service, get_trade_ledger_service
from app.core.models import PnlSummary, PositionLog, SignalRecord, TradeLog
from app.services.signal_engine_service import SignalEngineService
from app.services.trade_ledger_service import TradeLedgerService

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("/signals", response_model=list[SignalRecord])
def list_signal_logs(signal_service: SignalEngineService = Depends(get_signal_engine_service)) -> list[SignalRecord]:
    return signal_service.list_signals()


@router.get("/positions", response_model=list[PositionLog])
def list_position_logs(ledger: TradeLedgerService = Depends(get_trade_ledger_service)) -> list[PositionLog]:
    return ledger.list_position_logs()


@router.get("/trades", response_model=list[TradeLog])
def list_trade_logs(ledger: TradeLedgerService = Depends(get_trade_ledger_service)) -> list[TradeLog]:
    return ledger.list_trade_logs()


@router.get("/pnl", response_model=PnlSummary)
def get_pnl_summary(ledger: TradeLedgerService = Depends(get_trade_ledger_service)) -> PnlSummary:
    return ledger.pnl_summary()


@router.get("/export.csv")
def export_logs_csv(ledger: TradeLedgerService = Depends(get_trade_ledger_service)) -> Response:
    content = ledger.export_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="trade_logs.csv"'},
    )
