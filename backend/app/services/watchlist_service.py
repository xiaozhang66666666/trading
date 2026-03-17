from __future__ import annotations


class WatchlistService:
    def __init__(self) -> None:
        # 首版先用内存实现，后续任务再迁移数据库。
        self._symbols: set[str] = set()

    def list_symbols(self) -> list[str]:
        return sorted(self._symbols)

    def add(self, symbol: str) -> None:
        self._symbols.add(symbol.upper())

    def remove(self, symbol: str) -> None:
        self._symbols.discard(symbol.upper())
