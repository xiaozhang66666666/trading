from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class MarketType(str, Enum):
    US_EQUITY = "US_EQUITY"
    CRYPTO = "CRYPTO"


class SessionType(str, Enum):
    PRE_MARKET = "PRE_MARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    ALWAYS_OPEN = "ALWAYS_OPEN"


class DataState(str, Enum):
    REALTIME = "REALTIME"
    DELAYED = "DELAYED"
    DISCONNECTED = "DISCONNECTED"
    RESERVED = "RESERVED"


class Symbol(BaseModel):
    code: str
    name: str
    market: MarketType
    datasource: str


class DataSourceStatus(BaseModel):
    name: str
    state: DataState
    detail: str
    checked_at: str


class SymbolView(BaseModel):
    code: str
    name: str
    market: MarketType
    datasource: str
    data_state: DataState
    data_detail: str
    session: SessionType
    session_label: str


class WatchlistAction(BaseModel):
    symbol: str


class DataSnapshot(BaseModel):
    state: DataState
    detail: str
    last_price: Optional[float] = None


class MarketQuote(BaseModel):
    symbol: str
    last: float
    change: float
    change_percent: float
    high: float
    low: float
    volume: float
    timestamp: str
    state: DataState
    detail: str


class Kline(BaseModel):
    open_time: str
    close_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketOverview(BaseModel):
    symbol: str
    market: MarketType
    session: SessionType
    session_label: str
    quote: MarketQuote


class HistoryQuery(BaseModel):
    symbol: str
    interval: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int = 500


class HistoryDataset(BaseModel):
    symbol: str
    interval: str
    source: str
    updated_at: str
    missing_points: int
    has_missing: bool
    candles: list[Kline]


class StrategyTemplate(str, Enum):
    MA_CROSS = "MA_CROSS"
    RSI_REVERSAL = "RSI_REVERSAL"
    MACD_TREND = "MACD_TREND"
    BOLL_BREAKOUT = "BOLL_BREAKOUT"
    RANGE_BREAKOUT = "RANGE_BREAKOUT"


class StrategyDirectionConfig(BaseModel):
    allow_long: bool = True
    allow_short: bool = True
    include_extended_hours: bool = False


class StrategyPayload(BaseModel):
    name: str
    template: StrategyTemplate
    interval: str
    open_condition: str
    close_condition: str
    take_profit: float
    stop_loss: float
    position_size: float
    direction: StrategyDirectionConfig
    json_dsl: str


class StrategyVersion(BaseModel):
    version: int
    created_at: str
    payload: StrategyPayload


class StrategyRecord(BaseModel):
    id: str
    name: str
    current_version: int
    updated_at: str
    latest_payload: StrategyPayload
    versions: list[StrategyVersion]


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str
    interval: str = "15m"
    initial_capital: float = 100000
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0005
    allow_long: bool = True
    allow_short: bool = True
    include_extended_hours: bool = False


class BacktestTrade(BaseModel):
    side: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    qty: float
    pnl: float
    reason: str


class EquityPoint(BaseModel):
    time: str
    equity: float


class BacktestMetrics(BaseModel):
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    profit_loss_ratio: float
    profit_factor: float


class BacktestResult(BaseModel):
    symbol: str
    interval: str
    metrics: BacktestMetrics
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class RunInstancePayload(BaseModel):
    name: str
    strategy_id: str
    symbol: str
    interval: str
    fee_rate: float
    slippage_rate: float
    risk_limit: float
    notify_in_app: bool = True


class RunInstance(BaseModel):
    id: str
    status: RunStatus
    created_at: str
    updated_at: str
    payload: RunInstancePayload


class SignalType(str, Enum):
    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"


class SignalRecord(BaseModel):
    id: str
    run_instance_id: str
    strategy_id: str
    symbol: str
    interval: str
    signal_type: SignalType
    trigger_time: str
    trigger_price: float
    reason_snapshot: str
