from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass

from app.core.models import PnlSummary, PositionLog, SignalRecord, SignalType, TradeLog


@dataclass
class _OpenPosition:
    side: str
    entry_time: str
    entry_price: float
    qty: float
    reason_snapshot: str


class TradeLedgerService:
    def __init__(self) -> None:
        self._positions: dict[str, _OpenPosition] = {}
        self._position_logs: list[PositionLog] = []
        self._trade_logs: list[TradeLog] = []
        self._realized_pnl = 0.0

    def process_signal(self, signal: SignalRecord) -> None:
        run_id = signal.run_instance_id
        position = self._positions.get(run_id)

        if signal.signal_type in {SignalType.OPEN_LONG, SignalType.OPEN_SHORT}:
            if position is not None:
                return
            side = "LONG" if signal.signal_type == SignalType.OPEN_LONG else "SHORT"
            new_position = _OpenPosition(
                side=side,
                entry_time=signal.trigger_time,
                entry_price=signal.trigger_price,
                qty=1.0,
                reason_snapshot=signal.reason_snapshot,
            )
            self._positions[run_id] = new_position
            self._position_logs.append(
                PositionLog(
                    id=uuid.uuid4().hex[:12],
                    run_instance_id=run_id,
                    symbol=signal.symbol,
                    action="OPEN",
                    position_side=side,
                    quantity=1.0,
                    price=signal.trigger_price,
                    reason_snapshot=signal.reason_snapshot,
                    timestamp=signal.trigger_time,
                )
            )
            return

        if signal.signal_type in {SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT} and position is not None:
            if position.side == "LONG":
                pnl = (signal.trigger_price - position.entry_price) * position.qty
            else:
                pnl = (position.entry_price - signal.trigger_price) * position.qty
            self._realized_pnl += pnl
            self._trade_logs.append(
                TradeLog(
                    id=uuid.uuid4().hex[:12],
                    run_instance_id=run_id,
                    symbol=signal.symbol,
                    side=position.side,
                    entry_time=position.entry_time,
                    entry_price=position.entry_price,
                    exit_time=signal.trigger_time,
                    exit_price=signal.trigger_price,
                    realized_pnl=pnl,
                    reason_snapshot=signal.reason_snapshot,
                )
            )
            self._position_logs.append(
                PositionLog(
                    id=uuid.uuid4().hex[:12],
                    run_instance_id=run_id,
                    symbol=signal.symbol,
                    action="CLOSE",
                    position_side=position.side,
                    quantity=position.qty,
                    price=signal.trigger_price,
                    reason_snapshot=signal.reason_snapshot,
                    timestamp=signal.trigger_time,
                )
            )
            self._positions.pop(run_id, None)

    def list_position_logs(self) -> list[PositionLog]:
        return list(reversed(self._position_logs))

    def list_trade_logs(self) -> list[TradeLog]:
        return list(reversed(self._trade_logs))

    def pnl_summary(self, latest_prices: dict[str, float] | None = None) -> PnlSummary:
        unrealized = 0.0
        if latest_prices:
            for run_id, position in self._positions.items():
                price = latest_prices.get(run_id, position.entry_price)
                if position.side == "LONG":
                    unrealized += (price - position.entry_price) * position.qty
                else:
                    unrealized += (position.entry_price - price) * position.qty
        return PnlSummary(realized_pnl=self._realized_pnl, unrealized_pnl=unrealized, total_pnl=self._realized_pnl + unrealized)

    def export_csv(self) -> bytes:
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["log_type", "run_instance_id", "symbol", "side", "entry_time", "entry_price", "exit_time", "exit_price", "realized_pnl"])
        for trade in self._trade_logs:
            writer.writerow(
                [
                    "TRADE",
                    trade.run_instance_id,
                    trade.symbol,
                    trade.side,
                    trade.entry_time,
                    trade.entry_price,
                    trade.exit_time,
                    trade.exit_price,
                    trade.realized_pnl,
                ]
            )
        return stream.getvalue().encode("utf-8")
