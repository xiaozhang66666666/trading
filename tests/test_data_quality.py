import pandas as pd

from market_signal_system.data.quality import diagnose_ohlcv_quality


def test_diagnose_ohlcv_quality_detects_core_anomalies():
    idx = pd.to_datetime(
        [
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "2024-01-04T00:00:00Z",
            "2024-01-07T00:00:00Z",
        ],
        utc=True,
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0, -1.0, 104.0],
            "high": [102.0, 103.0, 100.0, 103.0],
            "low": [99.0, 102.0, 99.0, 105.0],
            "close": [101.0, 104.0, 99.5, 104.5],
            "volume": [1000.0, 1000.0, 1000.0, None],
        },
        index=idx,
    )

    result = diagnose_ohlcv_quality(frame)
    report = result.report

    assert report["row_count"] == 4
    assert report["missing_ohlcv_rows"] == 1
    assert report["invalid_price_rows"] == 1
    assert report["invalid_hl_rows"] == 1
    assert report["open_outside_hl_rows"] == 3
    assert report["close_outside_hl_rows"] == 2
    assert report["gap_count"] >= 1
    assert report["max_gap_multiplier"] >= 1.5

    issues = set(result.anomalies["issue"].tolist())
    assert "missing_ohlcv" in issues
    assert "invalid_price" in issues
    assert "invalid_high_low" in issues


def test_diagnose_ohlcv_quality_empty_frame():
    frame = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = diagnose_ohlcv_quality(frame)
    assert result.report["row_count"] == 0
    assert result.anomalies.empty
