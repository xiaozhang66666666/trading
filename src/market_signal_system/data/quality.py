"""Data quality diagnostics for OHLCV frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class DataQualityResult:
    report: dict[str, Any]
    anomalies: pd.DataFrame


def diagnose_ohlcv_quality(df: pd.DataFrame) -> DataQualityResult:
    if df.empty:
        return DataQualityResult(
            report={
                "row_count": 0,
                "start": None,
                "end": None,
                "timezone": None,
                "duplicate_timestamp_count": 0,
                "missing_ohlcv_rows": 0,
                "invalid_price_rows": 0,
                "invalid_hl_rows": 0,
                "open_outside_hl_rows": 0,
                "close_outside_hl_rows": 0,
                "gap_count": 0,
                "max_gap_multiplier": 0.0,
            },
            anomalies=pd.DataFrame(columns=["timestamp", "issue"]),
        )

    frame = df.copy()
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()

    required = ["open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required if col not in frame.columns]
    if missing_cols:
        raise ValueError(f"缺少 OHLCV 列: {missing_cols}")

    ohlcv = frame[required]

    missing_mask = ohlcv.isna().any(axis=1)
    invalid_price_mask = (ohlcv[["open", "high", "low", "close"]] <= 0).any(axis=1)
    invalid_hl_mask = ohlcv["high"] < ohlcv["low"]
    open_outside_hl_mask = (ohlcv["open"] > ohlcv["high"]) | (ohlcv["open"] < ohlcv["low"])
    close_outside_hl_mask = (ohlcv["close"] > ohlcv["high"]) | (ohlcv["close"] < ohlcv["low"])

    duplicate_count = int(frame.index.duplicated(keep=False).sum())

    diffs = frame.index.to_series().diff().dropna()
    gap_count = 0
    max_gap_multiplier = 0.0
    if not diffs.empty:
        median_gap = diffs.median()
        if pd.notna(median_gap) and median_gap > pd.Timedelta(0):
            gap_mask = diffs >= (median_gap * 1.5)
            gap_count = int(gap_mask.sum())
            max_gap_multiplier = float((diffs / median_gap).max())

    issue_masks: list[tuple[str, pd.Series]] = [
        ("missing_ohlcv", missing_mask),
        ("invalid_price", invalid_price_mask),
        ("invalid_high_low", invalid_hl_mask),
        ("open_outside_hl", open_outside_hl_mask),
        ("close_outside_hl", close_outside_hl_mask),
    ]
    anomaly_rows: list[dict[str, str]] = []
    for issue, mask in issue_masks:
        for ts in ohlcv.index[mask]:
            anomaly_rows.append({"timestamp": ts.isoformat(), "issue": issue})

    anomalies = pd.DataFrame(anomaly_rows)
    if not anomalies.empty:
        anomalies = anomalies.sort_values(["timestamp", "issue"]).reset_index(drop=True)

    report = {
        "row_count": int(len(frame)),
        "start": frame.index.min().isoformat(),
        "end": frame.index.max().isoformat(),
        "timezone": str(frame.index.tz),
        "duplicate_timestamp_count": duplicate_count,
        "missing_ohlcv_rows": int(missing_mask.sum()),
        "invalid_price_rows": int(invalid_price_mask.sum()),
        "invalid_hl_rows": int(invalid_hl_mask.sum()),
        "open_outside_hl_rows": int(open_outside_hl_mask.sum()),
        "close_outside_hl_rows": int(close_outside_hl_mask.sum()),
        "gap_count": gap_count,
        "max_gap_multiplier": round(max_gap_multiplier, 4),
    }
    return DataQualityResult(report=report, anomalies=anomalies)
