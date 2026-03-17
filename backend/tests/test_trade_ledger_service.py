import unittest

from app.core.models import SignalRecord, SignalType
from app.services.trade_ledger_service import TradeLedgerService


class TradeLedgerServiceTest(unittest.TestCase):
    def test_process_open_and_close_generates_trade(self) -> None:
        service = TradeLedgerService()
        open_signal = SignalRecord(
            id="s1",
            run_instance_id="r1",
            strategy_id="stg1",
            symbol="ETH",
            interval="15m",
            signal_type=SignalType.OPEN_LONG,
            trigger_time="2026-01-01T00:00:00+00:00",
            trigger_price=100.0,
            reason_snapshot="{}",
        )
        close_signal = SignalRecord(
            id="s2",
            run_instance_id="r1",
            strategy_id="stg1",
            symbol="ETH",
            interval="15m",
            signal_type=SignalType.CLOSE_LONG,
            trigger_time="2026-01-01T01:00:00+00:00",
            trigger_price=105.0,
            reason_snapshot="{}",
        )
        service.process_signal(open_signal)
        service.process_signal(close_signal)

        self.assertEqual(len(service.list_trade_logs()), 1)
        self.assertEqual(len(service.list_position_logs()), 2)
        self.assertGreater(service.pnl_summary().realized_pnl, 0)


if __name__ == "__main__":
    unittest.main()
