#!/usr/bin/env python3
"""Run and compare conservative/aggressive batch presets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_signal_system.research.preset_compare import compare_presets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键运行并对比保守/激进批处理预设")
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="输出目录（默认 outputs）",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="仅基于已有工件生成对比，不重新执行批处理",
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="仅执行快照清理与诊断落盘，不生成新的对比 CSV/Markdown",
    )
    parser.add_argument("--start", help="覆盖预设 vars.start（如 2020-01-01）")
    parser.add_argument("--end", help="覆盖预设 vars.end（如 2025-12-31）")
    parser.add_argument(
        "--keep-snapshots",
        type=int,
        default=20,
        help="保留最近 N 份 preset_compare_<timestamp>.csv（0 表示不清理）",
    )
    parser.add_argument(
        "--snapshot-keep-start",
        help="快照保留起点（UTC，支持 YYYY-MM-DD 或 YYYYMMDDTHHMMSSZ）；早于该时间的快照会被清理",
    )
    parser.add_argument(
        "--snapshot-keep-end",
        help="快照保留终点（UTC，支持 YYYY-MM-DD 或 YYYYMMDDTHHMMSSZ）；晚于该时间的快照会被清理",
    )
    parser.add_argument(
        "--keep-cleanup-history",
        type=int,
        default=50,
        help="保留最近 N 份 preset_compare_cleanup_<timestamp>.json（0 表示不清理）",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    project_root = PROJECT_ROOT
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    if (args.start and not args.end) or (args.end and not args.start):
        parser.error("--start 与 --end 需要同时提供")
    if args.keep_snapshots < 0:
        parser.error("--keep-snapshots 不能小于 0")
    if args.keep_cleanup_history < 0:
        parser.error("--keep-cleanup-history 不能小于 0")

    vars_override = None
    if args.start and args.end:
        vars_override = {"start": args.start, "end": args.end}

    try:
        csv_path, md_path = compare_presets(
            project_root=project_root,
            output_dir=output_dir,
            run_batches=(not args.no_run) and (not args.cleanup_only),
            vars_override=vars_override,
            keep_snapshot_count=args.keep_snapshots,
            cleanup_keep_start=args.snapshot_keep_start,
            cleanup_keep_end=args.snapshot_keep_end,
            cleanup_only=args.cleanup_only,
            keep_cleanup_history_count=args.keep_cleanup_history,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.cleanup_only:
        cleanup_path = output_dir / "preset_compare" / "preset_compare_cleanup_latest.json"
        print(f"Preset compare cleanup: {cleanup_path}")
    else:
        print(f"Preset compare CSV: {csv_path}")
        print(f"Preset compare Markdown: {md_path}")


if __name__ == "__main__":
    main()
