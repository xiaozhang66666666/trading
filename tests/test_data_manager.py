from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from market_signal_system.data.base import DataProvider
from market_signal_system.data.manager import DataManager, SymbolConfig
from market_signal_system.data.providers import BinanceSpotProvider, CoinGeckoProvider, StooqDailyProvider


def _build_frame(start: str, end: str) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D", tz="UTC")
    close = pd.Series(range(100, 100 + len(idx)), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )


@dataclass
class FakeProvider(DataProvider):
    history: pd.DataFrame
    calls: list[tuple[pd.Timestamp, pd.Timestamp]]

    def fetch_history(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        interval: str = "1d",
    ) -> pd.DataFrame:
        self.calls.append((start, end))
        return self.history.loc[(self.history.index >= start) & (self.history.index <= end)]


def test_incremental_backfill_when_start_before_cache(tmp_path: Path, monkeypatch):
    all_history = _build_frame("2020-01-01", "2020-12-31")
    provider = FakeProvider(history=all_history, calls=[])

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("market_signal_system.data.manager.CACHE_DIR", cache_dir)

    cached = all_history.loc[(all_history.index >= "2020-10-01") & (all_history.index <= "2020-12-31")]
    cached.to_csv(cache_dir / "QQQ_1d.csv")

    manager = DataManager()
    manager.symbol_map["QQQ"] = SymbolConfig(providers=[(provider, "QQQ")])

    data = manager.get_history(
        symbol="QQQ",
        start="2020-02-01",
        end="2020-11-30",
        interval="1d",
        use_cache=True,
        incremental=True,
    )

    assert not data.empty
    assert data.index.min() <= pd.Timestamp("2020-02-01", tz="UTC")
    assert data.index.max() >= pd.Timestamp("2020-11-30", tz="UTC")
    assert provider.calls, "expected backfill fetch when start is older than cache"


def test_fetch_with_fallback_uses_next_provider():
    history = _build_frame("2021-01-01", "2021-01-10")
    primary = FakeProvider(history=history.iloc[0:0], calls=[])
    secondary = FakeProvider(history=history, calls=[])
    cfg = SymbolConfig(providers=[(primary, "ETHUSDT"), (secondary, "ETH-USD")])

    out = DataManager._fetch_with_fallback(
        cfg,
        pd.Timestamp("2021-01-01", tz="UTC"),
        pd.Timestamp("2021-01-10", tz="UTC"),
        interval="1d",
    )
    assert not out.empty
    assert len(primary.calls) == 1
    assert len(secondary.calls) == 1


def test_get_aligned_history_returns_common_range():
    qqq_history = _build_frame("2021-01-01", "2021-01-10")
    eth_history = _build_frame("2021-01-05", "2021-01-12")
    qqq_provider = FakeProvider(history=qqq_history, calls=[])
    eth_provider = FakeProvider(history=eth_history, calls=[])

    manager = DataManager()
    manager.symbol_map["QQQ"] = SymbolConfig(providers=[(qqq_provider, "QQQ")])
    manager.symbol_map["ETH"] = SymbolConfig(providers=[(eth_provider, "ETH")])

    aligned = manager.get_aligned_history(
        symbols=["QQQ", "ETH"],
        start="2021-01-01",
        end="2021-01-12",
        interval="1d",
        use_cache=False,
    )
    assert set(aligned.keys()) == {"QQQ", "ETH"}
    assert aligned["QQQ"].index.min() == pd.Timestamp("2021-01-05", tz="UTC")
    assert aligned["QQQ"].index.max() == pd.Timestamp("2021-01-10", tz="UTC")
    assert aligned["QQQ"].index.equals(aligned["ETH"].index)


