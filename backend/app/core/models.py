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
