import os

import pandas as pd
import pytest

from market_signal_system.data.providers import BinanceSpotProvider


@pytest.mark.integration
def test_binance_provider_live_fetch_daily_ethusdt():
    if os.getenv("RUN_BINANCE_INTEGRATION", "0") != "1":
        pytest.skip("set RUN_BINANCE_INTEGRATION=1 to enable live Binance integration test")

    provider = BinanceSpotProvider(timeout=10.0)
    start = pd.Timestamp("2026-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-15", tz="UTC")
    try:
        frame = provider.fetch_history("ETHUSDT", start=start, end=end, interval="1d")
    except RuntimeError as exc:
        if "HTTP 451" in str(exc):
            pytest.skip("binance endpoint blocked in current region (HTTP 451)")
        raise

    assert not frame.empty
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index.min() >= start
    assert frame.index.max() <= end
