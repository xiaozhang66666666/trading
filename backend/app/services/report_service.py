from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from app.core.models import PerformanceReport, PositionLog, SignalRecord, TradeLog
from app.services.signal_engine_service import SignalEngineService
from app.services.trade_ledger_service import TradeLedgerService


class ReportService:
    def __init__(self, signal_service: SignalEngineService, ledger_service: TradeLedgerService) -> None:
        self._signal_service = signal_service
        self._ledger_service = ledger_service

    @staticmethod
    def _parse_iso(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _filter_time(self, items: list, start: datetime, end: datetime, getter) -> list:
        return [item for item in items if start <= self._parse_iso(getter(item)) < end]

    def generate(self, start: datetime, end: datetime) -> PerformanceReport:
        signals: list[SignalRecord] = self._filter_time(
            self._signal_service.list_signals(),
            start,
            end,
            getter=lambda item: item.trigger_time,
        )
        trades: list[TradeLog] = self._filter_time(
            self._ledger_service.list_trade_logs(),
            start,
            end,
            getter=lambda item: item.exit_time,
        )
        positions: list[PositionLog] = self._filter_time(
            self._ledger_service.list_position_logs(),
            start,
            end,
            getter=lambda item: item.timestamp,
        )

        signal_stats: dict[str, int] = {}
        for signal in signals:
            signal_stats[signal.signal_type] = signal_stats.get(signal.signal_type, 0) + 1

        realized_pnl = sum(item.realized_pnl for item in trades)
        win_count = sum(1 for item in trades if item.realized_pnl >= 0)
        loss_count = sum(1 for item in trades if item.realized_pnl < 0)
        avg_trade_pnl = realized_pnl / len(trades) if trades else 0.0

        return PerformanceReport(
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            signal_count=len(signals),
            signal_stats=signal_stats,
            trade_count=len(trades),
            win_count=win_count,
            loss_count=loss_count,
            realized_pnl=realized_pnl,
            avg_trade_pnl=avg_trade_pnl,
            position_change_count=len(positions),
        )

    def daily(self, date_utc: datetime | None = None) -> PerformanceReport:
        now = date_utc or datetime.now(tz=timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return self.generate(start=start, end=end)

    def weekly(self, date_utc: datetime | None = None) -> PerformanceReport:
        now = date_utc or datetime.now(tz=timezone.utc)
        week_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        return self.generate(start=week_start, end=week_end)

    @staticmethod
    def export_csv(report: PerformanceReport) -> bytes:
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["period_start", report.period_start])
        writer.writerow(["period_end", report.period_end])
        writer.writerow(["signal_count", report.signal_count])
        writer.writerow(["trade_count", report.trade_count])
        writer.writerow(["win_count", report.win_count])
        writer.writerow(["loss_count", report.loss_count])
        writer.writerow(["realized_pnl", report.realized_pnl])
        writer.writerow(["avg_trade_pnl", report.avg_trade_pnl])
        writer.writerow(["position_change_count", report.position_change_count])
        writer.writerow([])
        writer.writerow(["signal_type", "count"])
        for signal_type, count in report.signal_stats.items():
            writer.writerow([signal_type, count])
        return stream.getvalue().encode("utf-8")
