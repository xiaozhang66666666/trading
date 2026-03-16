#!/usr/bin/env python3
"""Render and run baseline daily batch config with dynamic dates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _default_dates() -> tuple[str, str, str]:
    as_of = datetime.now(timezone.utc).date()
    start = (as_of - timedelta(days=365 * 5)).isoformat()
    end = as_of.isoformat()
    return start, end, end


def parse_args() -> argparse.Namespace:
    start_default, end_default, as_of_default = _default_dates()
    parser = argparse.ArgumentParser(description="渲染并执行 baseline daily 批处理")
    parser.add_argument("--config", default="examples/config.batch.baseline.daily.json", help="baseline 模板路径")
    parser.add_argument("--start", default=start_default, help="MVP 开始日期（YYYY-MM-DD）")
    parser.add_argument("--end", default=end_default, help="MVP 结束日期（YYYY-MM-DD）")
    parser.add_argument("--as-of", default=as_of_default, help="Signal Pilot 统计日期（YYYY-MM-DD）")
    parser.add_argument("--output-config", help="渲染后配置输出路径（默认 outputs/baseline_daily_rendered_<ts>.json）")
    parser.add_argument("--no-run", action="store_true", help="只渲染不执行")
    parser.add_argument("--keep-rendered", action="store_true", help="执行后保留渲染配置")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / args.config).resolve()
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("配置文件必须是 JSON 对象", file=sys.stderr)
        return 1

    merged_vars = dict(payload.get("vars", {}))
    merged_vars.update({"start": args.start, "end": args.end, "as_of": args.as_of})
    payload["vars"] = merged_vars

    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.output_config:
        rendered_path = (project_root / args.output_config).resolve()
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rendered_path = output_dir / f"baseline_daily_rendered_{ts}.json"

    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"渲染配置: {rendered_path}")

    if args.no_run:
        return 0

    cmd = [sys.executable, "-m", "market_signal_system", "run-config", "--file", str(rendered_path)]
    proc = subprocess.run(cmd, cwd=str(project_root), check=False)
    if proc.returncode != 0:
        return proc.returncode

    if not args.keep_rendered and args.output_config is None and rendered_path.exists():
        rendered_path.unlink()
        print(f"已清理临时配置: {rendered_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
