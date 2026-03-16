#!/usr/bin/env python3
"""Build a compact MVP leaderboard report from mvp_summary JSON."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"


def _pick_latest_summary(output_dir: Path) -> Path:
    candidates = sorted(output_dir.glob("mvp_summary_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"未找到 mvp_summary_*.json: {output_dir}")
    return candidates[0]


def _load_summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mvp summary 必须是 JSON 对象")
    backtests = payload.get("backtests")
    if not isinstance(backtests, list) or not backtests:
        raise ValueError("mvp summary 缺少 backtests 或为空")
    return payload


def _build_rank_rows(backtests: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in backtests:
        symbol = str(row.get("symbol", "")).upper()
        grouped.setdefault(symbol, []).append(row)

    ranked_rows: list[dict] = []
    for symbol, rows in grouped.items():
        ranked = sorted(
            rows,
            key=lambda x: (
                float(x.get("sharpe", 0.0)),
                float(x.get("total_return", 0.0)),
                -float(x.get("max_drawdown", 0.0)),
            ),
            reverse=True,
        )
        for idx, row in enumerate(ranked, start=1):
            ranked_rows.append(
                {
                    "symbol": symbol,
                    "symbol_rank": idx,
                    "strategy": str(row.get("strategy", "")),
                    "sharpe": float(row.get("sharpe", 0.0)),
                    "total_return": float(row.get("total_return", 0.0)),
                    "max_drawdown": float(row.get("max_drawdown", 0.0)),
                    "bars": int(row.get("bars", 0)),
                    "metrics_file": str(row.get("metrics_file", "")),
                }
            )
    return ranked_rows


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "symbol_rank",
        "strategy",
        "sharpe",
        "total_return",
        "max_drawdown",
        "bars",
        "metrics_file",
    ]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(rows: list[dict], summary: dict, path: Path, leaderboard_csv: Path) -> None:
    run_tag = str(summary.get("run_tag", "unknown"))
    lines = [
        "# MVP 回测汇总",
        "",
        f"- run_tag: `{run_tag}`",
        f"- symbols: `{','.join(summary.get('symbols', []))}`",
        f"- strategies: `{','.join(summary.get('strategies', []))}`",
        f"- source_summary: `{summary.get('_source_file', '')}`",
        f"- leaderboard_csv: `{leaderboard_csv}`",
        "",
        "## 分组冠军",
    ]

    champion_map: dict[str, dict] = {}
    for row in rows:
        symbol = row["symbol"]
        if symbol not in champion_map or int(row["symbol_rank"]) < int(champion_map[symbol]["symbol_rank"]):
            champion_map[symbol] = row

    if not champion_map:
        lines.append("- 无可用冠军数据")
    else:
        for symbol in sorted(champion_map):
            c = champion_map[symbol]
            lines.append(
                "- "
                f"{symbol}: {c['strategy']} "
                f"(sharpe={c['sharpe']:.4f}, total_return={c['total_return']:.4f}, max_drawdown={c['max_drawdown']:.4f})"
            )

    lines.append("")
    lines.append("## 排行明细")
    lines.append("")
    lines.append("| symbol | rank | strategy | sharpe | total_return | max_drawdown | bars |")
    lines.append("| --- | ---: | --- | ---: | ---: | ---: | ---: |")
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['symbol_rank']} | {row['strategy']} | "
            f"{row['sharpe']:.4f} | {row['total_return']:.4f} | {row['max_drawdown']:.4f} | {row['bars']} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 mvp_summary 生成分组排行榜与简报")
    parser.add_argument("--summary-file", help="输入 mvp_summary_*.json；不传则自动选 outputs 下最新文件")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录，默认 outputs")
    parser.add_argument("--output-prefix", help="输出文件前缀；默认 mvp_report_<run_tag>")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    summary_path = Path(args.summary_file).resolve() if args.summary_file else _pick_latest_summary(output_dir)
    summary = _load_summary(summary_path)
    summary["_source_file"] = str(summary_path)
    rows = _build_rank_rows(summary.get("backtests", []))

    run_tag = str(summary.get("run_tag", "unknown"))
    output_prefix = args.output_prefix or f"mvp_report_{run_tag}"
    csv_path = output_dir / f"{output_prefix}.csv"
    md_path = output_dir / f"{output_prefix}.md"

    _write_csv(rows, csv_path)
    _write_markdown(rows, summary, md_path, csv_path)

    print(f"Saved leaderboard: {csv_path}")
    print(f"Saved report: {md_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[mvp-report] 失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