def test_binance_provider_parses_klines(monkeypatch):
    provider = BinanceSpotProvider()
    start = pd.Timestamp("2022-01-01", tz="UTC")
    end = pd.Timestamp("2022-01-03", tz="UTC")

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return [
                [1640995200000, "3700", "3800", "3600", "3750", "100", 1641081599999, "0", 0, "0", "0", "0"],
                [1641081600000, "3750", "3850", "3650", "3800", "110", 1641167999999, "0", 0, "0", "0", "0"],
            ]

    monkeypatch.setattr("market_signal_system.data.providers.requests.get", lambda *args, **kwargs: _Resp())
    frame = provider.fetch_history("ETHUSDT", start=start, end=end, interval="1d")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert frame.index.tz is not None


def test_coingecko_provider_builds_ohlcv_from_market_chart(monkeypatch):
    provider = CoinGeckoProvider()
    start = pd.Timestamp("2022-01-01", tz="UTC")
    end = pd.Timestamp("2022-01-03", tz="UTC")

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "prices": [
                    [1640995200000, 3700.0],
                    [1641038400000, 3720.0],
                    [1641081600000, 3750.0],
                    [1641124800000, 3780.0],
                ],
                "total_volumes": [
                    [1640995200000, 1000000.0],
                    [1641038400000, 1100000.0],
                    [1641081600000, 1200000.0],
                    [1641124800000, 1300000.0],
                ],
            }

    monkeypatch.setattr("market_signal_system.data.providers.requests.get", lambda *args, **kwargs: _Resp())
    frame = provider.fetch_history("ETH", start=start, end=end, interval="1d")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) >= 1
    assert frame.index.tz is not None


def test_stooq_provider_parses_daily_csv(monkeypatch):
    provider = StooqDailyProvider()
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2024-01-03", tz="UTC")

    class _Resp:
        status_code = 200
        text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01,400.0,405.0,398.0,404.0,1000000\n"
            "2024-01-02,404.0,407.0,401.0,406.0,1200000\n"
        )

    monkeypatch.setattr("market_signal_system.data.providers.requests.get", lambda *args, **kwargs: _Resp())
    frame = provider.fetch_history("QQQ", start=start, end=end, interval="1d")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert frame.index.tz is not None


def test_get_history_supports_weekly_interval_resample():
    all_history = _build_frame("2020-01-01", "2020-01-31")
    provider = FakeProvider(history=all_history, calls=[])
    manager = DataManager()
    manager.symbol_map["QQQ"] = SymbolConfig(providers=[(provider, "QQQ")])

    weekly = manager.get_history(
        symbol="QQQ",
        start="2020-01-03",
        end="2020-01-31",
        interval="1wk",
        use_cache=False,
        incremental=False,
    )

    assert not weekly.empty
    assert len(provider.calls) == 1
    assert list(weekly.columns) == ["open", "high", "low", "close", "volume"]

    first = weekly.iloc[0]
    assert first["open"] == 100.0
    assert first["close"] == 102.0
    assert first["high"] == 103.0
    assert first["low"] == 99.0
    assert first["volume"] == 3000.0


def test_update_cache_returns_summary_and_grows_cache(tmp_path: Path, monkeypatch):
    all_history = _build_frame("2020-01-01", "2020-01-20")
    provider = FakeProvider(history=all_history, calls=[])

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("market_signal_system.data.manager.CACHE_DIR", cache_dir)

    cached = all_history.loc[(all_history.index >= "2020-01-01") & (all_history.index <= "2020-01-10")]
    cached.to_csv(cache_dir / "QQQ_1d.csv")

    manager = DataManager()
    manager.symbol_map["QQQ"] = SymbolConfig(providers=[(provider, "QQQ")])

    summary = manager.update_cache(
        symbol="QQQ",
        start="2020-01-01",
        end="2020-01-20",
        interval="1d",
    )

    assert summary["symbol"] == "QQQ"
    assert summary["cache_rows_before"] == 10
    assert summary["cache_rows_after"] >= 20
    assert summary["cache_rows_added"] >= 10
    assert summary["cache_changed"] is True
    assert summary["window_rows"] >= 20
    assert provider.calls, "expected provider fetch when end is newer than cache"
