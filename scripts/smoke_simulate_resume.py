#!/usr/bin/env python3
"""离线冒烟：验证 simulate 在重启后可从状态文件恢复并继续交易。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_signal_system.utils.paths import CACHE_DIR, STATE_DIR, ensure_runtime_dirs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="simulate 恢复链路离线冒烟脚本")
    parser.add_argument("--symbol", default="QQQ", help="标的（默认 QQQ）")
    parser.add_argument("--strategy", default="ma_cross", help="策略（默认 ma_cross）")
    parser.add_argument("--start", default="2020-01-01", help="起始日期（默认 2020-01-01）")
    parser.add_argument("--split-end", default="2020-01-04", help="第一段结束日期（默认 2020-01-04）")
    parser.add_argument("--end", default="2020-01-06", help="第二段结束日期（默认 2020-01-06）")
    parser.add_argument(
        "--params",
        default='{"fast_window":2,"slow_window":3}',
        help='策略参数 JSON（默认 {"fast_window":2,"slow_window":3}）',
    )
    parser.add_argument("--python-bin", default=sys.executable, help="Python 可执行文件（默认当前解释器）")
    parser.add_argument("--keep-artifacts", action="store_true", help="保留本次生成的 cache/state 文件")
    return parser


def _write_offline_cache(cache_path: Path) -> None:
    cache_path.write_text(
        "\n".join(
            [
                ",open,high,low,close,volume",
                "2020-01-01T00:00:00+00:00,10,10,10,10,100",
                "2020-01-02T00:00:00+00:00,11,11,11,11,100",
                "2020-01-03T00:00:00+00:00,12,12,12,12,100",
                "2020-01-04T00:00:00+00:00,11,11,11,11,100",
                "2020-01-05T00:00:00+00:00,10,10,10,10,100",
                "2020-01-06T00:00:00+00:00,9,9,9,9,100",
            ]
        ),
        encoding="utf-8",
    )


def _run_once(
    python_bin: str,
    symbol: str,
    strategy: str,
    params: str,
    interval: str,
    start: str,
    end: str,
    state_file: str,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            python_bin,
            "-m",
            "market_signal_system",
            "simulate",
            "--symbol",
            symbol,
            "--strategy",
            strategy,
            "--params",
            params,
            "--start",
            start,
            "--end",
            end,
            "--interval",
            interval,
            "--state-file",
            state_file,
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        start_date = date.fromisoformat(args.start)
        split_end_date = date.fromisoformat(args.split_end)
        end_date = date.fromisoformat(args.end)
    except ValueError as exc:
        parser.error(f"日期格式非法: {exc}")
    if not (start_date < split_end_date < end_date):
        parser.error("日期区间要求 start < split-end < end")

    ensure_runtime_dirs()

    run_id = uuid.uuid4().hex[:10]
    interval = f"smoke_resume_{run_id}"
    state_file = f"smoke_resume_{run_id}.json"
    cache_path = CACHE_DIR / f"{args.symbol.upper()}_{interval}.csv"
    state_path = STATE_DIR / state_file

    _write_offline_cache(cache_path)
    try:
        first = _run_once(
            python_bin=args.python_bin,
            symbol=args.symbol,
            strategy=args.strategy,
            params=args.params,
            interval=interval,
            start=args.start,
            end=args.split_end,
            state_file=state_file,
        )
        if first.returncode != 0:
            raise RuntimeError(f"第一段 simulate 失败:\n{first.stderr.strip()}")
        if not state_path.exists():
            raise RuntimeError(f"第一段结束后未生成状态文件: {state_path}")
        first_state = json.loads(state_path.read_text(encoding="utf-8"))
        first_trade_count = len(first_state.get("trades", []))

        second = _run_once(
            python_bin=args.python_bin,
            symbol=args.symbol,
            strategy=args.strategy,
            params=args.params,
            interval=interval,
            start=args.start,
            end=args.end,
            state_file=state_file,
        )
        if second.returncode != 0:
            raise RuntimeError(f"第二段 simulate 失败:\n{second.stderr.strip()}")
        second_state = json.loads(state_path.read_text(encoding="utf-8"))
        second_trade_count = len(second_state.get("trades", []))

        if second_trade_count <= first_trade_count:
            raise RuntimeError(
                "恢复后交易条数未增长: "
                f"first={first_trade_count}, second={second_trade_count}"
            )
        print("simulate 恢复冒烟通过")
        print(f"- state_file: {state_path}")
        print(f"- first_trade_count: {first_trade_count}")
        print(f"- second_trade_count: {second_trade_count}")
        return 0
    finally:
        if not args.keep_artifacts:
            if cache_path.exists():
                cache_path.unlink()
            if state_path.exists():
                state_path.unlink()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI 顶层防护
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
