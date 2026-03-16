"""MVP execution pipeline: data -> backtest -> simulation -> acceptance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.backtest.engine import BacktestEngine
from market_signal_system.data.manager import DataManager
from market_signal_system.simulation.broker import create_broker
from market_signal_system.strategies import get_strategy
from market_signal_system.utils.paths import OUTPUT_DIR, ensure_runtime_dirs


@dataclass(frozen=True)
class MvpPipelineConfig:
    start: str
    end: str
    symbols: list[str]
    strategies: list[str]
    simulate_strategy: str
    simulate_params: dict[str, Any]
    interval: str = "1d"
    fee_rate: float = 0.0008
    slippage_bps: float = 5.0
    bars_per_year: int = 252
    max_drawdown: float | None = None
    cooldown_bars: int = 20
    quantity: float = 1.0
    run_tag: str | None = None
    state_prefix: str | None = None
    output_file: str | None = None


def build_mvp_acceptance(summary: dict[str, Any]) -> dict[str, Any]:
    symbols = {str(s).upper() for s in summary.get("symbols", [])}
    strategies = [str(s).lower() for s in summary.get("strategies", [])]
    backtests = list(summary.get("backtests", []))
    simulations = list(summary.get("simulations", []))
    signal_values: set[int] = set()
    for row in backtests:
        for value in row.get("signal_values", []):
            try:
                signal_values.add(int(value))
            except (TypeError, ValueError):
                continue

    simulation_required_fields = {
        "cash",
        "realized_pnl",
        "floating_pnl",
        "cumulative_pnl",
        "total_equity",
        "positions",
        "trade_count",
    }
    simulation_snapshots_ok = all(
        simulation_required_fields.issubset(set((item.get("snapshot") or {}).keys())) for item in simulations
    )
    expected_backtest_count = len(symbols) * len(strategies)

    checks = [
        {
            "id": "covers_qqq_eth",
            "passed": {"QQQ", "ETH"}.issubset(symbols),
            "actual": sorted(symbols),
            "expected": "symbols includes QQQ and ETH",
        },
        {
            "id": "strategy_count_gte_3",
            "passed": len(strategies) >= 3,
            "actual": len(strategies),
            "expected": ">= 3",
        },
        {
            "id": "backtest_count_complete",
            "passed": len(backtests) >= expected_backtest_count and expected_backtest_count > 0,
            "actual": len(backtests),
            "expected": expected_backtest_count,
        },
        {
            "id": "simulate_count_complete",
            "passed": len(simulations) >= len(symbols) and len(symbols) > 0,
            "actual": len(simulations),
            "expected": len(symbols),
        },
        {
            "id": "simulate_snapshot_fields_complete",
            "passed": simulation_snapshots_ok,
            "actual": sorted(simulation_required_fields),
            "expected": "each simulation snapshot contains required pnl/position fields",
        },
        {
            "id": "signal_values_ternary",
            "passed": signal_values.issubset({-1, 0, 1}) and len(signal_values) > 0,
            "actual": sorted(signal_values),
            "expected": "subset of [-1, 0, 1]",
        },
        {
            "id": "supports_long_short_flat",
            "passed": {-1, 0, 1}.issubset(signal_values),
            "actual": sorted(signal_values),
            "expected": "contains -1, 0, 1",
        },
    ]

    failed_ids = [str(item["id"]) for item in checks if not bool(item["passed"])]
    return {
        "overall_passed": len(failed_ids) == 0,
        "failed_check_ids": failed_ids,
        "checks": checks,
    }


def run_mvp_pipeline(config: MvpPipelineConfig, *, data_manager: DataManager | None = None) -> tuple[Path, dict[str, Any]]:
    ensure_runtime_dirs()

    symbols = [s.strip().upper() for s in config.symbols if s and s.strip()]
    strategies = [s.strip().lower() for s in config.strategies if s and s.strip()]
    if not symbols:
        raise ValueError("--symbols 不能为空")
    if len(strategies) < 3:
        raise ValueError("--strategies 至少包含 3 个策略，用于 MVP 基线验收")

    run_tag = str(config.run_tag or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    state_prefix = str(config.state_prefix or f"mvp_{run_tag}")

    dm = data_manager or DataManager()
    backtest_engine = BacktestEngine(
        fee_rate=config.fee_rate,
        slippage_bps=config.slippage_bps,
        bars_per_year=config.bars_per_year,
        max_drawdown=config.max_drawdown,
        cooldown_bars=config.cooldown_bars,
    )
    simulate_strategy = get_strategy(config.simulate_strategy, **(config.simulate_params or {}))

    summary: dict[str, Any] = {
        "run_tag": run_tag,
        "symbols": symbols,
        "strategies": strategies,
        "simulate_strategy": config.simulate_strategy,
        "start": config.start,
        "end": config.end,
        "interval": config.interval,
        "backtests": [],
        "simulations": [],
    }

    for symbol in symbols:
        data = dm.get_history(symbol=symbol, start=config.start, end=config.end, interval=config.interval)
        if data.empty:
            raise ValueError(f"{symbol} 数据为空，无法执行 MVP")

        for strategy_name in strategies:
            strategy = get_strategy(strategy_name)
            result = backtest_engine.run(data=data, strategy=strategy, symbol=symbol)
            metrics_path = OUTPUT_DIR / f"mvp_metrics_{symbol}_{strategy_name}_{run_tag}.json"
            equity_path = OUTPUT_DIR / f"mvp_equity_{symbol}_{strategy_name}_{run_tag}.csv"
            trades_path = OUTPUT_DIR / f"mvp_trades_{symbol}_{strategy_name}_{run_tag}.csv"
            signals_path = OUTPUT_DIR / f"mvp_signals_{symbol}_{strategy_name}_{run_tag}.csv"
            metrics_path.write_text(json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
            result.equity_curve.to_csv(equity_path, header=True)
            result.trades.to_csv(trades_path, index=False)
            result.signal_explain.to_csv(signals_path, index=True)
            summary["backtests"].append(
                {
                    "symbol": symbol,
                    "strategy": strategy_name,
                    "bars": int(len(data)),
                    "total_return": float(result.metrics.get("total_return", 0.0)),
                    "max_drawdown": float(result.metrics.get("max_drawdown", 0.0)),
                    "sharpe": float(result.metrics.get("sharpe", 0.0)),
                    "metrics_file": metrics_path.name,
                    "signal_values": sorted({int(v) for v in result.signals.dropna().tolist()}),
                }
            )

        broker = create_broker(state_file=f"{state_prefix}_{symbol}.json")
        explain = simulate_strategy.explain(data).reindex(data.index)
        explain["signal"] = explain.get("signal", simulate_strategy.generate_signals(data)).fillna(0).astype(int).clip(-1, 1)
        if "reason" not in explain.columns:
            explain["reason"] = explain["signal"].map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})

        sim_signal_rows: list[dict[str, Any]] = []
        sim_equity_rows: list[dict[str, Any]] = []
        for ts, row in data.iterrows():
            signal = int(explain.loc[ts, "signal"])
            reason = str(explain.loc[ts, "reason"])
            broker.process_signal(
                symbol=symbol,
                signal=signal,
                price=float(row["close"]),
                timestamp=ts.isoformat(),
                quantity=float(config.quantity),
            )
            broker.mark_to_market(symbol, float(row["close"]))
            snap = broker.snapshot()
            sim_signal_rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "symbol": symbol,
                    "price": float(row["close"]),
                    "signal": signal,
                    "reason": reason,
                    "quantity": float(config.quantity),
                }
            )
            sim_equity_rows.append(
                {
                    "timestamp": ts.isoformat(),
                    "symbol": symbol,
                    "cash": float(snap["cash"]),
                    "realized_pnl": float(snap["realized_pnl"]),
                    "floating_pnl": float(snap["floating_pnl"]),
                    "cumulative_pnl": float(snap["cumulative_pnl"]),
                    "total_equity": float(snap["total_equity"]),
                    "return_pct": float(snap["return_pct"]),
                }
            )

        broker.save_state()
        trades_df = pd.DataFrame([t.__dict__ for t in broker.trades])
        trades_path = OUTPUT_DIR / f"mvp_sim_trades_{symbol}_{config.simulate_strategy}_{run_tag}.csv"
        signal_path = OUTPUT_DIR / f"mvp_sim_signals_{symbol}_{config.simulate_strategy}_{run_tag}.csv"
        equity_path = OUTPUT_DIR / f"mvp_sim_equity_{symbol}_{config.simulate_strategy}_{run_tag}.csv"
        trades_df.to_csv(trades_path, index=False)
        pd.DataFrame(sim_signal_rows).to_csv(signal_path, index=False)
        pd.DataFrame(sim_equity_rows).to_csv(equity_path, index=False)
        summary["simulations"].append(
            {
                "symbol": symbol,
                "strategy": config.simulate_strategy,
                "trade_count": int(len(broker.trades)),
                "state_file": f"{state_prefix}_{symbol}.json",
                "signal_file": signal_path.name,
                "equity_file": equity_path.name,
                "trades_file": trades_path.name,
                "snapshot": broker.snapshot(),
            }
        )

    backtests_df = pd.DataFrame(summary["backtests"])
    if not backtests_df.empty:
        backtests_df["total_return"] = pd.to_numeric(backtests_df["total_return"], errors="coerce").fillna(0.0)
        backtests_df["sharpe"] = pd.to_numeric(backtests_df["sharpe"], errors="coerce").fillna(0.0)
        topn_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for symbol, group in backtests_df.groupby("symbol", sort=True):
            ranked = group.sort_values(["total_return", "sharpe"], ascending=[False, False]).head(3).reset_index(drop=True)
            rows: list[dict[str, Any]] = []
            for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
                rows.append(
                    {
                        "rank": rank,
                        "strategy": str(row.get("strategy", "")),
                        "total_return": float(row.get("total_return", 0.0)),
                        "sharpe": float(row.get("sharpe", 0.0)),
                        "max_drawdown": float(row.get("max_drawdown", 0.0)),
                    }
                )
            topn_by_symbol[str(symbol)] = rows
        summary["backtest_topn_by_symbol"] = topn_by_symbol

        overall_ranked = backtests_df.sort_values(["total_return", "sharpe"], ascending=[False, False]).head(5).reset_index(drop=True)
        summary["backtest_topn_overall"] = [
            {
                "rank": rank,
                "symbol": str(row.get("symbol", "")),
                "strategy": str(row.get("strategy", "")),
                "total_return": float(row.get("total_return", 0.0)),
                "sharpe": float(row.get("sharpe", 0.0)),
                "max_drawdown": float(row.get("max_drawdown", 0.0)),
            }
            for rank, (_, row) in enumerate(overall_ranked.iterrows(), start=1)
        ]

    summary["mvp_acceptance"] = build_mvp_acceptance(summary)
    summary_path = OUTPUT_DIR / (config.output_file or f"mvp_summary_{run_tag}.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path, summary
