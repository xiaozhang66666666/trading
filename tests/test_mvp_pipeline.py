from __future__ import annotations

from market_signal_system.mvp.pipeline import build_mvp_acceptance


def test_build_mvp_acceptance_passes_for_complete_summary() -> None:
    summary = {
        "symbols": ["QQQ", "ETH"],
        "strategies": ["ma_cross", "momentum", "regime"],
        "backtests": [
            {"signal_values": [-1, 0, 1]} for _ in range(6)
        ],
        "simulations": [
            {
                "snapshot": {
                    "cash": 1000,
                    "realized_pnl": 10,
                    "floating_pnl": 3,
                    "cumulative_pnl": 13,
                    "total_equity": 1013,
                    "positions": {},
                    "trade_count": 2,
                }
            },
            {
                "snapshot": {
                    "cash": 1000,
                    "realized_pnl": 0,
                    "floating_pnl": 0,
                    "cumulative_pnl": 0,
                    "total_equity": 1000,
                    "positions": {},
                    "trade_count": 0,
                }
            },
        ],
    }

    acceptance = build_mvp_acceptance(summary)
    assert acceptance["overall_passed"] is True
    assert acceptance["failed_check_ids"] == []


def test_build_mvp_acceptance_fails_when_no_short_signal() -> None:
    summary = {
        "symbols": ["QQQ", "ETH"],
        "strategies": ["ma_cross", "momentum", "regime"],
        "backtests": [
            {"signal_values": [0, 1]} for _ in range(6)
        ],
        "simulations": [
            {
                "snapshot": {
                    "cash": 1000,
                    "realized_pnl": 10,
                    "floating_pnl": 3,
                    "cumulative_pnl": 13,
                    "total_equity": 1013,
                    "positions": {},
                    "trade_count": 2,
                }
            },
            {
                "snapshot": {
                    "cash": 1000,
                    "realized_pnl": 0,
                    "floating_pnl": 0,
                    "cumulative_pnl": 0,
                    "total_equity": 1000,
                    "positions": {},
                    "trade_count": 0,
                }
            },
        ],
    }

    acceptance = build_mvp_acceptance(summary)
    assert acceptance["overall_passed"] is False
    assert "supports_long_short_flat" in acceptance["failed_check_ids"]
