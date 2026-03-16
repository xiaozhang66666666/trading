#!/usr/bin/env python3
"""压缩 STATUS/DECISIONS 长文档并归档历史版本。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def _split_sections(text: str) -> tuple[str, str, list[str]]:
    lines = text.splitlines()
    if not lines:
        return "", "", []
    title = lines[0]
    preamble: list[str] = []
    sections: list[list[str]] = []
    current: list[str] | None = None
    for line in lines[1:]:
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = [line]
        else:
            if current is None:
                preamble.append(line)
            else:
                current.append(line)
    if current:
        sections.append(current)
    preamble_text = "\n".join(preamble).strip()
    return title, preamble_text, ["\n".join(block).rstrip() for block in sections]


def compact_markdown(text: str, keep_sections: int, archive_hint: str) -> str:
    title, preamble, sections = _split_sections(text)
    if not title:
        return text
    kept = sections[: max(0, keep_sections)]
    body = "\n\n".join(s for s in kept if s.strip())
    footer = (
        "## 历史归档\n"
        f"- 历史详情已归档到：`{archive_hint}`\n"
        f"- 本文件仅保留最近 {max(0, keep_sections)} 个二级章节。"
    )
    merged = body.strip()
    if preamble:
        merged = f"{preamble}\n\n{merged}" if merged else preamble
    if merged.strip():
        return f"{title}\n\n{merged}\n\n{footer}\n"
    return f"{title}\n\n{footer}\n"


def _compact_one(path: Path, keep_sections: int, archive_dir: Path, apply: bool) -> tuple[int, int, Path]:
    source = path.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_file = archive_dir / f"{path.stem}.{timestamp}.md"
    compacted = compact_markdown(source, keep_sections=keep_sections, archive_hint=str(archive_file))
    before = len(source.encode("utf-8"))
    after = len(compacted.encode("utf-8"))

    if apply:
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_file.write_text(source, encoding="utf-8")
        path.write_text(compacted, encoding="utf-8")
    return before, after, archive_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="压缩 STATUS.md/DECISIONS.md 并归档历史版本")
    parser.add_argument("--keep-sections", type=int, default=8, help="每个文档保留的二级章节数量")
    parser.add_argument("--archive-dir", default="docs/history", help="归档目录（默认 docs/history）")
    parser.add_argument("--apply", action="store_true", help="执行写入；默认仅预览")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    targets = [root / "STATUS.md", root / "DECISIONS.md"]
    missing = [str(p) for p in targets if not p.exists()]
    if missing:
        raise FileNotFoundError(f"缺少目标文件: {', '.join(missing)}")

    archive_dir = root / args.archive_dir
    print(f"mode={'apply' if args.apply else 'dry-run'} keep_sections={args.keep_sections}")
    for path in targets:
        before, after, archive_file = _compact_one(
            path=path,
            keep_sections=args.keep_sections,
            archive_dir=archive_dir,
            apply=bool(args.apply),
        )
        ratio = (after / before) if before > 0 else 1.0
        print(f"- {path.name}: {before} -> {after} bytes (ratio={ratio:.2f}), archive={archive_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
