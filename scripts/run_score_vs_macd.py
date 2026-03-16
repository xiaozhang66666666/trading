#!/usr/bin/env python3
"""一键执行 score_regime vs macd_regime 专项对照批处理。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_signal_system.utils.emit_naming import (
    build_emit_filename,
    normalize_emit_segment,
    normalize_emit_separator,
    validate_emit_template,
)

COMPARE_TEMPLATE_MAP = {
    "qqq": PROJECT_ROOT / "examples" / "config.batch.score_vs_macd_compare.json",
    "eth": PROJECT_ROOT / "examples" / "config.batch.score_vs_macd_compare.eth.json",
}

NAMING_DEMO_TEMPLATE_MAP = {
    "qqq": PROJECT_ROOT / "examples" / "config.batch.score_vs_macd_naming_demo.json",
    "eth": PROJECT_ROOT / "examples" / "config.batch.score_vs_macd_naming_demo.eth.json",
}


def _validate_args(args: argparse.Namespace) -> None:
    if args.run and (args.no_run or args.dry_run):
        raise ValueError("--run 不能与 --no-run/--dry-run 同时使用")
    if args.no_run and args.dry_run:
        raise ValueError("--no-run 与 --dry-run 不能同时使用")
    if args.emit_config and args.emit_config_dir:
        raise ValueError("--emit-config 与 --emit-config-dir 不能同时使用")
    if args.keep_temp_config and (args.emit_config or args.emit_config_dir):
        raise ValueError("--keep-temp-config 与 --emit-config/--emit-config-dir 不能同时使用（渲染配置默认保留）")
    if args.keep_temp_config and (args.no_run or args.dry_run):
        raise ValueError("--keep-temp-config 仅在真实执行路径有效")
    if args.keep_emitted_configs < 0:
        raise ValueError("--keep-emitted-configs 必须 >= 0")
    if args.keep_emitted_configs > 0:
        if not args.emit_config and not args.emit_config_dir:
            raise ValueError("--keep-emitted-configs 需要与 --emit-config 或 --emit-config-dir 一起使用")
        if args.emit_config and "{ts}" not in args.emit_config:
            raise ValueError("--keep-emitted-configs 仅支持与包含 {ts} 的 --emit-config 一起使用")
    if args.emit_prefix:
        if not args.emit_config_dir:
            raise ValueError("--emit-prefix 仅支持与 --emit-config-dir 一起使用")
        normalize_emit_segment(args.emit_prefix, "--emit-prefix")
    if args.emit_tag:
        if not args.emit_config_dir:
            raise ValueError("--emit-tag 仅支持与 --emit-config-dir 一起使用")
        normalize_emit_segment(args.emit_tag, "--emit-tag")
    if args.emit_template:
        if not args.emit_config_dir:
            raise ValueError("--emit-template 仅支持与 --emit-config-dir 一起使用")
        if args.emit_prefix or args.emit_tag:
            raise ValueError("--emit-template 不能与 --emit-prefix/--emit-tag 同时使用")
        if args.emit_separator is not None:
            raise ValueError("--emit-template 不能与 --emit-separator 同时使用")
        validate_emit_template(args.emit_template, "--emit-template")
    if args.emit_separator is not None:
        if not args.emit_config_dir:
            raise ValueError("--emit-separator 仅支持与 --emit-config-dir 一起使用")
        normalize_emit_separator(args.emit_separator, "--emit-separator")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键运行 score_vs_macd 批处理模板")
    parser.add_argument(
        "--symbol",
        choices=["qqq", "eth"],
        default="qqq",
        help="模板标的：qqq 或 eth（默认 qqq）",
    )
    parser.add_argument(
        "--naming-demo",
        action="store_true",
        help="切换到命名演示模板（默认只渲染不执行）",
    )
    parser.add_argument("--run", action="store_true", help="与 --naming-demo 搭配时显式执行批处理")
    parser.add_argument("--start", help="覆盖模板 vars.start（格式：YYYY-MM-DD）")
    parser.add_argument("--end", help="覆盖模板 vars.end（格式：YYYY-MM-DD）")
    parser.add_argument("--report-file", help="覆盖模板中 report 任务的 output_file")
    parser.add_argument("--report-prefix", help="给 report 输出文件名追加统一前缀（不含目录）")
    parser.add_argument("--report-dir", help="覆盖 report 输出目录（仅替换目录，保留文件名）")
    parser.add_argument(
        "--report-tag",
        nargs="?",
        const="auto",
        help="给 report 输出文件追加后缀；不传值时自动使用 UTC 时间戳",
    )
    parser.add_argument("--emit-config", help="将渲染后的配置写入指定路径（相对路径基于项目根目录）")
    parser.add_argument(
        "--emit-config-dir",
        help="将渲染配置写入指定目录，文件名自动生成为 score_vs_macd_<symbol>_{ts}.json",
    )
    parser.add_argument("--emit-prefix", help="给 --emit-config-dir 生成的配置文件名追加统一前缀")
    parser.add_argument("--emit-tag", help="给 --emit-config-dir 生成的配置文件名追加后缀标记")
    parser.add_argument(
        "--emit-template",
        help="指定 --emit-config-dir 的文件名模板（需包含 {symbol} 与 {ts}）",
    )
    parser.add_argument(
        "--emit-separator",
        default=None,
        help="指定 --emit-config-dir 自动命名时的片段分隔符（默认 _）",
    )
    parser.add_argument(
        "--keep-emitted-configs",
        type=int,
        default=0,
        help="仅在 --emit-config 包含 {ts} 时生效，保留最近 N 份历史渲染配置（0 表示不清理）",
    )
    parser.add_argument("--no-run", action="store_true", help="仅生成临时配置并打印命令，不执行")
    parser.add_argument("--keep-temp-config", action="store_true", help="执行后保留临时配置文件")
    parser.add_argument("--print-config", action="store_true", help="打印渲染后的配置 JSON")
    parser.add_argument("--python-bin", default=sys.executable, help="Python 可执行文件（默认当前解释器）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将执行的命令，不实际运行")
    return parser


def _parse_iso_date(raw: str, arg_name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{arg_name} 日期格式错误，需为 YYYY-MM-DD: {raw}") from exc


def _load_template_payload(template: Path) -> dict[str, object]:
    payload = json.loads(template.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("模板配置必须是 JSON 对象")
    vars_block = payload.setdefault("vars", {})
    if not isinstance(vars_block, dict):
        raise ValueError("模板 vars 必须是 JSON 对象")
    return payload


def _append_report_tag(output_file: str, tag: str) -> str:
    path = Path(output_file)
    if path.suffix:
        return str(path.with_name(f"{path.stem}_{tag}{path.suffix}"))
    return str(path.with_name(f"{path.name}_{tag}"))


def _apply_report_prefix(output_file: str, prefix: str) -> str:
    prefix_value = prefix.strip()
    if not prefix_value:
        raise ValueError("--report-prefix 不能为空")
    path = Path(output_file)
    return str(path.with_name(f"{prefix_value}_{path.name}"))


def _resolve_report_tag(raw_tag: str | None) -> str | None:
    if raw_tag is None:
        return None
    if raw_tag == "auto":
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = raw_tag.strip()
    if not tag:
        raise ValueError("--report-tag 不能为空")
    return tag


def _apply_report_dir(output_file: str, report_dir: str) -> str:
    report_dir_value = report_dir.strip()
    if not report_dir_value:
        raise ValueError("--report-dir 不能为空")
    return str(Path(report_dir_value) / Path(output_file).name)


def _render_payload(
    template: Path,
    start: str | None,
    end: str | None,
    report_file: str | None,
    report_prefix: str | None,
    report_tag: str | None,
    report_dir: str | None,
) -> dict[str, object]:
    payload = _load_template_payload(template)
    vars_block = payload["vars"]
    assert isinstance(vars_block, dict)

    if start is not None or end is not None:
        if bool(start) != bool(end):
            raise ValueError("--start 与 --end 必须成对提供")
        assert start is not None
        assert end is not None
        start_date = _parse_iso_date(start, "--start")
        end_date = _parse_iso_date(end, "--end")
        if start_date >= end_date:
            raise ValueError("--start 必须早于 --end")
        vars_block["start"] = start
        vars_block["end"] = end
    if report_file or report_prefix or report_tag or report_dir:
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            raise ValueError("模板 tasks 必须是列表")
        resolved_tag = _resolve_report_tag(report_tag)
        for task in tasks:
            if isinstance(task, dict) and str(task.get("command", "")).strip().lower() == "report":
                current_output = str(task.get("output_file", "report_index.md"))
                next_output = report_file or current_output
                if report_prefix:
                    next_output = _apply_report_prefix(next_output, report_prefix)
                if resolved_tag:
                    next_output = _append_report_tag(next_output, resolved_tag)
                if report_dir:
                    next_output = _apply_report_dir(next_output, report_dir)
                task["output_file"] = next_output
                break
        else:
            raise ValueError("模板缺少 report 任务，无法覆盖 --report-file/--report-prefix/--report-tag/--report-dir")
    return payload


def _materialize_config_file(payload: dict[str, object], emit_config: str | None) -> Path:
    if emit_config:
        target = Path(emit_config)
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target

    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="score_vs_macd_rendered_",
        dir=str(output_dir),
        encoding="utf-8",
        delete=False,
    )
    with tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    return Path(tmp.name)


def _resolve_emit_target(raw_emit_config: str) -> tuple[Path, str | None]:
    target = raw_emit_config
    if "{ts}" in raw_emit_config:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = raw_emit_config.replace("{ts}", ts)
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = PROJECT_ROOT / target_path
    cleanup_pattern: str | None = None
    if "{ts}" in raw_emit_config:
        resolved = Path(raw_emit_config)
        cleanup_pattern = resolved.name.replace("{ts}", "*")
    return target_path, cleanup_pattern


def _build_emit_config_path(args: argparse.Namespace) -> str | None:
    if args.emit_config:
        return args.emit_config
    if args.emit_config_dir:
        emit_dir = args.emit_config_dir.strip()
        if not emit_dir:
            raise ValueError("--emit-config-dir 不能为空")
        template = validate_emit_template(args.emit_template, "--emit-template") if args.emit_template else None
        separator = normalize_emit_separator(args.emit_separator, "--emit-separator") if args.emit_separator else "_"
        prefix = normalize_emit_segment(args.emit_prefix, "--emit-prefix") if args.emit_prefix else None
        tag = normalize_emit_segment(args.emit_tag, "--emit-tag") if args.emit_tag else None
        name = build_emit_filename(
            symbol=args.symbol,
            timestamp_token="{ts}",
            separator=separator,
            prefix=prefix,
            tag=tag,
            template=template,
        )
        return str(Path(emit_dir) / name)
    return None


def _cleanup_emitted_configs(emit_target: Path, cleanup_pattern: str | None, keep_count: int) -> tuple[int, int]:
    if keep_count <= 0 or cleanup_pattern is None:
        return 0, 0
    candidates = sorted(
        emit_target.parent.glob(cleanup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if len(candidates) <= keep_count:
        return len(candidates), 0

    trash_dir = PROJECT_ROOT / ".trash" / "score_vs_macd_emitted"
    trash_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for old in candidates[keep_count:]:
        shutil.move(str(old), str(trash_dir / old.name))
        removed += 1
    return len(candidates), removed


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.naming_demo and not args.run and not args.no_run and not args.dry_run:
        args.no_run = True
    _validate_args(args)

    template_map = NAMING_DEMO_TEMPLATE_MAP if args.naming_demo else COMPARE_TEMPLATE_MAP
    template = template_map[args.symbol]
    temp_config: Path | None = None
    should_cleanup = False
    emit_target: Path | None = None
    cleanup_pattern: str | None = None

    try:
        need_render = bool(
            args.no_run
            or args.print_config
            or args.start
            or args.end
            or args.report_file
            or args.report_prefix
            or args.report_tag
            or args.report_dir
            or args.emit_config
            or args.emit_config_dir
            or args.emit_prefix
            or args.emit_tag
            or args.emit_template
        )
        payload: dict[str, object] | None = None
        if need_render:
            emit_config_path: str | None = None
            emit_config_raw = _build_emit_config_path(args)
            if emit_config_raw:
                emit_target, cleanup_pattern = _resolve_emit_target(emit_config_raw)
                emit_config_path = str(emit_target)
            payload = _render_payload(
                template,
                args.start,
                args.end,
                args.report_file,
                args.report_prefix,
                args.report_tag,
                args.report_dir,
            )
            temp_config = _materialize_config_file(payload, emit_config_path)
        config_file = temp_config or template

        cmd = [
            args.python_bin,
            "-m",
            "market_signal_system",
            "run-config",
            "--file",
            str(config_file),
        ]
        print("Command:", " ".join(cmd))
        if temp_config is not None:
            label = "Rendered config" if (args.emit_config or args.emit_config_dir) else "Temp config"
            print(f"{label}: {temp_config}")
        if args.print_config and payload is not None:
            print("Rendered config:")
            print(json.dumps(payload, ensure_ascii=False, indent=2), end="\n")

        if args.no_run or args.dry_run:
            return 0

        should_cleanup = temp_config is not None and not args.keep_temp_config and not args.emit_config
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr, file=sys.stderr, end="")
            raise RuntimeError("score_vs_macd 批处理执行失败")
        return 0
    finally:
        if should_cleanup and temp_config is not None and temp_config.exists():
            temp_config.unlink()
        if emit_target is not None:
            total, removed = _cleanup_emitted_configs(emit_target, cleanup_pattern, args.keep_emitted_configs)
            if total > 0:
                print(
                    f"Emitted config cleanup: pattern={cleanup_pattern} total={total} removed={removed} "
                    f"keep={args.keep_emitted_configs}"
                )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI 顶层防护
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
