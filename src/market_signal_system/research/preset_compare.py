"""One-click comparison for conservative/aggressive batch presets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PresetSpec:
    tag: str
    config_file: Path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 内容必须是对象: {path}")
    return payload


def _summarize_capital(capital_path: Path) -> dict[str, float]:
    if not capital_path.exists():
        return {
            "avg_exposure": 0.0,
            "avg_margin_util": 0.0,
            "peak_margin_util": 0.0,
            "avg_reserve_cash_ratio": 0.0,
        }
    df = pd.read_csv(capital_path)
    if df.empty:
        return {
            "avg_exposure": 0.0,
            "avg_margin_util": 0.0,
            "peak_margin_util": 0.0,
            "avg_reserve_cash_ratio": 0.0,
        }
    equity = df.get("total_equity", pd.Series([0.0], dtype=float))
    gross_ratio = df.get(
        "gross_exposure_ratio",
        df.get("gross_exposure", pd.Series([0.0], dtype=float)) / equity.replace(0.0, np.nan),
    ).fillna(0.0)
    used_margin = df.get("used_margin", pd.Series([0.0], dtype=float))
    available_margin = df.get("available_margin", pd.Series([0.0], dtype=float))
    reserve_cash = df.get("reserve_cash", pd.Series([0.0], dtype=float))
    margin_util = (used_margin / (used_margin + available_margin).replace(0.0, np.nan)).fillna(0.0)
    reserve_ratio = (reserve_cash / equity.replace(0.0, np.nan)).fillna(0.0)
    return {
        "avg_exposure": float(gross_ratio.mean()),
        "avg_margin_util": float(margin_util.mean()),
        "peak_margin_util": float(margin_util.max()),
        "avg_reserve_cash_ratio": float(reserve_ratio.mean()),
    }


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _parse_cleanup_time(raw: str, field_name: str) -> datetime:
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%dT%H%M%SZ"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"{field_name} 日期格式非法: {raw}") from exc
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_snapshot_timestamp(path: Path) -> datetime | None:
    stem = path.stem
    prefix = "preset_compare_"
    if not stem.startswith(prefix):
        return None
    stamp = stem[len(prefix):]
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _cleanup_snapshot_history(
    snapshot_dir: Path,
    keep_snapshot_count: int,
    cleanup_keep_start: datetime | None = None,
    cleanup_keep_end: datetime | None = None,
    protected_files: set[Path] | None = None,
) -> dict[str, int]:
    snapshot_files = sorted(snapshot_dir.glob("preset_compare_*.csv"))
    before_count = len(snapshot_files)
    protected = {p.resolve() for p in (protected_files or set())}
    removed_by_date_range = 0
    removed_by_count = 0

    filtered: list[Path] = []
    if cleanup_keep_start is not None or cleanup_keep_end is not None:
        for path in snapshot_files:
            path_resolved = path.resolve()
            if path_resolved in protected:
                filtered.append(path)
                continue
            ts = _parse_snapshot_timestamp(path)
            if ts is None:
                filtered.append(path)
                continue
            if cleanup_keep_start is not None and ts < cleanup_keep_start:
                path.unlink(missing_ok=True)
                removed_by_date_range += 1
                continue
            if cleanup_keep_end is not None and ts > cleanup_keep_end:
                path.unlink(missing_ok=True)
                removed_by_date_range += 1
                continue
            filtered.append(path)
    else:
        filtered = snapshot_files

    if keep_snapshot_count <= 0:
        after_count = len(list(snapshot_dir.glob("preset_compare_*.csv")))
        return {
            "before_count": before_count,
            "after_count": after_count,
            "removed_by_date_range": removed_by_date_range,
            "removed_by_count": removed_by_count,
        }
    removable = [p for p in filtered if p.resolve() not in protected]
    protected_count = len(filtered) - len(removable)
    removable_target = max(0, keep_snapshot_count - protected_count)
    if len(removable) <= removable_target:
        after_count = len(list(snapshot_dir.glob("preset_compare_*.csv")))
        return {
            "before_count": before_count,
            "after_count": after_count,
            "removed_by_date_range": removed_by_date_range,
            "removed_by_count": removed_by_count,
        }
    stale = removable[: len(removable) - removable_target]
    for path in stale:
        path.unlink(missing_ok=True)
        removed_by_count += 1
    after_count = len(list(snapshot_dir.glob("preset_compare_*.csv")))
    return {
        "before_count": before_count,
        "after_count": after_count,
        "removed_by_date_range": removed_by_date_range,
        "removed_by_count": removed_by_count,
    }


def _snapshot_artifacts(
    output_dir: Path,
    snapshot_dir: Path,
    tag: str,
    symbols: str,
    strategy: str,
) -> dict[str, Path]:
    symbols_key = "_".join(s.strip().upper() for s in symbols.split(",") if s.strip())
    metrics = output_dir / f"portfolio_metrics_{strategy}_{symbols_key}.json"
    capital = output_dir / f"sim_portfolio_capital_{symbols_key}_{strategy}.csv"
    report = output_dir / f"report_index_{tag}.md"
    summary = output_dir / f"batch_{tag}_summary.json"

    metrics_snap = snapshot_dir / f"portfolio_metrics_{tag}.json"
    capital_snap = snapshot_dir / f"sim_portfolio_capital_{tag}.csv"
    report_snap = snapshot_dir / f"report_index_{tag}.md"
    summary_snap = snapshot_dir / f"batch_{tag}_summary.json"

    _copy_if_exists(metrics, metrics_snap)
    _copy_if_exists(capital, capital_snap)
    _copy_if_exists(report, report_snap)
    _copy_if_exists(summary, summary_snap)
    return {
        "metrics": metrics_snap,
        "capital": capital_snap,
        "report": report_snap,
        "summary": summary_snap,
    }


def _write_cleanup_payload(
    snapshot_dir: Path,
    cleanup_keep_start: str | None,
    cleanup_keep_end: str | None,
    keep_snapshot_count: int,
    cleanup_stats: dict[str, int],
) -> None:
    now = datetime.now(timezone.utc)
    cleanup_payload = {
        "generated_at": now.isoformat(),
        "snapshot_keep_start": cleanup_keep_start,
        "snapshot_keep_end": cleanup_keep_end,
        "keep_snapshot_count": keep_snapshot_count,
        **cleanup_stats,
    }
    (snapshot_dir / "preset_compare_cleanup_latest.json").write_text(
        json.dumps(cleanup_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    history_name = f"preset_compare_cleanup_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    (snapshot_dir / history_name).write_text(
        json.dumps(cleanup_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return


def _cleanup_cleanup_history(snapshot_dir: Path, keep_cleanup_history_count: int) -> None:
    if keep_cleanup_history_count <= 0:
        return
    history_files = sorted(
        path
        for path in snapshot_dir.glob("preset_compare_cleanup_*.json")
        if path.name != "preset_compare_cleanup_latest.json"
    )
    if len(history_files) <= keep_cleanup_history_count:
        return
    stale = history_files[: len(history_files) - keep_cleanup_history_count]
    for path in stale:
        path.unlink(missing_ok=True)


def _build_row(tag: str, artifacts: dict[str, Path]) -> dict[str, Any]:
    metrics = _load_json(artifacts["metrics"]) if artifacts["metrics"].exists() else {}
    summary = _load_json(artifacts["summary"]) if artifacts["summary"].exists() else {}
    capital_stats = _summarize_capital(artifacts["capital"])
    return {
        "preset": tag,
        "total_return": float(metrics.get("total_return", 0.0) or 0.0),
        "sharpe": float(metrics.get("sharpe", 0.0) or 0.0),
        "calmar": float(metrics.get("calmar", 0.0) or 0.0),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
        "avg_exposure": capital_stats["avg_exposure"],
        "avg_margin_util": capital_stats["avg_margin_util"],
        "peak_margin_util": capital_stats["peak_margin_util"],
        "avg_reserve_cash_ratio": capital_stats["avg_reserve_cash_ratio"],
        "failed_count": int(summary.get("failed_count", 0) or 0),
        "run_duration_ms": float(summary.get("run_duration_ms", 0.0) or 0.0),
    }


def _build_markdown(rows: pd.DataFrame) -> str:
    def _fmt_cell(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{float(value):.4f}"
        return str(value)

    def _manual_markdown_table(frame: pd.DataFrame) -> str:
        headers = [str(c) for c in frame.columns]
        head_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        body_lines = []
        for _, row in frame.iterrows():
            cells = [_fmt_cell(row[col]) for col in frame.columns]
            body_lines.append("| " + " | ".join(cells) + " |")
        return "\n".join([head_line, sep_line, *body_lines])

    lines = ["# 保守/激进模板对比", ""]
    if rows.empty:
        lines.append("无可用结果。")
        return "\n".join(lines) + "\n"
    try:
        lines.append(rows.to_markdown(index=False, floatfmt=".4f"))
    except ImportError:
        lines.append(_manual_markdown_table(rows))
    lines.append("")
    if len(rows) >= 2:
        pivot = rows.set_index("preset")
        if "conservative" in pivot.index and "aggressive" in pivot.index:
            diff = pivot.loc["aggressive"] - pivot.loc["conservative"]
            lines.append("## 激进 - 保守（差值）")
            lines.append("")
            for key in [
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
                lines.append(f"- {key}: {float(diff.get(key, 0.0)):.4f}")
            lines.append("")
    return "\n".join(lines) + "\n"


def compare_presets(
    project_root: Path,
    output_dir: Path,
    run_batches: bool = True,
    vars_override: dict[str, Any] | None = None,
    keep_snapshot_count: int = 20,
    cleanup_keep_start: str | None = None,
    cleanup_keep_end: str | None = None,
    cleanup_only: bool = False,
    keep_cleanup_history_count: int = 50,
) -> tuple[Path, Path]:
    if keep_snapshot_count < 0:
        raise ValueError("keep_snapshot_count 不能小于 0")
    if keep_cleanup_history_count < 0:
        raise ValueError("keep_cleanup_history_count 不能小于 0")
    keep_start_dt = _parse_cleanup_time(cleanup_keep_start, "cleanup_keep_start") if cleanup_keep_start else None
    keep_end_dt = _parse_cleanup_time(cleanup_keep_end, "cleanup_keep_end") if cleanup_keep_end else None
    if keep_start_dt is not None and keep_end_dt is not None and keep_start_dt > keep_end_dt:
        raise ValueError("cleanup_keep_start 不能晚于 cleanup_keep_end")
    presets = [
        PresetSpec(tag="conservative", config_file=project_root / "examples/config.batch.portfolio_conservative.json"),
        PresetSpec(tag="aggressive", config_file=project_root / "examples/config.batch.portfolio_aggressive.json"),
    ]
    snapshot_dir = output_dir / "preset_compare"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    csv_path = snapshot_dir / "preset_compare.csv"
    md_path = snapshot_dir / "preset_compare.md"

    if cleanup_only:
        cleanup_stats = _cleanup_snapshot_history(
            snapshot_dir,
            keep_snapshot_count=keep_snapshot_count,
            cleanup_keep_start=keep_start_dt,
            cleanup_keep_end=keep_end_dt,
        )
        _write_cleanup_payload(
            snapshot_dir=snapshot_dir,
            cleanup_keep_start=cleanup_keep_start,
            cleanup_keep_end=cleanup_keep_end,
            keep_snapshot_count=keep_snapshot_count,
            cleanup_stats=cleanup_stats,
        )
        _cleanup_cleanup_history(snapshot_dir, keep_cleanup_history_count=keep_cleanup_history_count)
        return csv_path, md_path

    rows: list[dict[str, Any]] = []
    for spec in presets:
        payload = _load_json(spec.config_file)
        vars_obj = payload.get("vars", {})
        symbols = str(vars_obj.get("symbols", "QQQ,ETH"))
        strategy = str(vars_obj.get("strategy", "momentum"))

        if run_batches:
            run_config_file = spec.config_file
            tmp_file: Any | None = None
            if vars_override:
                patched_payload = dict(payload)
                patched_vars = dict(vars_obj)
                patched_vars.update(vars_override)
                patched_payload["vars"] = patched_vars
                tmp_file = tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    suffix=f".{spec.tag}.json",
                    delete=False,
                )
                with tmp_file as fh:
                    fh.write(json.dumps(patched_payload, ensure_ascii=False, indent=2))
                run_config_file = Path(tmp_file.name)

            cmd = [
                sys.executable,
                "-m",
                "market_signal_system",
                "run-config",
                "--file",
                str(run_config_file),
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root / "src")
            try:
                completed = subprocess.run(cmd, cwd=str(project_root), env=env, check=False)
                if completed.returncode != 0:
                    raise RuntimeError(
                        f"批处理预设执行失败: tag={spec.tag}, returncode={completed.returncode}, config={spec.config_file}"
                    )
            finally:
                if tmp_file is not None:
                    try:
                        Path(tmp_file.name).unlink(missing_ok=True)
                    except OSError:
                        pass

        artifacts = _snapshot_artifacts(
            output_dir=output_dir,
            snapshot_dir=snapshot_dir,
            tag=spec.tag,
            symbols=symbols,
            strategy=strategy,
        )
        rows.append(_build_row(spec.tag, artifacts))

    table = pd.DataFrame(rows).sort_values("preset").reset_index(drop=True)
    table.to_csv(csv_path, index=False)
    md_path.write_text(_build_markdown(table), encoding="utf-8")
    snapshot_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_csv_path = snapshot_dir / f"preset_compare_{snapshot_tag}.csv"
    table.to_csv(snapshot_csv_path, index=False)
    cleanup_stats = _cleanup_snapshot_history(
        snapshot_dir,
        keep_snapshot_count=keep_snapshot_count,
        cleanup_keep_start=keep_start_dt,
        cleanup_keep_end=keep_end_dt,
        protected_files={snapshot_csv_path},
    )
    _write_cleanup_payload(
        snapshot_dir=snapshot_dir,
        cleanup_keep_start=cleanup_keep_start,
        cleanup_keep_end=cleanup_keep_end,
        keep_snapshot_count=keep_snapshot_count,
        cleanup_stats=cleanup_stats,
    )
    _cleanup_cleanup_history(snapshot_dir, keep_cleanup_history_count=keep_cleanup_history_count)
    return csv_path, md_path
