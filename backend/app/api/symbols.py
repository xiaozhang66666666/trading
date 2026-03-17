from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import (
    get_history_data_service,
    get_market_data_service,
    get_symbol_service,
    get_symbol_view_assembler,
    get_watchlist_service,
)
from app.core.models import HistoryDataset, Kline, MarketOverview, SymbolView, WatchlistAction
from app.services.history_data_service import HistoryDataService
from app.services.market_data_service import MarketDataService
from app.services.symbol_service import SymbolService
from app.services.symbol_view_assembler import SymbolViewAssembler
from app.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/api/v1", tags=["symbols"])


@router.get("/symbols/search", response_model=list[SymbolView])
async def search_symbols(
    q: str = "",
    symbol_service: SymbolService = Depends(get_symbol_service),
    assembler: SymbolViewAssembler = Depends(get_symbol_view_assembler),
) -> list[SymbolView]:
    symbols = symbol_service.search(q)
    return await assembler.build_many(symbols)


@router.get("/watchlist", response_model=list[SymbolView])
async def get_watchlist(
    symbol_service: SymbolService = Depends(get_symbol_service),
    watchlist: WatchlistService = Depends(get_watchlist_service),
    assembler: SymbolViewAssembler = Depends(get_symbol_view_assembler),
) -> list[SymbolView]:
    symbols = []
    for code in watchlist.list_symbols():
        symbol = symbol_service.get_symbol(code)
        if symbol:
            symbols.append(symbol)
    return await assembler.build_many(symbols)


@router.post("/watchlist", response_model=list[SymbolView])
async def add_watchlist(
    payload: WatchlistAction,
    symbol_service: SymbolService = Depends(get_symbol_service),
    watchlist: WatchlistService = Depends(get_watchlist_service),
    assembler: SymbolViewAssembler = Depends(get_symbol_view_assembler),
) -> list[SymbolView]:
    symbol = symbol_service.get_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=404, detail="标的不存在")

    watchlist.add(symbol.code)
    return await get_watchlist(symbol_service, watchlist, assembler)


@router.delete("/watchlist/{symbol}", response_model=list[SymbolView])
async def remove_watchlist(
    symbol: str,
    symbol_service: SymbolService = Depends(get_symbol_service),
    watchlist: WatchlistService = Depends(get_watchlist_service),
    assembler: SymbolViewAssembler = Depends(get_symbol_view_assembler),
) -> list[SymbolView]:
    watchlist.remove(symbol)
    return await get_watchlist(symbol_service, watchlist, assembler)


@router.get("/data-sources/status")
async def get_data_source_status(
    symbol_service: SymbolService = Depends(get_symbol_service),
):
    return await symbol_service.datasource_status()


@router.get("/market/overview", response_model=MarketOverview)
async def get_market_overview(
    symbol: str,
    symbol_service: SymbolService = Depends(get_symbol_service),
    market_data: MarketDataService = Depends(get_market_data_service),
) -> MarketOverview:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    return await market_data.get_overview(symbol_info)


@router.get("/market/klines", response_model=list[Kline])
async def get_market_klines(
    symbol: str,
    interval: str = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=200, ge=30, le=500),
    symbol_service: SymbolService = Depends(get_symbol_service),
    market_data: MarketDataService = Depends(get_market_data_service),
) -> list[Kline]:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    return await market_data.get_klines(symbol_info, interval=interval, limit=limit)


@router.get("/history/klines", response_model=HistoryDataset)
async def get_history_klines(
    symbol: str,
    interval: str = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=500, ge=30, le=500),
    refresh: bool = Query(default=False),
    symbol_service: SymbolService = Depends(get_symbol_service),
    history_service: HistoryDataService = Depends(get_history_data_service),
) -> HistoryDataset:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    return await history_service.fetch_history(symbol=symbol_info, interval=interval, limit=limit, force_refresh=refresh)


@router.post("/history/refresh", response_model=HistoryDataset)
async def refresh_history_klines(
    symbol: str,
    interval: str = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=500, ge=30, le=500),
    symbol_service: SymbolService = Depends(get_symbol_service),
    history_service: HistoryDataService = Depends(get_history_data_service),
) -> HistoryDataset:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    return await history_service.fetch_history(symbol=symbol_info, interval=interval, limit=limit, force_refresh=True)


@router.get("/history/download.csv")
async def download_history_csv(
    symbol: str,
    interval: str = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=500, ge=30, le=500),
    symbol_service: SymbolService = Depends(get_symbol_service),
    history_service: HistoryDataService = Depends(get_history_data_service),
) -> Response:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    dataset = await history_service.fetch_history(symbol=symbol_info, interval=interval, limit=limit)
    content = history_service.to_csv_bytes(dataset)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{symbol.upper()}_{interval}.csv"'},
    )


@router.get("/history/download.parquet")
async def download_history_parquet(
    symbol: str,
    interval: str = Query(default="15m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=500, ge=30, le=500),
    symbol_service: SymbolService = Depends(get_symbol_service),
    history_service: HistoryDataService = Depends(get_history_data_service),
) -> Response:
    symbol_info = symbol_service.get_symbol(symbol)
    if not symbol_info:
        raise HTTPException(status_code=404, detail="标的不存在")
    dataset = await history_service.fetch_history(symbol=symbol_info, interval=interval, limit=limit)
    try:
        content = history_service.to_parquet_bytes(dataset)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Parquet 导出失败，请安装 pyarrow 或 fastparquet: {exc}") from exc
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{symbol.upper()}_{interval}.parquet"'},
    )
