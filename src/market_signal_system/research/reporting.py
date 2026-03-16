"""Build human-readable report index from output artifacts."""

from __future__ import annotations

import json
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _compute_high_alert_streak(levels: pd.Series) -> tuple[int, int]:
    high = levels.fillna("none").astype(str).eq("high")
    max_streak = 0
    current = 0
    segments = 0
    in_segment = False
    for flag in high.tolist():
        if flag:
            current += 1
            max_streak = max(max_streak, current)
            if not in_segment:
                segments += 1
                in_segment = True
        else:
            current = 0
            in_segment = False
    return max_streak, segments


def _extract_run_summary_time(path: Path, payload: dict[str, Any]) -> pd.Timestamp:
    for field in ("run_ended_at", "run_started_at"):
        raw = payload.get(field)
        if not raw:
            continue
        ts = pd.to_datetime(raw, utc=True, errors="coerce")
        if not pd.isna(ts):
            return ts
    return pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _safe_int(value: Any, default: int = 0) -> int:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        return default
    return int(num)


def _safe_int_with_flag(value: Any, default: int = 0) -> tuple[int, bool]:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(num):
        invalid = value not in (None, "", " ", "None")
        return default, invalid
    return int(num), False


def _parse_run_id_time(run_id: str) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc))
    except ValueError:
        pass
    ts = pd.to_datetime(run_id, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def _load_json_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fp:
            payload = json.load(fp)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _extract_symbol_champions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "symbol" not in df.columns or "strategy" not in df.columns:
        return pd.DataFrame(columns=["symbol", "strategy", "composite_score"])
    temp = df.copy()
    if "composite_score" not in temp.columns:
        temp["composite_score"] = 0.0
    temp["composite_score"] = pd.to_numeric(temp["composite_score"], errors="coerce").fillna(0.0)
    if "symbol_rank" in temp.columns:
        temp["symbol_rank"] = pd.to_numeric(temp["symbol_rank"], errors="coerce")
        champions = temp[temp["symbol_rank"] == 1]
        if champions.empty:
            champions = temp.sort_values("composite_score", ascending=False).groupby("symbol", as_index=False).head(1)
    else:
        champions = temp.sort_values("composite_score", ascending=False).groupby("symbol", as_index=False).head(1)
    return champions[["symbol", "strategy", "composite_score"]].sort_values("symbol", ascending=True).reset_index(drop=True)


def _extract_run_symbol_champions(payload: dict[str, Any]) -> dict[str, str]:
    champion_runs = payload.get("symbol_group_champions", [])
    if not isinstance(champion_runs, list):
        return {}
    symbol_map: dict[str, str] = {}
    ordered_runs = sorted(
        [x for x in champion_runs if isinstance(x, dict)],
        key=lambda x: int(x.get("task_index", 0) or 0),
    )
    for entry in ordered_runs:
        champions = entry.get("champions", [])
        if not isinstance(champions, list):
            continue
        for row in champions:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "")).strip()
            strategy = str(row.get("strategy", "")).strip()
            if symbol and strategy:
                symbol_map[symbol] = strategy
    return symbol_map


def _switch_alert_level(
    switches: int,
    *,
    watch_threshold: int = 1,
    high_threshold: int = 2,
) -> str:
    watch = max(0, int(watch_threshold))
    high = max(watch, int(high_threshold))
    if switches >= high:
        return "high"
    if switches >= watch:
        return "watch"
    return "none"


