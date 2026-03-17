from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_backtest_service, get_strategy_service, get_symbol_service
from app.core.models import (
    BacktestCompareRequest,
    BacktestCompareResult,
    BacktestRequest,
    BacktestResult,
    BacktestScanRequest,
    BacktestScanResult,
    PortfolioBacktestRequest,
    PortfolioBacktestResult,
)
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


@router.post("/scan", response_model=BacktestScanResult)
async def run_backtest_scan(
    payload: BacktestScanRequest,
    symbol_service: SymbolService = Depends(get_symbol_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> BacktestScanResult:
    symbol = symbol_service.get_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=404, detail="标的不存在")

    strategy = strategy_service.get(payload.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    return await backtest_service.scan(payload, symbol=symbol, strategy=strategy)


@router.post("/compare", response_model=BacktestCompareResult)
async def run_backtest_compare(
    payload: BacktestCompareRequest,
    symbol_service: SymbolService = Depends(get_symbol_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> BacktestCompareResult:
    symbol = symbol_service.get_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=404, detail="标的不存在")

    strategies = []
    for strategy_id in payload.strategy_ids:
        strategy = strategy_service.get(strategy_id)
        if strategy:
            strategies.append(strategy)
    if not strategies:
        raise HTTPException(status_code=404, detail="策略不存在")

    return await backtest_service.compare(payload, symbol=symbol, strategies=strategies)


@router.post("/portfolio", response_model=PortfolioBacktestResult)
async def run_portfolio_backtest(
    payload: PortfolioBacktestRequest,
    symbol_service: SymbolService = Depends(get_symbol_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
    backtest_service: BacktestService = Depends(get_backtest_service),
) -> PortfolioBacktestResult:
    strategy = strategy_service.get(payload.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    symbols = []
    for code in payload.symbols:
        symbol = symbol_service.get_symbol(code)
        if symbol:
            symbols.append(symbol)
    if not symbols:
        raise HTTPException(status_code=404, detail="标的不存在")

    return await backtest_service.run_portfolio(payload, symbols=symbols, strategy=strategy)
