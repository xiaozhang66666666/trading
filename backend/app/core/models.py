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
