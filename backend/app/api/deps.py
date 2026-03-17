from __future__ import annotations

from functools import lru_cache

from app.services.data_source_registry import DataSourceRegistry
from app.services.history_data_service import HistoryDataService
from app.services.market_data_service import MarketDataService
from app.services.market_session import MarketSessionService
from app.services.notification_service import NotificationService
from app.services.run_instance_service import RunInstanceService
from app.services.signal_engine_service import SignalEngineService
from app.services.strategy_service import StrategyService
from app.services.symbol_service import SymbolService
from app.services.system_health_service import SystemHealthService
from app.services.system_settings_service import SystemSettingsService
from app.services.trade_ledger_service import TradeLedgerService
from app.services.symbol_view_assembler import SymbolViewAssembler
from app.services.watchlist_service import WatchlistService


@lru_cache
def get_registry() -> DataSourceRegistry:
    return DataSourceRegistry()


@lru_cache
def get_symbol_service() -> SymbolService:
    return SymbolService(registry=get_registry())


@lru_cache
def get_watchlist_service() -> WatchlistService:
    return WatchlistService()


@lru_cache
def get_symbol_view_assembler() -> SymbolViewAssembler:
    return SymbolViewAssembler(registry=get_registry(), session_service=MarketSessionService())


@lru_cache
def get_market_data_service() -> MarketDataService:
    return MarketDataService(registry=get_registry(), session_service=MarketSessionService())


@lru_cache
def get_history_data_service() -> HistoryDataService:
    return HistoryDataService(market_data=get_market_data_service())


@lru_cache
def get_strategy_service() -> StrategyService:
    return StrategyService()


@lru_cache
def get_backtest_service() -> BacktestService:
    return BacktestService(market_data=get_market_data_service())


@lru_cache
def get_run_instance_service() -> RunInstanceService:
    return RunInstanceService()


@lru_cache
def get_signal_engine_service() -> SignalEngineService:
    return SignalEngineService(market_data=get_market_data_service())


@lru_cache
def get_notification_service() -> NotificationService:
    return NotificationService(settings_service=get_system_settings_service())


@lru_cache
def get_trade_ledger_service() -> TradeLedgerService:
    return TradeLedgerService()


@lru_cache
def get_system_settings_service() -> SystemSettingsService:
    return SystemSettingsService()


@lru_cache
def get_system_health_service() -> SystemHealthService:
    return SystemHealthService(symbol_service=get_symbol_service(), run_service=get_run_instance_service())
from app.services.backtest_service import BacktestService
