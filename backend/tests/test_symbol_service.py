import asyncio
import unittest

from app.core.models import DataSnapshot, DataState
from app.services.symbol_service import SymbolService


class _FakeSource:
    def __init__(self, detail: str) -> None:
        self._detail = detail

    async def health_check(self) -> DataSnapshot:
        return DataSnapshot(state=DataState.REALTIME, detail=self._detail)


class _FakeRegistry:
    def __init__(self) -> None:
        self._sources = {
            "binance": _FakeSource("binance ok"),
            "us_equity_realtime": _FakeSource("reserved"),
        }

    def all_sources(self):
        return self._sources


class SymbolServiceTest(unittest.TestCase):
    def test_search_can_find_required_symbols(self) -> None:
        service = SymbolService(registry=_FakeRegistry())
        symbols = service.search("QQ")
        codes = {item.code for item in symbols}
        self.assertIn("QQQ", codes)
        self.assertIn("TQQQ", codes)

        crypto = service.search("ETH")
        self.assertEqual([item.code for item in crypto], ["ETH"])

    def test_datasource_status_contains_binance_and_us_equity(self) -> None:
        service = SymbolService(registry=_FakeRegistry())
        result = asyncio.run(service.datasource_status())
        names = {item.name for item in result}
        self.assertIn("binance", names)
        self.assertIn("us_equity_realtime", names)


if __name__ == "__main__":
    unittest.main()
