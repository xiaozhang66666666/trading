from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_compact_module():
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "scripts" / "compact_project_docs.py"
    spec = importlib.util.spec_from_file_location("compact_project_docs_script", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compact_markdown_keeps_latest_sections_and_footer():
    module = _load_compact_module()
    sample = "\n".join(
        [
            "# STATUS",
            "",
            "## S1",
            "- a",
            "",
            "## S2",
            "- b",
            "",
            "## S3",
            "- c",
        ]
    )
    compacted = module.compact_markdown(sample, keep_sections=2, archive_hint="docs/history/STATUS.x.md")
    assert "## S1" in compacted
    assert "## S2" in compacted
    assert "## S3" not in compacted
    assert "## 历史归档" in compacted
    assert "docs/history/STATUS.x.md" in compacted


def test_compact_one_apply_writes_archive_and_target(tmp_path: Path):
    module = _load_compact_module()
    target = tmp_path / "STATUS.md"
    target.write_text("# STATUS\n\n## A\n1\n\n## B\n2\n", encoding="utf-8")
    archive_dir = tmp_path / "history"
    before, after, archive = module._compact_one(  # type: ignore[attr-defined]
        path=target,
        keep_sections=1,
        archive_dir=archive_dir,
        apply=True,
    )
    assert before > 0
    assert after > 0
    assert archive.exists()
    text = target.read_text(encoding="utf-8")
    assert "## A" in text
    assert "## B" not in text
    assert "## 历史归档" in text