def _collect_run_config_summary_rows(output_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    summary_files = sorted(set(output_dir.glob("*summary*.json")) | set(output_dir.glob("*summary*.json.gz")))
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in summary_files:
        payload = _load_json_file(path)
        if "task_count" not in payload or "results" not in payload or "on_error" not in payload:
            continue
        rows.append((path, payload))
    return rows


def _collect_recent_champion_switch_rows(
    run_config_rows: list[tuple[Path, dict[str, Any]]],
    *,
    recent_runs: int = 10,
    watch_threshold: int = 1,
    high_threshold: int = 2,
) -> tuple[int, list[dict[str, Any]]]:
    if not run_config_rows:
        return 0, []
    sorted_rows = sorted(
        run_config_rows,
        key=lambda item: _extract_run_summary_time(item[0], item[1]),
        reverse=True,
    )
    recent_n = min(max(1, int(recent_runs)), len(sorted_rows))
    recent_rows = sorted_rows[:recent_n]
    recent_rows_chrono = list(reversed(recent_rows))
    symbol_history: dict[str, list[tuple[str, pd.Timestamp]]] = {}
    for path, payload in recent_rows_chrono:
        run_ts = _extract_run_summary_time(path, payload)
        run_symbol_map = _extract_run_symbol_champions(payload)
        for symbol, strategy in run_symbol_map.items():
            symbol_history.setdefault(symbol, []).append((strategy, run_ts))

    switch_rows: list[dict[str, Any]] = []
    for symbol in sorted(symbol_history.keys()):
        history = symbol_history[symbol]
        strategies = [x[0] for x in history]
        run_times = [x[1] for x in history]
        switches = sum(1 for i in range(1, len(strategies)) if strategies[i] != strategies[i - 1])
        unique_count = len(set(strategies))
        latest = strategies[-1] if strategies else "-"
        first_run_time = run_times[0].isoformat() if run_times else ""
        latest_run_time = run_times[-1].isoformat() if run_times else ""
        alert_level = _switch_alert_level(
            switches,
            watch_threshold=watch_threshold,
            high_threshold=high_threshold,
        )
        switch_rows.append(
            {
                "symbol": symbol,
                "samples": len(strategies),
                "switches": switches,
                "unique_champions": unique_count,
                "latest": latest,
                "alert_level": alert_level,
                "watch_threshold": max(0, int(watch_threshold)),
                "high_threshold": max(max(0, int(watch_threshold)), int(high_threshold)),
                "recent_run_window": recent_n,
                "first_run_time": first_run_time,
                "latest_run_time": latest_run_time,
            }
        )
    return recent_n, switch_rows


def export_champion_switch_trend_csv(
    output_dir: Path,
    *,
    output_file: str = "champion_switch_last_runs.csv",
    recent_runs: int = 10,
    watch_threshold: int = 1,
    high_threshold: int = 2,
) -> Path | None:
    run_config_rows = _collect_run_config_summary_rows(output_dir)
    recent_n, switch_rows = _collect_recent_champion_switch_rows(
        run_config_rows,
        recent_runs=recent_runs,
        watch_threshold=watch_threshold,
        high_threshold=high_threshold,
    )
    if recent_n <= 0 or not switch_rows:
        return None
    out = output_dir / output_file
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(switch_rows).to_csv(out, index=False)
    return out


def build_report_index(
    output_dir: Path,
    *,
    champion_switch_watch_threshold: int = 1,
    champion_switch_high_threshold: int = 2,
    champion_switch_recent_runs: int = 10,
) -> str:
    lines: list[str] = ["# 实验报告索引", ""]

    metric_files = sorted(output_dir.glob("metrics_*.json"))
    portfolio_files = sorted(output_dir.glob("portfolio_metrics_*.json"))
    portfolio_attr_files = sorted(output_dir.glob("portfolio_attribution_*.csv"))
    portfolio_alert_files = sorted(output_dir.glob("portfolio_alerts_*.csv"))
    portfolio_weight_files = sorted(output_dir.glob("portfolio_weights_*.csv"))
    portfolio_drift_files = sorted(output_dir.glob("portfolio_drift_*.csv"))
    portfolio_rebalance_files = sorted(output_dir.glob("portfolio_rebalance_*.csv"))
    portfolio_capital_files = sorted(output_dir.glob("sim_portfolio_capital_*.csv"))
    sim_equity_files = sorted(output_dir.glob("sim_equity_*.csv"))
    wf_files = sorted(output_dir.glob("walk_forward_summary_*.json"))
    stability_files = sorted(output_dir.glob("stability_summary_*.json"))
    leaderboard_files = sorted(output_dir.glob("leaderboard_*.csv"))
    symbol_leaderboard_files = sorted(output_dir.glob("leaderboard_by_symbol_*.csv"))
    run_config_rows = _collect_run_config_summary_rows(output_dir)
    retry_budget_trace_files = sorted(
        set(output_dir.glob("*retry_budget_trace*.csv")) | set(output_dir.glob("*retry_budget_trace*.csv.gz"))
    )
    preset_compare_csv = output_dir / "preset_compare" / "preset_compare.csv"
    preset_cleanup_json = output_dir / "preset_compare" / "preset_compare_cleanup_latest.json"

    if metric_files:
        lines.append("## 单策略回测")
        for path in metric_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            benchmark_total = pd.to_numeric(pd.Series([payload.get("benchmark_total_return")]), errors="coerce").iloc[0]
            excess_total = pd.to_numeric(pd.Series([payload.get("excess_total_return")]), errors="coerce").iloc[0]
            info_ratio = pd.to_numeric(pd.Series([payload.get("information_ratio")]), errors="coerce").iloc[0]
            benchmark_text = (
                f", benchmark_total_return={float(benchmark_total):.4f}, "
                f"excess_total_return={float(excess_total):.4f}, information_ratio={float(info_ratio):.4f}"
                if not pd.isna(benchmark_total) and not pd.isna(excess_total) and not pd.isna(info_ratio)
                else ""
            )
            lines.append(
                f"- `{path.name}`: total_return={payload.get('total_return', 0):.4f}, "
                f"sharpe={payload.get('sharpe', 0):.4f}, max_drawdown={payload.get('max_drawdown', 0):.4f}"
                f"{benchmark_text}"
            )
        lines.append("")

        score_files: dict[str, Path] = {}
        macd_files: dict[str, Path] = {}
        for path in metric_files:
            stem = path.stem
            if "_score_regime_" in stem:
                symbol = stem.removeprefix("metrics_").split("_score_regime_")[0]
                prev = score_files.get(symbol)
                if prev is None or path.stat().st_mtime >= prev.stat().st_mtime:
                    score_files[symbol] = path
            elif "_macd_regime_" in stem:
                symbol = stem.removeprefix("metrics_").split("_macd_regime_")[0]
                prev = macd_files.get(symbol)
                if prev is None or path.stat().st_mtime >= prev.stat().st_mtime:
                    macd_files[symbol] = path

        shared_symbols = sorted(set(score_files.keys()) & set(macd_files.keys()))
        if shared_symbols:
            lines.append("## 策略对照摘要（score_regime vs macd_regime）")
            for symbol in shared_symbols:
                score_path = score_files[symbol]
                macd_path = macd_files[symbol]
                score_payload = json.loads(score_path.read_text(encoding="utf-8"))
                macd_payload = json.loads(macd_path.read_text(encoding="utf-8"))
                lines.append(
                    f"- {symbol}: score=`{score_path.name}`, macd=`{macd_path.name}`"
                )
                for field in ("total_return", "sharpe", "calmar", "max_drawdown", "win_rate"):
                    score_v = pd.to_numeric(pd.Series([score_payload.get(field)]), errors="coerce").iloc[0]
                    macd_v = pd.to_numeric(pd.Series([macd_payload.get(field)]), errors="coerce").iloc[0]
                    gap = (0.0 if pd.isna(score_v) else float(score_v)) - (
                        0.0 if pd.isna(macd_v) else float(macd_v)
                    )
                    lines.append(f"- {symbol}.score_minus_macd.{field}={gap:.4f}")
            lines.append("")

    if portfolio_files:
        lines.append("## 组合回测")
        for path in portfolio_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            benchmark_total = pd.to_numeric(pd.Series([payload.get("benchmark_total_return")]), errors="coerce").iloc[0]
            excess_total = pd.to_numeric(pd.Series([payload.get("excess_total_return")]), errors="coerce").iloc[0]
            info_ratio = pd.to_numeric(pd.Series([payload.get("information_ratio")]), errors="coerce").iloc[0]
            benchmark_text = (
                f", benchmark_total_return={float(benchmark_total):.4f}, "
                f"excess_total_return={float(excess_total):.4f}, information_ratio={float(info_ratio):.4f}"
                if not pd.isna(benchmark_total) and not pd.isna(excess_total) and not pd.isna(info_ratio)
                else ""
            )
            lines.append(
                f"- `{path.name}`: total_return={payload.get('total_return', 0):.4f}, "
                f"sharpe={payload.get('sharpe', 0):.4f}, max_drawdown={payload.get('max_drawdown', 0):.4f}"
                f"{benchmark_text}"
            )
        lines.append("")

    if portfolio_attr_files:
        lines.append("## 组合归因")
        for path in portfolio_attr_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            top = df.sort_values("total_contribution", ascending=False).iloc[0]
            lines.append(
                f"- `{path.name}` top_contrib={top.get('symbol')} "
                f"contrib={float(top.get('total_contribution', 0.0)):.4f}, "
                f"vol={float(top.get('annualized_vol_contribution', 0.0)):.4f}"
            )
        lines.append("")

    if portfolio_alert_files:
        lines.append("## 相关性与拥挤度告警")
        for path in portfolio_alert_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            high = int((df["alert_level"] == "high").sum()) if "alert_level" in df.columns else 0
            watch = int((df["alert_level"] == "watch").sum()) if "alert_level" in df.columns else len(df)
            top = df.iloc[0]
            lines.append(
                f"- `{path.name}` alerts={len(df)}, high={high}, watch={watch}, "
                f"sample_pair={top.get('pair', '-')}"
            )
        lines.append("")

    if portfolio_weight_files:
        lines.append("## 组合权重快照")
        for path in portfolio_weight_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            weight_cols = [c for c in df.columns if c.endswith("_weight")]
            avg_gross = float(df[weight_cols].abs().sum(axis=1).mean()) if weight_cols else 0.0
            lines.append(f"- `{path.name}` avg_gross_exposure={avg_gross:.4f}")
        lines.append("")

    if portfolio_drift_files:
        lines.append("## 组合权重偏移")
        for path in portfolio_drift_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            avg_abs_gap = float(df.get("abs_weight_gap_sum", pd.Series([0.0])).mean())
            max_abs_gap = float(df.get("abs_weight_gap_sum", pd.Series([0.0])).max())
            if "drift_alert_level" in df.columns:
                high = int((df["drift_alert_level"] == "high").sum())
                watch = int((df["drift_alert_level"] == "watch").sum())
                max_high_streak, high_segments = _compute_high_alert_streak(df["drift_alert_level"])
                lines.append(
                    f"- `{path.name}` avg_abs_gap={avg_abs_gap:.4f}, max_abs_gap={max_abs_gap:.4f}, "
                    f"drift_alerts(high={high}, watch={watch}, max_high_streak={max_high_streak}, "
                    f"high_segments={high_segments})"
                )
            else:
                lines.append(f"- `{path.name}` avg_abs_gap={avg_abs_gap:.4f}, max_abs_gap={max_abs_gap:.4f}")
        lines.append("")

    if portfolio_capital_files:
        lines.append("## 组合资金占用摘要")
        for path in portfolio_capital_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            equity = df.get("total_equity", pd.Series([0.0]))
            gross_ratio = df.get(
                "gross_exposure_ratio",
                df.get("gross_exposure", pd.Series([0.0])) / equity.replace(0.0, pd.NA),
            ).fillna(0.0)
            used_margin = df.get("used_margin", pd.Series([0.0]))
            available_margin = df.get("available_margin", pd.Series([0.0]))
            reserve_cash = df.get("reserve_cash", pd.Series([0.0]))
            margin_denom = (used_margin + available_margin).replace(0.0, pd.NA)
            margin_util = (used_margin / margin_denom).fillna(0.0)
            reserve_ratio = (reserve_cash / equity.replace(0.0, pd.NA)).fillna(0.0)
            lines.append(
                f"- `{path.name}` avg_exposure={float(gross_ratio.mean()):.4f}, "
                f"avg_margin_util={float(margin_util.mean()):.4f}, "
                f"peak_margin_util={float(margin_util.max()):.4f}, "
                f"avg_reserve_cash_ratio={float(reserve_ratio.mean()):.4f}"
            )
        lines.append("")

    if sim_equity_files:
        lines.append("## 单标的模拟资金曲线摘要")
        for path in sim_equity_files:
            df = pd.read_csv(path)
            if df.empty or "total_equity" not in df.columns:
                lines.append(f"- `{path.name}`: empty")
                continue
            equity = pd.to_numeric(df["total_equity"], errors="coerce").ffill().fillna(0.0)
            start_equity = float(equity.iloc[0])
            end_equity = float(equity.iloc[-1])
            total_return = (end_equity / start_equity - 1.0) if start_equity > 0 else 0.0
            drawdown = (equity / equity.cummax().replace(0.0, pd.NA) - 1.0).fillna(0.0)
            max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
            lines.append(
                f"- `{path.name}` bars={len(df)}, start_equity={start_equity:.2f}, "
                f"end_equity={end_equity:.2f}, total_return={total_return:.4f}, "
                f"max_drawdown={max_drawdown:.4f}"
            )
        lines.append("")

    if portfolio_rebalance_files:
        lines.append("## 漂移再平衡实验")
        ranking_rows: list[dict[str, float | str]] = []
        for path in portfolio_rebalance_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            trigger_cnt = int(df.get("triggered", pd.Series([0])).sum())
            turnover = float(df.get("rebalance_turnover", pd.Series([0.0])).sum())
            cost = float(df.get("rebalance_cost", pd.Series([0.0])).sum())
            avg_cost = cost / trigger_cnt if trigger_cnt > 0 else 0.0
            lines.append(
                f"- `{path.name}` triggers={trigger_cnt}, "
                f"turnover={turnover:.4f}, cost={cost:.4f}"
            )
            ranking_rows.append(
                {
                    "file": path.name,
                    "trigger_count": trigger_cnt,
                    "cost": cost,
                    "avg_cost_per_trigger": avg_cost,
                }
            )
        if ranking_rows:
            ranked = sorted(ranking_rows, key=lambda x: (float(x["avg_cost_per_trigger"]), float(x["cost"])))
            best = ranked[0]
            worst = ranked[-1]
            lines.append(
                f"- best_by_avg_cost: `{best['file']}` avg_cost_per_trigger={float(best['avg_cost_per_trigger']):.6f}"
            )
            lines.append(
                f"- worst_by_avg_cost: `{worst['file']}` avg_cost_per_trigger={float(worst['avg_cost_per_trigger']):.6f}"
            )
        lines.append("")

    if wf_files:
        lines.append("## Walk-Forward 汇总")
        for path in wf_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            lines.append(
                f"- `{path.name}`: windows={payload.get('window_count', 0)}, "
                f"avg_test_sharpe={payload.get('avg_test_sharpe', 0):.4f}"
            )
        lines.append("")

    if stability_files:
        lines.append("## 参数稳定性")
        for path in stability_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            lines.append(
                f"- `{path.name}`: windows={payload.get('window_count', 0):.0f}, "
                f"top_param_share={payload.get('top_param_set_share', 0):.4f}, "
                f"positive_sharpe_ratio={payload.get('positive_sharpe_ratio', 0):.4f}"
            )
        lines.append("")

    if leaderboard_files:
        lines.append("## 多策略排行榜")
        excess_rows: list[dict[str, object]] = []
        for path in leaderboard_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            top = df.iloc[0]
            lines.append(
                f"- `{path.name}` top1={top.get('strategy')}@{top.get('symbol')} "
                f"score={float(top.get('composite_score', 0.0)):.4f}"
            )
            if "excess_total_return" in df.columns:
                temp = df.copy()
                temp["excess_total_return"] = pd.to_numeric(temp["excess_total_return"], errors="coerce")
                temp = temp.dropna(subset=["excess_total_return"]).reset_index(drop=True)
                if not temp.empty:
                    top_excess = temp.sort_values("excess_total_return", ascending=False).iloc[0]
                    bottom_excess = temp.sort_values("excess_total_return", ascending=True).iloc[0]
                    lines.append(
                        f"- `{path.name}` excess_top={top_excess.get('strategy')}@{top_excess.get('symbol')} "
                        f"({float(top_excess.get('excess_total_return', 0.0)):.4f}), "
                        f"excess_bottom={bottom_excess.get('strategy')}@{bottom_excess.get('symbol')} "
                        f"({float(bottom_excess.get('excess_total_return', 0.0)):.4f})"
                    )
                    excess_rows.extend(
                        [
                            {
                                "file": path.name,
                                "symbol": str(top_excess.get("symbol", "-")),
                                "strategy": str(top_excess.get("strategy", "-")),
                                "excess_total_return": float(top_excess.get("excess_total_return", 0.0)),
                            },
                            {
                                "file": path.name,
                                "symbol": str(bottom_excess.get("symbol", "-")),
                                "strategy": str(bottom_excess.get("strategy", "-")),
                                "excess_total_return": float(bottom_excess.get("excess_total_return", 0.0)),
                            },
                        ]
                    )
        if excess_rows:
            excess_df = pd.DataFrame(excess_rows).drop_duplicates()
            if not excess_df.empty:
                agg_top = excess_df.sort_values("excess_total_return", ascending=False).iloc[0]
                agg_bottom = excess_df.sort_values("excess_total_return", ascending=True).iloc[0]
                lines.append(
                    f"- aggregate_excess_top: `{agg_top.get('file')}` {agg_top.get('strategy')}@{agg_top.get('symbol')} "
                    f"({float(agg_top.get('excess_total_return', 0.0)):.4f})"
                )
                lines.append(
                    f"- aggregate_excess_bottom: `{agg_bottom.get('file')}` "
                    f"{agg_bottom.get('strategy')}@{agg_bottom.get('symbol')} "
                    f"({float(agg_bottom.get('excess_total_return', 0.0)):.4f})"
                )
        lines.append("")

    if symbol_leaderboard_files:
        lines.append("## 分组排行榜（按标的）")
        for path in symbol_leaderboard_files:
            df = pd.read_csv(path)
            champions = _extract_symbol_champions(df)
            if champions.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            champion_text = ", ".join(
                f"{row.get('symbol')}:{row.get('strategy')}({float(row.get('composite_score', 0.0)):.4f})"
                for _, row in champions.iterrows()
            )
            lines.append(f"- `{path.name}` champions={champion_text}")
        lines.append("")

        recent_symbol_files = sorted(symbol_leaderboard_files, key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        history_rows: list[dict[str, Any]] = []
        for path in sorted(recent_symbol_files, key=lambda p: p.stat().st_mtime):
            champions = _extract_symbol_champions(pd.read_csv(path))
            if champions.empty:
                continue
            for _, row in champions.iterrows():
                history_rows.append(
                    {
                        "file": path.name,
                        "ts": pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC"),
                        "symbol": str(row.get("symbol", "")),
                        "strategy": str(row.get("strategy", "")),
                    }
                )
        if history_rows:
            lines.append("## 分组冠军稳定性")
            history = pd.DataFrame(history_rows).sort_values(["symbol", "ts", "file"], ascending=[True, True, True])
            for symbol, group in history.groupby("symbol"):
                ordered = group.reset_index(drop=True)
                strategies = ordered["strategy"].astype(str).tolist()
                switches = sum(1 for i in range(1, len(strategies)) if strategies[i] != strategies[i - 1])
                unique_count = len(set(strategies))
                latest_strategy = strategies[-1] if strategies else "-"
                alert_level = _switch_alert_level(
                    switches,
                    watch_threshold=champion_switch_watch_threshold,
                    high_threshold=champion_switch_high_threshold,
                )
                lines.append(
                    f"- {symbol}: samples={len(strategies)}, switches={switches}, "
                    f"unique_champions={unique_count}, latest={latest_strategy}, alert={alert_level}"
                )
            lines.append("")

    if run_config_rows:
        lines.append("## 批处理执行摘要")
        failed_cmd_counts: dict[str, int] = {}
        for path, payload in run_config_rows:
            task_count = int(payload.get("task_count", 0) or 0)
            success_count = int(payload.get("success_count", 0) or 0)
            failed_count = int(payload.get("failed_count", 0) or 0)
            run_id = str(payload.get("run_id", "-"))
            duration_ms = float(payload.get("run_duration_ms", 0.0) or 0.0)
            run_duration_s = duration_ms / 1000.0 if duration_ms > 0 else 0.0
            results = payload.get("results", [])
            slowest = "-"
            if isinstance(results, list) and results:
                slow_row = max(
                    (r for r in results if isinstance(r, dict)),
                    key=lambda x: float(x.get("duration_ms", 0.0) or 0.0),
                    default=None,
                )
                if slow_row is not None:
                    slowest = (
                        f"{slow_row.get('command', '-')}"
                        f"({float(slow_row.get('duration_ms', 0.0) or 0.0):.1f}ms)"
                    )
                for row in results:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("status", "")) != "failed":
                        continue
                    cmd = str(row.get("command", "-"))
                    failed_cmd_counts[cmd] = failed_cmd_counts.get(cmd, 0) + 1
            lines.append(
                f"- `{path.name}` run_id={run_id}, tasks={task_count}, "
                f"success={success_count}, failed={failed_count}, "
                f"duration={run_duration_s:.2f}s, slowest={slowest}"
            )
            champion_runs = payload.get("symbol_group_champions", [])
            if isinstance(champion_runs, list):
                for entry in champion_runs:
                    if not isinstance(entry, dict):
                        continue
                    champions = entry.get("champions", [])
                    if not isinstance(champions, list) or not champions:
                        continue
                    champion_parts: list[str] = []
                    for item in champions:
                        if not isinstance(item, dict):
                            continue
                        score_value = pd.to_numeric(pd.Series([item.get("composite_score")]), errors="coerce").iloc[0]
                        score = 0.0 if pd.isna(score_value) else float(score_value)
                        champion_parts.append(
                            f"{str(item.get('symbol', '-'))}:{str(item.get('strategy', '-'))}({score:.4f})"
                        )
                    champion_text = ", ".join(champion_parts)
                    if champion_text:
                        lines.append(
                            f"- `{path.name}` compare_task#{int(entry.get('task_index', 0) or 0)} "
                            f"champions={champion_text}"
                        )
        if failed_cmd_counts:
            top_items = sorted(failed_cmd_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
            top_text = ", ".join(f"{cmd}:{cnt}" for cmd, cnt in top_items)
            lines.append(f"- failed_top_commands: {top_text}")
        sorted_rows = sorted(run_config_rows, key=lambda item: _extract_run_summary_time(item[0], item[1]), reverse=True)

        def _build_aggregate_text(label: str, rows: list[tuple[Path, dict[str, object]]]) -> str:
            run_failed = sum(1 for _, payload in rows if int(payload.get("failed_count", 0) or 0) > 0)
            total_tasks = sum(int(payload.get("task_count", 0) or 0) for _, payload in rows)
            failed_tasks = sum(int(payload.get("failed_count", 0) or 0) for _, payload in rows)
            run_fail_rate = _safe_ratio(float(run_failed), float(len(rows)))
            task_fail_rate = _safe_ratio(float(failed_tasks), float(total_tasks))

            task_rows: list[dict[str, object]] = []
            for _, payload in rows:
                result_list = payload.get("results", [])
                if not isinstance(result_list, list):
                    continue
                task_rows.extend([x for x in result_list if isinstance(x, dict)])

            def _retry_used(row: dict[str, object]) -> int:
                raw = row.get("retries_used")
                if raw is None:
                    attempts = int(row.get("attempts", 1) or 1)
                    return max(0, attempts - 1)
                return max(0, int(raw or 0))

            retried_rows = [r for r in task_rows if _retry_used(r) > 0]
            retry_success_rows = [r for r in retried_rows if str(r.get("status", "")) == "success"]
            total_retries_used = sum(_retry_used(r) for r in task_rows)
            retry_hit_rate = _safe_ratio(float(len(retry_success_rows)), float(len(retried_rows)))
            failed_rows = [r for r in task_rows if str(r.get("status", "")) == "failed"]
            non_retryable_failed = [
                r
                for r in failed_rows
                if bool(r.get("retry_retryable_only", False))
                and int(r.get("retry_count", 0) or 0) > 0
                and _retry_used(r) == 0
            ]
            non_retryable_fail_share = _safe_ratio(float(len(non_retryable_failed)), float(len(failed_rows)))

            durations_s = [
                float(payload.get("run_duration_ms", 0.0) or 0.0) / 1000.0
                for _, payload in rows
                if float(payload.get("run_duration_ms", 0.0) or 0.0) > 0
            ]
            if durations_s:
                duration_series = pd.Series(durations_s, dtype=float)
                avg_duration = float(duration_series.mean())
                p50_duration = float(duration_series.quantile(0.5))
                p90_duration = float(duration_series.quantile(0.9))
            else:
                avg_duration = 0.0
                p50_duration = 0.0
                p90_duration = 0.0
            return (
                f"- {label}: run_fail_rate={run_fail_rate:.4f}, "
                f"task_fail_rate={task_fail_rate:.4f}, avg_duration={avg_duration:.2f}s, "
                f"p50_duration={p50_duration:.2f}s, p90_duration={p90_duration:.2f}s, "
                f"retry_hit_rate={retry_hit_rate:.4f}, total_retries_used={total_retries_used}, "
                f"non_retryable_fail_share={non_retryable_fail_share:.4f}"
            )

        lines.append(_build_aggregate_text("aggregate_all_runs", sorted_rows))
        recent_n = min(max(1, int(champion_switch_recent_runs)), len(sorted_rows))
        recent_rows = sorted_rows[:recent_n]
        lines.append(_build_aggregate_text(f"aggregate_last_{len(recent_rows)}_runs", recent_rows))
        _, switch_rows = _collect_recent_champion_switch_rows(
            run_config_rows,
            recent_runs=champion_switch_recent_runs,
            watch_threshold=champion_switch_watch_threshold,
            high_threshold=champion_switch_high_threshold,
        )
        if switch_rows:
            switch_parts = [
                (
                    f"{row['symbol']}(samples={row['samples']},switches={row['switches']},"
                    f"unique={row['unique_champions']},latest={row['latest']})"
                    f"[alert={row['alert_level']}]"
                )
                for row in switch_rows
            ]
            lines.append(f"- champion_switch_last_{len(recent_rows)}_runs: " + "; ".join(switch_parts))
        lines.append("")

    if retry_budget_trace_files:
        lines.append("## 重试预算轨迹")
        total_rows = 0
        total_depleted = 0
        total_consumed = 0.0
        total_failed = 0
        total_depleted_failed = 0
        aggregate_depleted_cmd_counts: dict[str, int] = {}
        run_stats: list[dict[str, Any]] = []
        for path in retry_budget_trace_files:
            df = pd.read_csv(path)
            if df.empty:
                lines.append(f"- `{path.name}`: empty")
                continue
            budget_before = pd.to_numeric(df.get("budget_before", pd.Series(dtype=float)), errors="coerce")
            budget_after = pd.to_numeric(df.get("budget_after", pd.Series(dtype=float)), errors="coerce")
            retries_used = pd.to_numeric(df.get("retries_used", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
            consumed = (budget_before - budget_after).fillna(retries_used).clip(lower=0.0)
            depleted_mask = ((budget_after <= 0) & (retries_used > 0)) if not budget_after.empty else pd.Series([], dtype=bool)
            depleted = int(depleted_mask.sum())
            status_series = df.get("status", pd.Series(dtype=object)).fillna("").astype(str)
            failed = int(status_series.eq("failed").sum()) if not status_series.empty else 0
            depleted_failed = (
                int((depleted_mask & status_series.eq("failed")).sum())
                if not status_series.empty
                else 0
            )
            failed_ratio = _safe_ratio(float(failed), float(len(df)))
            avg_consumed = float(consumed.mean()) if not consumed.empty else 0.0
            final_remaining = float(budget_after.iloc[-1]) if not budget_after.empty else 0.0
            depleted_cmd_text = "-"
            if depleted > 0 and "command" in df.columns:
                depleted_cmds = df.loc[depleted_mask, "command"].fillna("").astype(str)
                cmd_counts = depleted_cmds.value_counts().to_dict()
                for cmd, cnt in cmd_counts.items():
                    aggregate_depleted_cmd_counts[cmd] = aggregate_depleted_cmd_counts.get(cmd, 0) + int(cnt)
                top_items = sorted(cmd_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
                depleted_cmd_text = ",".join(f"{cmd}:{cnt}" for cmd, cnt in top_items)
            lines.append(
                f"- `{path.name}` rows={len(df)}, depleted_events={depleted}, "
                f"avg_consumed={avg_consumed:.4f}, final_remaining={final_remaining:.1f}, "
                f"failed_rows={failed}, failed_ratio={failed_ratio:.4f}, depleted_failed={depleted_failed}, "
                f"depleted_top_commands={depleted_cmd_text}"
            )
            total_rows += len(df)
            total_depleted += depleted
            total_consumed += float(consumed.sum()) if not consumed.empty else 0.0
            total_failed += failed
            total_depleted_failed += depleted_failed

            if "run_id" in df.columns and not df["run_id"].dropna().empty:
                grouped = df.groupby(df["run_id"].astype(str), sort=False)
                for run_id, run_df in grouped:
                    run_before = pd.to_numeric(run_df.get("budget_before", pd.Series(dtype=float)), errors="coerce")
                    run_after = pd.to_numeric(run_df.get("budget_after", pd.Series(dtype=float)), errors="coerce")
                    run_used = pd.to_numeric(run_df.get("retries_used", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
                    run_depleted_mask = (
                        ((run_after <= 0) & (run_used > 0)) if not run_after.empty else pd.Series([], dtype=bool)
                    )
                    run_status = run_df.get("status", pd.Series(dtype=object)).fillna("").astype(str)
                    run_failed = int(run_status.eq("failed").sum()) if not run_status.empty else 0
                    run_stats.append(
                        {
                            "run_id": run_id,
                            "rows": len(run_df),
                            "depleted_events": int(run_depleted_mask.sum()),
                            "depleted_rate": _safe_ratio(float(run_depleted_mask.sum()), float(len(run_df))),
                            "failed_ratio": _safe_ratio(float(run_failed), float(len(run_df))),
                            "sort_time": _parse_run_id_time(run_id)
                            or pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC"),
                        }
                    )
            else:
                run_stats.append(
                    {
                        "run_id": path.stem,
                        "rows": len(df),
                        "depleted_events": depleted,
                        "depleted_rate": _safe_ratio(float(depleted), float(len(df))),
                        "failed_ratio": failed_ratio,
                        "sort_time": pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC"),
                    }
                )
        if total_rows > 0:
            lines.append(
                f"- aggregate: files={len(retry_budget_trace_files)}, rows={total_rows}, "
                f"depleted_events={total_depleted}, avg_consumed={total_consumed / total_rows:.4f}, "
                f"failed_rows={total_failed}, failed_ratio={_safe_ratio(float(total_failed), float(total_rows)):.4f}, "
                f"depleted_failed={total_depleted_failed}"
            )
            if aggregate_depleted_cmd_counts:
                top_items = sorted(aggregate_depleted_cmd_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
                lines.append("- aggregate_depleted_top_commands: " + ", ".join(f"{cmd}:{cnt}" for cmd, cnt in top_items))
            if run_stats:
                sorted_run_stats = sorted(run_stats, key=lambda x: (x["sort_time"], x["run_id"]), reverse=True)
                recent_n = min(10, len(sorted_run_stats))
                recent_runs = sorted_run_stats[:recent_n]
                depleted_run_rate = _safe_ratio(
                    float(sum(1 for x in recent_runs if int(x["depleted_events"]) > 0)),
                    float(len(recent_runs)),
                )
                avg_depleted_rate = (
                    float(pd.Series([float(x["depleted_rate"]) for x in recent_runs], dtype=float).mean())
                    if recent_runs
                    else 0.0
                )
                avg_failed_ratio = (
                    float(pd.Series([float(x["failed_ratio"]) for x in recent_runs], dtype=float).mean())
                    if recent_runs
                    else 0.0
                )
                lines.append(
                    f"- aggregate_last_{recent_n}_runs: depleted_run_rate={depleted_run_rate:.4f}, "
                    f"avg_depleted_rate={avg_depleted_rate:.4f}, avg_failed_ratio={avg_failed_ratio:.4f}"
                )
        lines.append("")

    if preset_compare_csv.exists():
        lines.append("## 预设对比摘要")
        df = pd.read_csv(preset_compare_csv)
        if df.empty:
            lines.append(f"- `{preset_compare_csv.relative_to(output_dir)}`: empty")
        else:
            lines.append(f"- `{preset_compare_csv.relative_to(output_dir)}` rows={len(df)}")
            if "preset" in df.columns:
                pivot = df.set_index("preset")
                if "conservative" in pivot.index and "aggressive" in pivot.index:
                    for field in [
                        "total_return",
                        "sharpe",
                        "calmar",
                        "max_drawdown",
                        "avg_exposure",
                        "avg_margin_util",
                        "peak_margin_util",
                        "avg_reserve_cash_ratio",
                        "failed_count",
                        "run_duration_ms",
                    ]:
                        if field in pivot.columns:
                            aggr_v = pd.to_numeric(pd.Series([pivot.loc["aggressive", field]]), errors="coerce").iloc[0]
                            cons_v = pd.to_numeric(pd.Series([pivot.loc["conservative", field]]), errors="coerce").iloc[0]
                            gap = (0.0 if pd.isna(aggr_v) else float(aggr_v)) - (
                                0.0 if pd.isna(cons_v) else float(cons_v)
                            )
                            lines.append(f"- aggressive_minus_conservative.{field}={gap:.4f}")
            snapshot_files = sorted((output_dir / "preset_compare").glob("preset_compare_*.csv"))
            if snapshot_files:
                def _load_gap(path: Path) -> float:
                    snap = pd.read_csv(path)
                    if snap.empty or "preset" not in snap.columns or "total_return" not in snap.columns:
                        return 0.0
                    pivot = snap.set_index("preset")
                    if "conservative" not in pivot.index or "aggressive" not in pivot.index:
                        return 0.0
                    return float(pivot.loc["aggressive"]["total_return"] - pivot.loc["conservative"]["total_return"])

                latest = snapshot_files[-1]
                latest_gap = _load_gap(latest)
                lines.append(f"- history.latest_snapshot=`{latest.name}`, total_return_gap={latest_gap:.4f}")
                if len(snapshot_files) >= 2:
                    prev = snapshot_files[-2]
                    prev_gap = _load_gap(prev)
                    lines.append(
                        f"- history.prev_snapshot=`{prev.name}`, total_return_gap={prev_gap:.4f}, "
                        f"delta={latest_gap - prev_gap:.4f}"
                    )
                trend_n = min(10, len(snapshot_files))
                recent = snapshot_files[-trend_n:]
                recent_gaps = pd.Series([_load_gap(x) for x in recent], dtype=float)
                improving = int((recent_gaps.diff() > 0).sum()) if len(recent_gaps) > 1 else 0
                transitions = max(1, len(recent_gaps) - 1)
                lines.append(
                    f"- history.aggregate_last_{trend_n}_snapshots: avg_gap={float(recent_gaps.mean()):.4f}, "
                    f"min_gap={float(recent_gaps.min()):.4f}, max_gap={float(recent_gaps.max()):.4f}, "
                    f"improving_ratio={_safe_ratio(float(improving), float(transitions)):.4f}"
                )
            if preset_cleanup_json.exists():
                cleanup = _load_json_file(preset_cleanup_json)
                generated_at = str(cleanup.get("generated_at", "-") or "-")
                lines.append(
                    f"- cleanup.latest: generated_at={generated_at}, "
                    f"before={_safe_int(cleanup.get('before_count', 0))}, "
                    f"after={_safe_int(cleanup.get('after_count', 0))}, "
                    f"removed_by_date_range={_safe_int(cleanup.get('removed_by_date_range', 0))}, "
                    f"removed_by_count={_safe_int(cleanup.get('removed_by_count', 0))}, "
                    f"keep_snapshot_count={_safe_int(cleanup.get('keep_snapshot_count', 0))}"
                )
                cleanup_history_files = sorted((output_dir / "preset_compare").glob("preset_compare_cleanup_*.json"))
                cleanup_rows: list[dict[str, object]] = []
                history_files_total = 0
                skipped_invalid_time = 0
                invalid_numeric_rows = 0
                for path in cleanup_history_files:
                    if path.name == "preset_compare_cleanup_latest.json":
                        continue
                    history_files_total += 1
                    payload = _load_json_file(path)
                    ts = pd.to_datetime(str(payload.get("generated_at", "")), utc=True, errors="coerce")
                    if pd.isna(ts):
                        skipped_invalid_time += 1
                        continue
                    removed_by_date, invalid_date = _safe_int_with_flag(payload.get("removed_by_date_range", 0))
                    removed_by_count, invalid_count = _safe_int_with_flag(payload.get("removed_by_count", 0))
                    if invalid_date or invalid_count:
                        invalid_numeric_rows += 1
                    cleanup_rows.append(
                        {
                            "generated_at": ts,
                            "removed_total": removed_by_date + removed_by_count,
                        }
                    )
                if cleanup_rows:
                    recent_n = min(10, len(cleanup_rows))
                    recent_df = (
                        pd.DataFrame(cleanup_rows)
                        .sort_values("generated_at")
                        .tail(recent_n)
                        .reset_index(drop=True)
                    )
                    first_ts = recent_df["generated_at"].iloc[0]
                    latest_ts = recent_df["generated_at"].iloc[-1]
                    span_hours = max(0.0, float((latest_ts - first_ts).total_seconds() / 3600.0))
                    abnormal_rows = skipped_invalid_time + invalid_numeric_rows
                    abnormal_ratio = _safe_ratio(float(abnormal_rows), float(history_files_total))
                    lines.append(
                        f"- cleanup.aggregate_last_{recent_n}_runs: first_generated_at={first_ts.isoformat()}, "
                        f"latest_generated_at={latest_ts.isoformat()}, span_hours={span_hours:.2f}, "
                        f"history_files={history_files_total}, valid_runs={len(cleanup_rows)}, "
                        f"avg_removed_total={float(recent_df['removed_total'].mean()):.2f}, "
                        f"max_removed_total={int(recent_df['removed_total'].max())}, "
                        f"skipped_invalid_time={skipped_invalid_time}, "
                        f"rows_with_invalid_numeric={invalid_numeric_rows}, "
                        f"abnormal_ratio={abnormal_ratio:.4f}"
                    )
        lines.append("")

    if len(lines) <= 2:
        lines.append("当前没有可汇总的输出文件。")

    return "\n".join(lines).strip() + "\n"
