import unittest
from datetime import datetime, timezone

from app.core.models import PositionLog, SignalRecord, SignalType, TradeLog
from app.services.report_service import ReportService


class _FakeSignalService:
    def list_signals(self) -> list[SignalRecord]:
        return [
            SignalRecord(
                id="s1",
                run_instance_id="r1",
                strategy_id="stg1",
                symbol="ETH",
                interval="15m",
                signal_type=SignalType.OPEN_LONG,
                trigger_time="2026-03-17T01:00:00+00:00",
                trigger_price=100.0,
                reason_snapshot="{}",
            ),
            SignalRecord(
                id="s2",
                run_instance_id="r1",
                strategy_id="stg1",
                symbol="ETH",
                interval="15m",
                signal_type=SignalType.CLOSE_LONG,
                trigger_time="2026-03-17T02:00:00+00:00",
                trigger_price=105.0,
                reason_snapshot="{}",
            ),
        ]


class _FakeLedgerService:
    def list_trade_logs(self) -> list[TradeLog]:
        return [
            TradeLog(
                id="t1",
                run_instance_id="r1",
                symbol="ETH",
                side="LONG",
                entry_time="2026-03-17T01:00:00+00:00",
                entry_price=100.0,
                exit_time="2026-03-17T02:00:00+00:00",
                exit_price=105.0,
                realized_pnl=5.0,
                reason_snapshot="{}",
            )
        ]

    def list_position_logs(self) -> list[PositionLog]:
        return [
            PositionLog(
                id="p1",
                run_instance_id="r1",
                symbol="ETH",
                action="OPEN",
                position_side="LONG",
                quantity=1.0,
                price=100.0,
                reason_snapshot="{}",
                timestamp="2026-03-17T01:00:00+00:00",
            ),
            PositionLog(
                id="p2",
                run_instance_id="r1",
                symbol="ETH",
                action="CLOSE",
                position_side="LONG",
                quantity=1.0,
                price=105.0,
                reason_snapshot="{}",
                timestamp="2026-03-17T02:00:00+00:00",
            ),
        ]


class ReportServiceTest(unittest.TestCase):
    def test_generate_and_export(self) -> None:
        service = ReportService(signal_service=_FakeSignalService(), ledger_service=_FakeLedgerService())
        report = service.generate(
            start=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 18, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(report.signal_count, 2)
        self.assertEqual(report.trade_count, 1)
        self.assertEqual(report.realized_pnl, 5.0)

        content = service.export_csv(report).decode("utf-8")
        self.assertIn("realized_pnl", content)
        self.assertIn("OPEN_LONG", content)


if __name__ == "__main__":
    unittest.main()
