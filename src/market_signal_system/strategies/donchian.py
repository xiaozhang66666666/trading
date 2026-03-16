"""Donchian breakout strategy."""

from __future__ import annotations

import pandas as pd

from market_signal_system.strategies.base import Strategy


class DonchianBreakoutStrategy(Strategy):
    """Long/short breakout with neutral exit at channel middle."""

    def __init__(self, lookback: int = 55, exit_lookback: int = 20) -> None:
        self.lookback = lookback
        self.exit_lookback = exit_lookback
        self.name = f"donchian_{lookback}_{exit_lookback}"

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        upper = close.rolling(self.lookback).max().shift(1)
        lower = close.rolling(self.lookback).min().shift(1)
        middle = close.rolling(self.exit_lookback).mean().shift(1)

        states: list[int] = []
        current = 0
        for idx, px in enumerate(close):
            up = upper.iloc[idx]
            down = lower.iloc[idx]
            mid = middle.iloc[idx]
            if pd.isna(up) or pd.isna(down) or pd.isna(mid):
                states.append(0)
                continue

            if px > up:
                current = 1
            elif px < down:
                current = -1
            elif (current == 1 and px < mid) or (current == -1 and px > mid):
                current = 0
            states.append(current)

        return pd.Series(states, index=data.index, name="signal").fillna(0).astype(int)

    def explain(self, data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"]
        upper = close.rolling(self.lookback).max().shift(1)
        lower = close.rolling(self.lookback).min().shift(1)
        middle = close.rolling(self.exit_lookback).mean().shift(1)

        states: list[int] = []
        reasons: list[str] = []
        current = 0
        for idx, px in enumerate(close):
            up = upper.iloc[idx]
            down = lower.iloc[idx]
            mid = middle.iloc[idx]
            if pd.isna(up) or pd.isna(down) or pd.isna(mid):
                states.append(0)
                reasons.append("warmup")
                continue

            if px > up:
                current = 1
                reason = "breakout_up"
            elif px < down:
                current = -1
                reason = "breakout_down"
            elif (current == 1 and px < mid) or (current == -1 and px > mid):
                current = 0
                reason = "exit_mid"
            else:
                reason = "hold"

            states.append(current)
            reasons.append(reason)

        return pd.DataFrame(
            {
                "signal": pd.Series(states, index=data.index, dtype=int),
                "upper_channel": upper,
                "lower_channel": lower,
                "middle_channel": middle,
                "reason": reasons,
            },
            index=data.index,
        )
