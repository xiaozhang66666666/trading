from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.models import DataSnapshot, DataState, Kline, MarketQuote
from app.services.data_sources.base import BaseDataSource


class _AlpacaProvider:
    _BASE_URL = "https://data.alpaca.markets/v2"

    def __init__(self) -> None:
        self._key = os.getenv("ALPACA_API_KEY", "")
        self._secret = os.getenv("ALPACA_API_SECRET", "")

    @property
    def configured(self) -> bool:
        return bool(self._key and self._secret)

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._key,
            "APCA-API-SECRET-KEY": self._secret,
        }

    async def quote(self, symbol: str) -> MarketQuote | None:
        if not self.configured:
            return None
        async with httpx.AsyncClient(timeout=5.0) as client:
            trade_resp = await client.get(
                f"{self._BASE_URL}/stocks/{symbol}/trades/latest",
                headers=self._headers(),
                params={"feed": "iex"},
            )
            quote_resp = await client.get(
                f"{self._BASE_URL}/stocks/{symbol}/quotes/latest",
                headers=self._headers(),
                params={"feed": "iex"},
            )
            trade_resp.raise_for_status()
            quote_resp.raise_for_status()
        trade_data = trade_resp.json().get("trade", {})
        quote_data = quote_resp.json().get("quote", {})
        last = float(trade_data.get("p", 0.0))
        bid = float(quote_data.get("bp", last))
        ask = float(quote_data.get("ap", last))
        now = datetime.now(tz=timezone.utc).isoformat()
        return MarketQuote(
            symbol=symbol,
            last=last,
            change=0.0,
            change_percent=0.0,
            high=max(last, bid, ask),
            low=min(last, bid, ask),
            volume=float(trade_data.get("s", 0.0)),
            timestamp=now,
            state=DataState.REALTIME,
            detail="Alpaca IEX 实时",
        )

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline] | None:
        if not self.configured:
            return None
        timeframe_map = {
            "1m": "1Min",
            "5m": "5Min",
            "15m": "15Min",
            "1h": "1Hour",
            "4h": "4Hour",
            "1d": "1Day",
        }
        timeframe = timeframe_map.get(interval, "15Min")
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                f"{self._BASE_URL}/stocks/{symbol}/bars",
                headers=self._headers(),
                params={"timeframe": timeframe, "limit": min(max(limit, 30), 500), "feed": "iex"},
            )
            response.raise_for_status()
            payload = response.json()
        bars = payload.get("bars", [])
        candles: list[Kline] = []
        for item in bars:
            open_time = item.get("t")
            close_time = datetime.fromisoformat(open_time.replace("Z", "+00:00")) + timedelta(minutes=1)
            candles.append(
                Kline(
                    open_time=open_time,
                    close_time=close_time.isoformat(),
                    open=float(item.get("o", 0.0)),
                    high=float(item.get("h", 0.0)),
                    low=float(item.get("l", 0.0)),
                    close=float(item.get("c", 0.0)),
                    volume=float(item.get("v", 0.0)),
                )
            )
        return candles


