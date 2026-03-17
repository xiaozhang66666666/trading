from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.models import (
    RunInstance,
    RunStatus,
    SignalRecord,
    SignalType,
    StrategyRecord,
    StrategyTemplate,
    Symbol,
)
from app.services.market_data_service import MarketDataService


@dataclass
class _EngineState:
    position: str = "FLAT"
    last_signal_time: str = ""
    last_open_time: str = ""


class SignalEngineService:
    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data
        self._states: dict[str, _EngineState] = {}
        self._signals: list[SignalRecord] = []
        self._dedup_keys: set[str] = set()

    @staticmethod
    def _sma(values: list[float], period: int, idx: int) -> float | None:
        if idx + 1 < period:
            return None
        sample = values[idx + 1 - period : idx + 1]
        return sum(sample) / period

    @staticmethod
    def _rsi(values: list[float], period: int, idx: int) -> float | None:
        if idx < period:
            return None
        gains = 0.0
        losses = 0.0
        for i in range(idx - period + 1, idx + 1):
            delta = values[i] - values[i - 1]
            if delta > 0:
                gains += delta
            elif delta < 0:
                losses += abs(delta)
        if losses == 0:
            return 100
        rs = gains / losses
        return 100 - 100 / (1 + rs)

    def _calc_signals(self, template: StrategyTemplate, closes: list[float]) -> tuple[bool, bool, bool, bool]:
        idx = len(closes) - 1
        if idx < 25:
            return (False, False, False, False)

        if template == StrategyTemplate.MA_CROSS:
            fast_now = self._sma(closes, 5, idx)
            fast_prev = self._sma(closes, 5, idx - 1)
            slow_now = self._sma(closes, 20, idx)
            slow_prev = self._sma(closes, 20, idx - 1)
            if None in (fast_now, fast_prev, slow_now, slow_prev):
                return (False, False, False, False)
            open_long = fast_prev <= slow_prev and fast_now > slow_now
            close_long = fast_prev >= slow_prev and fast_now < slow_now
            return (open_long, close_long, close_long, open_long)

        rsi = self._rsi(closes, 14, idx)
        if rsi is None:
            return (False, False, False, False)
        open_long = rsi < 30
        close_long = rsi > 55
        open_short = rsi > 70
        close_short = rsi < 45
        return (open_long, close_long, open_short, close_short)

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _can_emit_signal(self, run: RunInstance, state: _EngineState, latest_close_time: str) -> bool:
        if not state.last_signal_time:
            return True
        elapsed = (self._parse_iso(latest_close_time) - self._parse_iso(state.last_signal_time)).total_seconds()
        return elapsed >= max(run.payload.min_signal_interval_seconds, 0)

    def _cooldown_ready(self, run: RunInstance, state: _EngineState, latest_close_time: str) -> bool:
        if not state.last_open_time:
            return True
        elapsed = (self._parse_iso(latest_close_time) - self._parse_iso(state.last_open_time)).total_seconds()
        return elapsed >= max(run.payload.cooldown_seconds, 0)

    @staticmethod
    def _risk_allows(run: RunInstance, latest_price: float, latest_open: float, latest_high: float, latest_low: float) -> bool:
        if latest_price > run.payload.max_position_value:
            return False
        if latest_open <= 0:
            return False
        volatility = (latest_high - latest_low) / latest_open
        return volatility <= max(run.payload.risk_limit, 0)

    @staticmethod
    def _make_reason(strategy: StrategyRecord, signal_type: SignalType) -> str:
        return json.dumps(
            {
                "strategy": strategy.name,
                "template": strategy.latest_payload.template,
                "signal": signal_type,
                "json_dsl": strategy.latest_payload.json_dsl,
            },
            ensure_ascii=False,
        )

    async def tick(self, runs: list[RunInstance], strategy_map: dict[str, StrategyRecord], symbol_map: dict[str, Symbol]) -> list[SignalRecord]:
        created: list[SignalRecord] = []
        for run in runs:
            if run.status != RunStatus.RUNNING:
                continue
            strategy = strategy_map.get(run.payload.strategy_id)
            symbol = symbol_map.get(run.payload.symbol)
            if not strategy or not symbol:
                continue

            candles = await self._market_data.get_klines(symbol=symbol, interval=run.payload.interval, limit=120)
            if not candles:
                continue
            latest = candles[-1]
            closes = [item.close for item in candles]
            open_long, close_long, open_short, close_short = self._calc_signals(strategy.latest_payload.template, closes)

            state = self._states.setdefault(run.id, _EngineState())
            signal_type: SignalType | None = None
            if run.payload.require_volume and latest.volume <= 0:
                continue
            if not self._can_emit_signal(run, state, latest.close_time):
                continue

            if state.position == "FLAT":
                if not self._cooldown_ready(run, state, latest.close_time):
                    continue
                if strategy.latest_payload.direction.allow_long and open_long:
                    if not self._risk_allows(run, latest.close, latest.open, latest.high, latest.low):
                        continue
                    signal_type = SignalType.OPEN_LONG
                    state.position = "LONG"
                    state.last_open_time = latest.close_time
                elif strategy.latest_payload.direction.allow_short and open_short:
                    if not self._risk_allows(run, latest.close, latest.open, latest.high, latest.low):
                        continue
                    signal_type = SignalType.OPEN_SHORT
                    state.position = "SHORT"
                    state.last_open_time = latest.close_time
            elif state.position == "LONG" and close_long:
                signal_type = SignalType.CLOSE_LONG
                state.position = "FLAT"
            elif state.position == "LONG" and open_short and run.payload.reverse_on_opposite:
                signal_type = SignalType.CLOSE_LONG
                state.position = "FLAT"
            elif state.position == "SHORT" and close_short:
                signal_type = SignalType.CLOSE_SHORT
                state.position = "FLAT"
            elif state.position == "SHORT" and open_long and run.payload.reverse_on_opposite:
                signal_type = SignalType.CLOSE_SHORT
                state.position = "FLAT"

            if signal_type is None:
                continue

            dedup_key = f"{run.id}:{latest.close_time}:{signal_type}"
            if dedup_key in self._dedup_keys:
                continue
            self._dedup_keys.add(dedup_key)
            state.last_signal_time = latest.close_time

            record = SignalRecord(
                id=uuid.uuid4().hex[:12],
                run_instance_id=run.id,
                strategy_id=run.payload.strategy_id,
                symbol=run.payload.symbol,
                interval=run.payload.interval,
                signal_type=signal_type,
                trigger_time=latest.close_time,
                trigger_price=latest.close,
                reason_snapshot=self._make_reason(strategy, signal_type),
            )
            self._signals.append(record)
            created.append(record)
        return created

    def list_signals(self) -> list[SignalRecord]:
        return list(reversed(self._signals))
