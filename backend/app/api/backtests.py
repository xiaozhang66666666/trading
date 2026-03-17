from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_backtest_service, get_strategy_service, get_symbol_service
from app.core.models import BacktestRequest, BacktestResult
from app.services.backtest_service import BacktestService
from app.services.strategy_service import StrategyService
from app.services.symbol_service import SymbolService

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    payload: BacktestRequest,
    symbol_service: SymbolService = Depends(get_symbol_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> BacktestResult:
    symbol = symbol_service.get_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=404, detail="标的不存在")

    strategy = strategy_service.get(payload.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    return await backtest_service.run(payload, symbol=symbol, strategy=strategy)
