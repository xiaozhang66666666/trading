#!/usr/bin/env python3
"""Run an offline MVP smoke flow with synthetic QQQ/ETH data."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.mvp import build_mvp_acceptance
from market_signal_system.simulation.broker import PaperBroker
from market_signal_system.strategies import get_strategy


def _make_synthetic_ohlcv(seed: int, bars: int = 420) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=bars, freq="D", tz="UTC")
    drift = rng.normal(0.0004, 0.02, size=bars)
    close = 100 * np.exp(np.cumsum(drift))
    open_ = np.concatenate(([close[0]], close[:-1]))
    spread = np.abs(rng.normal(0.004, 0.002, size=bars))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.integers(1000, 5000, size=bars)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def _run_simulation(
    data: pd.DataFrame,
    symbol: str,
    strategy_name: str,
    quantity: float,
    state_file: str,
) -> dict[str, object]:
    strategy = get_strategy(strategy_name)
    explain = strategy.explain(data).reindex(data.index)
    explain["signal"] = explain.get("signal", strategy.generate_signals(data)).fillna(0).astype(int).clip(-1, 1)

    broker = PaperBroker(state_file=state_file)
    for ts, row in data.iterrows():
        broker.process_signal(
            symbol=symbol,
            signal=int(explain.loc[ts, "signal"]),
            price=float(row["close"]),
            timestamp=ts.isoformat(),
            quantity=quantity,
        )
        broker.mark_to_market(symbol, float(row["close"]))
    broker.save_state()
    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "trade_count": len(broker.trades),
        "snapshot": broker.snapshot(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline MVP smoke test using synthetic QQQ/ETH data")
    parser.add_argument("--bars", type=int, default=420, help="Bar count for synthetic data")
    parser.add_argument("--quantity", type=float, default=1.0, help="Simulation quantity per signal")
    parser.add_argument("--state-prefix", default="offline_smoke", help="State file prefix")
    parser.add_argument("--output-file", help="Output summary JSON file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    strategies = ["ma_cross", "momentum", "donchian"]
    symbols = ["QQQ", "ETH"]

    datasets = {
        "QQQ": _make_synthetic_ohlcv(seed=7, bars=args.bars),
        "ETH": _make_synthetic_ohlcv(seed=77, bars=args.bars),
    }
    engine = BacktestEngine()

    summary: dict[str, object] = {
        "run_tag": run_tag,
        "mode": "offline_smoke",
        "symbols": symbols,
        "strategies": strategies,
        "backtests": [],
        "simulations": [],
    }

    for symbol in symbols:
        data = datasets[symbol]
        for strategy_name in strategies:
            result = engine.run(data=data, strategy=get_strategy(strategy_name), symbol=symbol)
            summary["backtests"].append(
                {
                    "symbol": symbol,
                    "strategy": strategy_name,
                    "bars": len(data),
                    "total_return": float(result.metrics.get("total_return", 0.0)),
                    "max_drawdown": float(result.metrics.get("max_drawdown", 0.0)),
                    "sharpe": float(result.metrics.get("sharpe", 0.0)),
                    "signal_values": sorted({int(v) for v in result.signals.dropna().tolist()}),
                }
            )

        sim = _run_simulation(
            data=data,
            symbol=symbol,
            strategy_name="momentum",
            quantity=args.quantity,
            state_file=f"{args.state_prefix}_{run_tag}_{symbol.lower()}.json",
        )
        summary["simulations"].append(sim)

    summary["mvp_acceptance"] = build_mvp_acceptance(summary)
    out = Path(args.output_file) if args.output_file else Path("outputs") / f"mvp_offline_smoke_{summary['run_tag']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary_file": str(out), "backtests": len(summary["backtests"]), "simulations": len(summary["simulations"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
