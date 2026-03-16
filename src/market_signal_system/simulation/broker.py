"""Paper trading broker with persistent state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import asdict, dataclass

from market_signal_system.utils.paths import STATE_DIR, ensure_runtime_dirs


@dataclass
class Position:
    symbol: str
    side: int
    quantity: float
    entry_price: float
    mark_price: float

    @property
    def unrealized_pnl(self) -> float:
        return (self.mark_price - self.entry_price) * self.quantity * self.side


@dataclass
class Trade:
    symbol: str
    side: int
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    entry_time: str
    exit_time: str


class PaperBroker:
    """Signal-driven paper broker for long/short/flat lifecycle."""

    def __init__(
        self,
        state_file: str = "paper_broker.json",
        initial_cash: float = 100000.0,
        fee_rate: float = 0.0008,
        slippage_bps: float = 5.0,
    ) -> None:
        ensure_runtime_dirs()
        self.state_path = STATE_DIR / state_file
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps

        self.cash = initial_cash
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.total_slippage = 0.0
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self._entry_times: dict[str, str] = {}
        self._last_processed_at: dict[str, str] = {}

        if self.state_path.exists():
            self.load_state()

    def process_signal(
        self,
        symbol: str,
        signal: int,
        price: float,
        timestamp: str,
        quantity: float = 1.0,
    ) -> None:
        normalized_ts = self._normalize_timestamp(timestamp)
        if self._is_duplicate_bar(symbol=symbol, timestamp=normalized_ts):
            return

        target_side = int(max(-1, min(1, signal)))
        current = self.positions.get(symbol)
        current_side = current.side if current else 0

        if current is not None:
            current.mark_price = price

        if target_side == current_side:
            self._last_processed_at[symbol] = normalized_ts
            return

        if current is not None:
            self._close_position(symbol=symbol, exit_price=price, exit_time=normalized_ts)

        if target_side != 0:
            self._open_position(
                symbol=symbol,
                side=target_side,
                quantity=quantity,
                entry_price=price,
                entry_time=normalized_ts,
            )
        self._last_processed_at[symbol] = normalized_ts

    def mark_to_market(self, symbol: str, price: float) -> None:
        pos = self.positions.get(symbol)
        if pos:
            pos.mark_price = price

    @property
    def floating_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def cumulative_pnl(self) -> float:
        return self.realized_pnl + self.floating_pnl

    def snapshot(self) -> dict[str, object]:
        total_equity = self.initial_cash + self.cumulative_pnl
        return_pct = (total_equity / self.initial_cash - 1.0) if self.initial_cash > 0 else 0.0
        return {
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
            "floating_pnl": self.floating_pnl,
            "cumulative_pnl": self.cumulative_pnl,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_equity": total_equity,
            "return_pct": return_pct,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "trade_count": len(self.trades),
        }

    def save_state(self) -> None:
        payload = {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "trades": [asdict(t) for t in self.trades],
            "entry_times": self._entry_times,
            "last_processed_at": self._last_processed_at,
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self) -> None:
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.initial_cash = float(payload.get("initial_cash", self.initial_cash))
        self.cash = float(payload.get("cash", self.initial_cash))
        self.realized_pnl = float(payload.get("realized_pnl", 0.0))
        self.total_fees = float(payload.get("total_fees", 0.0))
        self.total_slippage = float(payload.get("total_slippage", 0.0))

        self.positions = {}
        for symbol, pos_data in payload.get("positions", {}).items():
            self.positions[symbol] = Position(**pos_data)

        self.trades = [Trade(**row) for row in payload.get("trades", [])]
        self._entry_times = dict(payload.get("entry_times", {}))
        self._last_processed_at = {
            str(symbol): self._normalize_timestamp(str(ts))
            for symbol, ts in payload.get("last_processed_at", {}).items()
        }

    def _is_duplicate_bar(self, symbol: str, timestamp: str) -> bool:
        last_ts = self._last_processed_at.get(symbol)
        return bool(last_ts and timestamp <= last_ts)

    @staticmethod
    def _normalize_timestamp(timestamp: str) -> str:
        raw = timestamp.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()

    def _open_position(
        self,
        symbol: str,
        side: int,
        quantity: float,
        entry_price: float,
        entry_time: str,
    ) -> None:
        fee = entry_price * quantity * self.fee_rate
        slip = entry_price * quantity * (self.slippage_bps / 10000.0)
        self.total_fees += fee
        self.total_slippage += slip
        self.cash -= fee + slip
        self.realized_pnl -= fee + slip

        self.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            mark_price=entry_price,
        )
        self._entry_times[symbol] = entry_time

    def _close_position(self, symbol: str, exit_price: float, exit_time: str) -> None:
        pos = self.positions.pop(symbol)
        entry_time = self._entry_times.pop(symbol, exit_time)

        gross_pnl = (exit_price - pos.entry_price) * pos.quantity * pos.side
        fee = exit_price * pos.quantity * self.fee_rate
        slip = exit_price * pos.quantity * (self.slippage_bps / 10000.0)
        self.total_fees += fee
        self.total_slippage += slip
        realized = gross_pnl - fee - slip

        self.cash += realized
        self.realized_pnl += realized
        self.trades.append(
            Trade(
                symbol=symbol,
                side=pos.side,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                realized_pnl=realized,
                entry_time=entry_time,
                exit_time=exit_time,
            )
        )


def create_broker(state_file: str = "paper_broker.json") -> PaperBroker:
    ensure_runtime_dirs()
    return PaperBroker(state_file=state_file)
