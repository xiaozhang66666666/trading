from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class SessionIntegrity(BaseModel):
    pre_market_ratio: float = 0.0
    regular_ratio: float = 0.0
    after_hours_ratio: float = 0.0
    checked_trading_day: str = ""
    issues: list[str] = Field(default_factory=list)


class KlineQualityReport(BaseModel):
    symbol: str
    interval: str
    total_points: int
    duplicate_points: int
    out_of_order_points: int
    missing_points: int
    filled_points: int
    invalid_price_points: int
    session_integrity: SessionIntegrity
    score: float
    level: str
    issues: list[str] = Field(default_factory=list)


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


class ScanRange(BaseModel):
    start: float
    end: float
    step: float


class BacktestScanRequest(BaseModel):
    strategy_id: str
    symbol: str
    interval: str = "15m"
    initial_capital: float = 100000
    fee_rate: ScanRange = Field(default_factory=lambda: ScanRange(start=0.0002, end=0.001, step=0.0002))
    slippage_rate: ScanRange = Field(default_factory=lambda: ScanRange(start=0.0002, end=0.001, step=0.0002))
    allow_long: bool = True
    allow_short: bool = True
    include_extended_hours: bool = False
    sort_by: str = "total_return"
    top_n: int = 20


class BacktestScanItem(BaseModel):
    fee_rate: float
    slippage_rate: float
    metrics: BacktestMetrics


class BacktestScanResult(BaseModel):
    symbol: str
    interval: str
    scanned_count: int
    sort_by: str
    items: list[BacktestScanItem]


class BacktestCompareRequest(BaseModel):
    strategy_ids: list[str]
    symbol: str
    interval: str = "15m"
    initial_capital: float = 100000
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0005
    allow_long: bool = True
    allow_short: bool = True
    include_extended_hours: bool = False
    sort_by: str = "total_return"


class BacktestCompareItem(BaseModel):
    strategy_id: str
    strategy_name: str
    metrics: BacktestMetrics


class BacktestCompareResult(BaseModel):
    symbol: str
    interval: str
    sort_by: str
    items: list[BacktestCompareItem]


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


class NotificationType(str, Enum):
    SIGNAL = "SIGNAL"
    SYSTEM = "SYSTEM"
    DATASOURCE = "DATASOURCE"


class NotificationRecord(BaseModel):
    id: str
    type: NotificationType
    title: str
    content: str
    created_at: str
    read: bool = False


class MarkReadPayload(BaseModel):
    ids: list[str]


class PositionLog(BaseModel):
    id: str
    run_instance_id: str
    symbol: str
    action: str
    position_side: str
    quantity: float
    price: float
    reason_snapshot: str
    timestamp: str


class TradeLog(BaseModel):
    id: str
    run_instance_id: str
    symbol: str
    side: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    realized_pnl: float
    reason_snapshot: str


class PnlSummary(BaseModel):
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float


class SystemSettings(BaseModel):
    preferred_us_provider: str = "alpaca"
    fallback_us_provider: str = "twelve_data"
    default_fee_rate: float = 0.0005
    default_slippage_rate: float = 0.0005
    timezone: str = "UTC"
    us_pre_market_start: str = "04:00"
    us_regular_start: str = "09:30"
    us_regular_end: str = "16:00"
    us_after_market_end: str = "20:00"
    feishu_enabled: bool = False
    feishu_webhook_url: str = ""
    feishu_notify_signal: bool = True
    feishu_notify_system: bool = True
    feishu_throttle_seconds: int = 60


class SystemHealth(BaseModel):
    api_status: str
    data_sources: list[DataSourceStatus]
    running_instances: int
    paused_instances: int
    stopped_instances: int
    errors: list[str]
