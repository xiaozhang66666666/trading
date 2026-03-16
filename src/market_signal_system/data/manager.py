"""Unified market data access with local cache + incremental updates."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from market_signal_system.data.base import DataProvider
from market_signal_system.data.providers import BinanceSpotProvider, CoinGeckoProvider, StooqDailyProvider, YahooFinanceProvider
from market_signal_system.utils.paths import CACHE_DIR, ensure_runtime_dirs


@dataclass
class SymbolConfig:
    providers: list[tuple[DataProvider, str]]


class DataManager:
    """Unified entry for history fetch and cache maintenance."""

    _WEEKLY_INTERVALS = {"1w", "1wk", "1week"}

    def __init__(self) -> None:
        ensure_runtime_dirs()
        timeout = self._env_float("MSS_DATA_HTTP_TIMEOUT", 10.0)
        retries = self._env_int("MSS_DATA_HTTP_RETRIES", 2)
        backoff = self._env_float("MSS_DATA_HTTP_BACKOFF_SECONDS", 0.4)
        self.symbol_map: dict[str, SymbolConfig] = {
            "QQQ": SymbolConfig(
                providers=[
                    (YahooFinanceProvider(), "QQQ"),
                    (StooqDailyProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "QQQ"),
                ]
            ),
            "ETH": SymbolConfig(
                providers=[
                    (BinanceSpotProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETHUSDT"),
                    (YahooFinanceProvider(), "ETH-USD"),
                    (CoinGeckoProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETH"),
                ]
            ),
            "ETHUSD": SymbolConfig(
                providers=[
                    (BinanceSpotProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETHUSDT"),
                    (YahooFinanceProvider(), "ETH-USD"),
                    (CoinGeckoProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETH"),
                ]
            ),
            "ETHUSDT": SymbolConfig(
                providers=[
                    (BinanceSpotProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETHUSDT"),
                    (YahooFinanceProvider(), "ETH-USD"),
                    (CoinGeckoProvider(timeout=timeout, retries=retries, backoff_seconds=backoff), "ETH"),
                ]
            ),
        }

    @staticmethod
    def _env_float(key: str, default: float) -> float:
        raw = os.getenv(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    @staticmethod
    def _env_int(key: str, default: int) -> int:
        raw = os.getenv(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_history(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        interval: str = "1d",
        use_cache: bool = True,
        incremental: bool = True,
    ) -> pd.DataFrame:
        normalized_interval = interval.lower()
        if normalized_interval in self._WEEKLY_INTERVALS:
            return self._get_weekly_history_from_daily(
                symbol=symbol,
                start=start,
                end=end,
                use_cache=use_cache,
                incremental=incremental,
            )

        key = symbol.upper()
        if key not in self.symbol_map:
            raise ValueError(f"Unsupported symbol: {symbol}.")

        start_ts = self._to_utc_ts(start)
        end_ts = self._to_utc_ts(end)
        if end_ts <= start_ts:
            raise ValueError("end must be greater than start.")

        config = self.symbol_map[key]
        cache_path = CACHE_DIR / f"{key}_{interval}.csv"

        cached = self._load_cache(cache_path) if use_cache else pd.DataFrame()
        if cached.empty:
            fetched = self._fetch_with_fallback(config, start_ts, end_ts, interval)
            merged = self._postprocess(fetched, interval)
            if use_cache:
                self._save_cache(cache_path, merged)
            return merged.loc[(merged.index >= start_ts) & (merged.index <= end_ts)]

        merged = cached
        if incremental:
            cached_start = cached.index.min()
            cached_end = cached.index.max()
            if cached_start.tzinfo is None:
                cached_start = cached_start.tz_localize("UTC")
            if cached_end.tzinfo is None:
                cached_end = cached_end.tz_localize("UTC")
            need_update = False

            if start_ts < cached_start:
                backfill_end = min(end_ts, cached_start + pd.Timedelta(days=5))
                fetched = self._fetch_with_fallback(config, start_ts, backfill_end, interval)
                merged = pd.concat([merged, fetched], axis=0)
                need_update = True

            if cached_end < end_ts:
                refresh_start = max(start_ts, cached_end - pd.Timedelta(days=5))
                fetched = self._fetch_with_fallback(config, refresh_start, end_ts, interval)
                merged = pd.concat([merged, fetched], axis=0)
                need_update = True

            if need_update:
                merged = merged.sort_index()
                merged = merged[~merged.index.duplicated(keep="last")]
                merged = self._postprocess(merged, interval)
                if use_cache:
                    self._save_cache(cache_path, merged)

        sliced = merged.loc[(merged.index >= start_ts) & (merged.index <= end_ts)]
        if sliced.empty:
            fetched = self._fetch_with_fallback(config, start_ts, end_ts, interval)
            sliced = self._postprocess(fetched, interval)
        return sliced

    def _get_weekly_history_from_daily(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        use_cache: bool,
        incremental: bool,
    ) -> pd.DataFrame:
        start_ts = self._to_utc_ts(start)
        end_ts = self._to_utc_ts(end)
        fetch_start = start_ts - pd.Timedelta(days=7)
        daily = self.get_history(
            symbol=symbol,
            start=fetch_start,
            end=end_ts,
            interval="1d",
            use_cache=use_cache,
            incremental=incremental,
        )
        weekly = self._resample_ohlcv(daily, rule="W-FRI")
        return weekly.loc[(weekly.index >= start_ts) & (weekly.index <= end_ts)]

    def get_aligned_history(
        self,
        symbols: list[str],
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        interval: str = "1d",
        use_cache: bool = True,
        incremental: bool = True,
    ) -> dict[str, pd.DataFrame]:
        if not symbols:
            raise ValueError("symbols cannot be empty")

        frames: dict[str, pd.DataFrame] = {}
        common_index: pd.DatetimeIndex | None = None
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            if not symbol:
                continue
            data = self.get_history(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
                use_cache=use_cache,
                incremental=incremental,
            )
            if data.empty:
                continue
            frames[symbol] = data.sort_index()
            common_index = data.index if common_index is None else common_index.intersection(data.index)

        if not frames:
            raise ValueError("no data loaded for symbols")
        if common_index is None or len(common_index) == 0:
            raise ValueError("symbols have no aligned timestamp range")

        return {symbol: frame.loc[common_index].copy() for symbol, frame in frames.items()}

    def update_cache(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        interval: str = "1d",
    ) -> dict[str, object]:
        key = symbol.upper()
        if key not in self.symbol_map:
            raise ValueError(f"Unsupported symbol: {symbol}.")

        start_ts = self._to_utc_ts(start)
        end_ts = self._to_utc_ts(end)
        if end_ts <= start_ts:
            raise ValueError("end must be greater than start.")

        cache_path = CACHE_DIR / f"{key}_{interval}.csv"
        before = self._load_cache(cache_path)
        before_rows = int(len(before))
        before_start = before.index.min().isoformat() if not before.empty else None
        before_end = before.index.max().isoformat() if not before.empty else None

        window = self.get_history(
            symbol=key,
            start=start_ts,
            end=end_ts,
            interval=interval,
            use_cache=True,
            incremental=True,
        )
        after = self._load_cache(cache_path)
        after_rows = int(len(after))
        after_start = after.index.min().isoformat() if not after.empty else None
        after_end = after.index.max().isoformat() if not after.empty else None

        return {
            "symbol": key,
            "interval": interval,
            "cache_file": str(cache_path),
            "cache_rows_before": before_rows,
            "cache_rows_after": after_rows,
            "cache_rows_added": max(0, after_rows - before_rows),
            "cache_changed": after_rows != before_rows or before_start != after_start or before_end != after_end,
            "cache_start_before": before_start,
            "cache_end_before": before_end,
            "cache_start_after": after_start,
            "cache_end_after": after_end,
            "window_rows": int(len(window)),
            "window_start": window.index.min().isoformat() if not window.empty else None,
            "window_end": window.index.max().isoformat() if not window.empty else None,
        }

    @staticmethod
    def _fetch_with_fallback(
        config: SymbolConfig,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str,
    ) -> pd.DataFrame:
        last_error: Exception | None = None
        for provider, provider_symbol in config.providers:
            try:
                frame = provider.fetch_history(provider_symbol, start, end, interval)
                if not frame.empty:
                    return frame
            except Exception as exc:  # pragma: no cover - 网络异常分支依赖外部环境
                last_error = exc
                continue
        if last_error is not None:
            raise RuntimeError(f"All providers failed: {last_error}") from last_error
        raise RuntimeError("No provider configured.")

    @staticmethod
    def align_close_frames(frames: dict[str, pd.DataFrame], how: str = "inner") -> pd.DataFrame:
        closes = []
        for name, df in frames.items():
            close = df[["close"]].rename(columns={"close": name})
            closes.append(close)

        combined = pd.concat(closes, axis=1, join=how).sort_index()
        return combined.ffill().dropna(how="all")

    @staticmethod
    def _resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
        aggregated = frame.resample(rule, label="right", closed="right").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return aggregated.dropna(subset=["open", "high", "low", "close"])

    @staticmethod
    def _postprocess(df: pd.DataFrame, interval: str) -> pd.DataFrame:
        frame = df.copy()
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        frame = frame.ffill().dropna(subset=["open", "high", "low", "close"])
        if interval.endswith("d"):
            frame = frame[frame.index.dayofweek <= 6]
        return frame

    @staticmethod
    def _load_cache(path: os.PathLike[str] | str) -> pd.DataFrame:
        p = pd.io.common.stringify_path(path)
        try:
            df = pd.read_csv(p, index_col=0, parse_dates=True)
        except FileNotFoundError:
            return pd.DataFrame()
        if df.empty:
            return df
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    @staticmethod
    def _save_cache(path: os.PathLike[str] | str, df: pd.DataFrame) -> None:
        df.to_csv(path)

    @staticmethod
    def _to_utc_ts(value: str | pd.Timestamp) -> pd.Timestamp:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")
