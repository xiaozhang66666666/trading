"""Concrete free data providers (Yahoo + Binance + CoinGecko)."""

from __future__ import annotations

import io
import requests
import pandas as pd
import yfinance as yf

from market_signal_system.data.base import DataProvider


class YahooFinanceProvider(DataProvider):
    """Yahoo provider via yfinance (used for QQQ)."""

    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raw = yf.download(
            tickers=symbol,
            start=start.tz_convert("UTC").tz_localize(None),
            end=end.tz_convert("UTC").tz_localize(None),
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if raw.empty:
            raise ValueError(f"YahooFinanceProvider empty data for {symbol}.")

        if isinstance(raw.columns, pd.MultiIndex):
            # yfinance can return MultiIndex columns even for single ticker.
            raw.columns = [str(col[0]).lower() for col in raw.columns]
        else:
            raw.columns = [str(col).lower() for col in raw.columns]

        df = raw.rename(
            columns={
                "adj close": "adj_close",
            }
        )
        df.index = pd.to_datetime(df.index, utc=True)
        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"YahooFinanceProvider missing columns {missing} for {symbol}.")
        df = df[required].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df


class StooqDailyProvider(DataProvider):
    """Stooq CSV daily provider (fallback for ETFs/stocks)."""

    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.symbol_map = {
            "QQQ": "qqq.us",
        }

    def _resolve_symbol(self, symbol: str) -> str:
        key = symbol.strip().upper()
        return self.symbol_map.get(key, symbol.strip().lower())

    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError(f"StooqDailyProvider unsupported interval: {interval}")

        resp = requests.get(
            self.BASE_URL,
            params={"s": self._resolve_symbol(symbol), "i": "d"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"StooqDailyProvider HTTP {resp.status_code}: {resp.text[:200]}")

        raw = pd.read_csv(io.StringIO(resp.text))
        if raw.empty:
            raise ValueError(f"StooqDailyProvider empty data for {symbol}.")
        raw.columns = [str(col).strip().lower() for col in raw.columns]
        required = ["date", "open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in raw.columns]
        if missing:
            raise ValueError(f"StooqDailyProvider missing columns {missing} for {symbol}.")

        raw["date"] = pd.to_datetime(raw["date"], utc=True, errors="coerce")
        frame = raw.dropna(subset=["date"]).set_index("date")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        frame[numeric_cols] = frame[numeric_cols].apply(pd.to_numeric, errors="coerce")
        frame = frame.dropna(subset=["open", "high", "low", "close"])
        frame = frame[numeric_cols].sort_index()
        frame = frame[(frame.index >= start) & (frame.index <= end)]
        if frame.empty:
            raise ValueError(f"StooqDailyProvider empty data for {symbol} in range.")
        return frame


class BinanceSpotProvider(DataProvider):
    """Binance public kline provider (mainly for crypto symbols)."""

    BASE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    @staticmethod
    def _map_interval(interval: str) -> str:
        mapping = {
            "1d": "1d",
            "1h": "1h",
            "4h": "4h",
            "1w": "1w",
        }
        if interval not in mapping:
            raise ValueError(f"BinanceSpotProvider unsupported interval: {interval}")
        return mapping[interval]

    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        binance_interval = self._map_interval(interval)
        start_ms = int(start.tz_convert("UTC").timestamp() * 1000)
        end_ms = int(end.tz_convert("UTC").timestamp() * 1000)
        rows: list[list[object]] = []
        cursor = start_ms

        while cursor < end_ms:
            resp = requests.get(
                self.BASE_URL,
                params={
                    "symbol": symbol.upper(),
                    "interval": binance_interval,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1000,
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"BinanceSpotProvider HTTP {resp.status_code}: {resp.text[:200]}")
            chunk = resp.json()
            if not isinstance(chunk, list):
                raise RuntimeError("BinanceSpotProvider invalid response payload.")
            if not chunk:
                break
            rows.extend(chunk)
            next_open_ms = int(chunk[-1][0]) + 1
            if next_open_ms <= cursor:
                break
            cursor = next_open_ms
            if len(chunk) < 1000:
                break

        if not rows:
            raise ValueError(f"BinanceSpotProvider empty data for {symbol}.")

        frame = pd.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        frame = frame.set_index("open_time")
        numeric_cols = ["open", "high", "low", "close", "volume"]
        frame[numeric_cols] = frame[numeric_cols].astype(float)
        frame = frame[numeric_cols].sort_index()
        frame = frame[(frame.index >= start) & (frame.index <= end)]
        if frame.empty:
            raise ValueError(f"BinanceSpotProvider empty data for {symbol} in range.")
        return frame


class CoinGeckoProvider(DataProvider):
    """CoinGecko market chart range provider (crypto fallback)."""

    BASE_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self.symbol_map = {
            "ETH": "ethereum",
            "ETHUSD": "ethereum",
            "ETHUSDT": "ethereum",
        }

    @staticmethod
    def _map_interval(interval: str) -> str:
        mapping = {
            "1d": "1D",
            "1h": "1H",
            "4h": "4H",
        }
        if interval not in mapping:
            raise ValueError(f"CoinGeckoProvider unsupported interval: {interval}")
        return mapping[interval]

    def _resolve_coin_id(self, symbol: str) -> str:
        key = symbol.strip().upper()
        if key in self.symbol_map:
            return self.symbol_map[key]
        return symbol.strip().lower()

    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        coin_id = self._resolve_coin_id(symbol)
        start_utc = start.tz_convert("UTC")
        end_utc = end.tz_convert("UTC")
        if end_utc <= start_utc:
            raise ValueError("end must be greater than start.")

        resp = requests.get(
            self.BASE_URL.format(coin_id=coin_id),
            params={
                "vs_currency": "usd",
                "from": int(start_utc.timestamp()),
                "to": int(end_utc.timestamp()),
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"CoinGeckoProvider HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        if not isinstance(payload, dict):
            raise RuntimeError("CoinGeckoProvider invalid response payload.")

        prices = payload.get("prices", [])
        total_volumes = payload.get("total_volumes", [])
        if not prices:
            raise ValueError(f"CoinGeckoProvider empty prices for {symbol}.")

        price_df = pd.DataFrame(prices, columns=["timestamp_ms", "price"])
        price_df["timestamp"] = pd.to_datetime(price_df["timestamp_ms"], unit="ms", utc=True)
        price_df = price_df.set_index("timestamp")
        price_series = price_df["price"].astype(float)

        vol_df = pd.DataFrame(total_volumes, columns=["timestamp_ms", "volume"])
        if vol_df.empty:
            volume_series = pd.Series(0.0, index=price_series.index, dtype=float)
        else:
            vol_df["timestamp"] = pd.to_datetime(vol_df["timestamp_ms"], unit="ms", utc=True)
            vol_df = vol_df.set_index("timestamp")
            volume_series = vol_df["volume"].astype(float).reindex(price_series.index).ffill().fillna(0.0)

        resample_rule = self._map_interval(interval)
        ohlc = price_series.resample(resample_rule).ohlc().dropna(how="all")
        volume = volume_series.resample(resample_rule).sum().rename("volume")

        frame = ohlc.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})
        frame = frame.join(volume, how="left")
        frame["volume"] = frame["volume"].fillna(0.0)
        frame = frame[["open", "high", "low", "close", "volume"]].sort_index()
        frame = frame[(frame.index >= start_utc) & (frame.index <= end_utc)]
        if frame.empty:
            raise ValueError(f"CoinGeckoProvider empty data for {symbol} in range.")
        return frame
