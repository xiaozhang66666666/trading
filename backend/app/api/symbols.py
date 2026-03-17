from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_symbol_service, get_symbol_view_assembler, get_watchlist_service
from app.core.models import SymbolView, WatchlistAction
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
