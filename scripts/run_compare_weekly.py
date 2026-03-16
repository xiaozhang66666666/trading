#!/usr/bin/env python3
"""Render and run weekly compare config with dynamic date overrides."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def _parse_iso_date(raw: str, arg_name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{arg_name} 日期格式错误，需为 YYYY-MM-DD: {raw}") from exc


def _default_dates() -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=365 * 5)
    return start.isoformat(), end.isoformat()


def parse_args() -> argparse.Namespace:
    start_default, end_default = _default_dates()
    parser = argparse.ArgumentParser(description="渲染并执行周频 compare 模板")
    parser.add_argument("--config", default="examples/config.compare.weekly.json", help="周频模板路径")
    parser.add_argument("--start", default=start_default, help="开始日期（YYYY-MM-DD）")
    parser.add_argument("--end", default=end_default, help="结束日期（YYYY-MM-DD）")
    parser.add_argument("--symbols", help="覆盖 symbols，逗号分隔，例如 QQQ,ETH")
    parser.add_argument("--strategies", help="覆盖 strategies，逗号分隔")
    parser.add_argument("--output-config", help="渲染后配置输出路径（默认 outputs/compare_weekly_rendered_<ts>.json）")
    parser.add_argument("--no-run", action="store_true", help="仅渲染，不执行")
    parser.add_argument("--keep-rendered", action="store_true", help="执行成功后保留自动渲染文件")
    return parser.parse_args()


def _split_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    if not parts:
        raise ValueError("覆盖列表不能为空")
    return parts


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / args.config).resolve()
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    try:
        start = _parse_iso_date(args.start, "--start")
        end = _parse_iso_date(args.end, "--end")
        if start >= end:
            raise ValueError("--start 必须早于 --end")
        symbols = _split_csv(args.symbols)
        strategies = _split_csv(args.strategies)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("配置文件必须是 JSON 对象", file=sys.stderr)
        return 1

    payload["start"] = start.isoformat()
    payload["end"] = end.isoformat()
    payload["interval"] = "1wk"
    if symbols is not None:
        payload["symbols"] = symbols
    if strategies is not None:
        payload["strategies"] = strategies

    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    auto_generated = False
    if args.output_config:
        rendered_path = (project_root / args.output_config).resolve()
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rendered_path = output_dir / f"compare_weekly_rendered_{ts}.json"
        auto_generated = True

    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"渲染配置: {rendered_path}")

    if args.no_run:
        return 0

    cmd = [sys.executable, "-m", "market_signal_system", "run-config", "--file", str(rendered_path)]
    proc = subprocess.run(cmd, cwd=str(project_root), check=False)
    if proc.returncode != 0:
        return proc.returncode

    if auto_generated and not args.keep_rendered and rendered_path.exists():
        rendered_path.unlink()
        print(f"已清理临时配置: {rendered_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
