#!/usr/bin/env python3
"""Run strict-compress failure demo and regenerate report index."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="strict 模式失败任务 + 报告汇总演示")
    parser.add_argument(
        "--config",
        default="examples/config.batch.strict_failure_demo.json",
        help="批处理配置路径（默认 strict failure demo）",
    )
    parser.add_argument(
        "--report-file",
        default="strict_failure_demo_report.md",
        help="报告输出文件名（写入 outputs/）",
    )
    parser.add_argument(
        "--allow-success",
        action="store_true",
        help="允许批处理返回 0（默认要求该演示出现失败并返回非 0）",
    )
    return parser


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    return int(proc.returncode)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    run_cmd = [
        sys.executable,
        "-m",
        "market_signal_system",
        "run-config",
        "--file",
        str(config_path),
    ]
    run_code = _run(run_cmd)
    if run_code == 0 and not args.allow_success:
        raise SystemExit("strict failure demo 期望 run-config 失败退出，但返回了 0")

    report_cmd = [
        sys.executable,
        "-m",
        "market_signal_system",
        "report",
        "--output-file",
        args.report_file,
    ]
    report_code = _run(report_cmd)
    if report_code != 0:
        raise SystemExit(f"report 生成失败，退出码={report_code}")

    outputs = PROJECT_ROOT / "outputs"
    print(f"run-config returncode: {run_code}")
    print(f"summary json: {outputs / 'strict_failure_summary.json.gz'}")
    print(f"summary csv: {outputs / 'strict_failure_summary.csv.gz'}")
    print(f"retry trace: {outputs / 'strict_failure_retry_trace.csv.gz'}")
    print(f"report: {outputs / args.report_file}")


if __name__ == "__main__":
    main()