class _TwelveDataProvider:
    _BASE_URL = "https://api.twelvedata.com"

    def __init__(self) -> None:
        self._key = os.getenv("TWELVE_DATA_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def quote(self, symbol: str) -> MarketQuote | None:
        if not self.configured:
            return None
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{self._BASE_URL}/quote",
                params={"symbol": symbol, "apikey": self._key},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code"):
            raise ValueError(payload.get("message", "TwelveData quote 错误"))

        last = float(payload.get("close", payload.get("price", 0.0)))
        prev_close = float(payload.get("previous_close", last))
        change = last - prev_close
        change_percent = (change / prev_close * 100.0) if prev_close else 0.0
        return MarketQuote(
            symbol=symbol,
            last=last,
            change=change,
            change_percent=change_percent,
            high=float(payload.get("high", last)),
            low=float(payload.get("low", last)),
            volume=float(payload.get("volume", 0.0)),
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            state=DataState.DELAYED,
            detail="Twelve Data 准实时",
        )

    async def klines(self, symbol: str, interval: str, limit: int) -> list[Kline] | None:
        if not self.configured:
            return None

        interval_map = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "1h": "1h",
            "4h": "4h",
            "1d": "1day",
        }
        mapped = interval_map.get(interval, "15min")
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                f"{self._BASE_URL}/time_series",
                params={
                    "symbol": symbol,
                    "interval": mapped,
                    "outputsize": min(max(limit, 30), 500),
                    "apikey": self._key,
                },
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code"):
            raise ValueError(payload.get("message", "TwelveData time_series 错误"))

        values = payload.get("values", [])
        candles: list[Kline] = []
        for row in reversed(values):
            start = datetime.fromisoformat(row["datetime"]).replace(tzinfo=timezone.utc)
            candles.append(
                Kline(
                    open_time=start.isoformat(),
                    close_time=(start + timedelta(minutes=1)).isoformat(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        return candles


class UsEquityRealtimePlaceholderDataSource(BaseDataSource):
    """美股 provider 适配层：优先 Alpaca，失败回退 Twelve Data。"""

    name = "us_equity_realtime"

    def __init__(self) -> None:
        self._alpaca = _AlpacaProvider()
        self._twelve = _TwelveDataProvider()

    def _fallback_quote(self, symbol: str, reason: str) -> MarketQuote:
        now = datetime.now(tz=timezone.utc)
        seed = sum(ord(ch) for ch in symbol)
        base = 100 + seed % 200
        return MarketQuote(
            symbol=symbol,
            last=float(base),
            change=0.0,
            change_percent=0.0,
            high=float(base * 1.01),
            low=float(base * 0.99),
            volume=0.0,
            timestamp=now.isoformat(),
            state=DataState.DISCONNECTED,
            detail=f"美股数据源不可用，当前为占位行情：{reason}",
        )

    def _fallback_klines(self, symbol: str, limit: int) -> list[Kline]:
        now = datetime.now(tz=timezone.utc)
        seed = float(100 + (sum(ord(ch) for ch in symbol) % 100))
        candles: list[Kline] = []
        for i in range(limit):
            open_time = now - timedelta(minutes=limit - i)
            wave = ((i % 8) - 4) * 0.15
            open_price = seed + wave
            close_price = open_price + ((i % 3) - 1) * 0.08
            high = max(open_price, close_price) + 0.15
            low = min(open_price, close_price) - 0.15
            candles.append(
                Kline(
                    open_time=open_time.isoformat(),
                    close_time=(open_time + timedelta(minutes=1)).isoformat(),
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close_price, 4),
                    volume=0.0,
                )
            )
        return candles

    @staticmethod
    def _safe_text(exc: Exception) -> str:
        return str(exc).replace("\n", " ")

    async def fetch_snapshot(self, symbol: str) -> DataSnapshot:
        quote = await self.fetch_quote(symbol)
        return DataSnapshot(state=quote.state, detail=quote.detail, last_price=quote.last)

    async def health_check(self) -> DataSnapshot:
        if self._alpaca.configured:
            return DataSnapshot(
                state=DataState.REALTIME,
                detail="美股通道：Alpaca 已配置（IEX feed）",
                last_price=None,
            )
        if self._twelve.configured:
            return DataSnapshot(
                state=DataState.DELAYED,
                detail="美股通道：Alpaca 未配置，回退 Twelve Data",
                last_price=None,
            )
        return DataSnapshot(
            state=DataState.RESERVED,
            detail="美股通道未配置（请设置 ALPACA_API_KEY / ALPACA_API_SECRET 或 TWELVE_DATA_API_KEY）",
            last_price=None,
        )

    async def fetch_quote(self, symbol: str) -> MarketQuote:
        errors: list[str] = []
        if self._alpaca.configured:
            try:
                quote = await self._alpaca.quote(symbol)
                if quote:
                    return quote
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Alpaca: {self._safe_text(exc)}")

        if self._twelve.configured:
            try:
                quote = await self._twelve.quote(symbol)
                if quote:
                    return quote
            except Exception as exc:  # noqa: BLE001
                errors.append(f"TwelveData: {self._safe_text(exc)}")

        reason = "；".join(errors) if errors else "未配置可用 provider"
        return self._fallback_quote(symbol, reason)

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 200) -> list[Kline]:
        errors: list[str] = []
        if self._alpaca.configured:
            try:
                bars = await self._alpaca.klines(symbol, interval, limit)
                if bars:
                    return bars
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Alpaca: {self._safe_text(exc)}")

        if self._twelve.configured:
            try:
                bars = await self._twelve.klines(symbol, interval, limit)
                if bars:
                    return bars
            except Exception as exc:  # noqa: BLE001
                errors.append(f"TwelveData: {self._safe_text(exc)}")

        # provider 失败时仍返回占位 K 线，确保页面可加载并显式显示断连态。
        return self._fallback_klines(symbol, min(max(limit, 30), 300))
