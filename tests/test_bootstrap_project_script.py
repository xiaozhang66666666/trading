from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_bootstrap_module():
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "scripts" / "bootstrap_project.py"
    spec = importlib.util.spec_from_file_location("bootstrap_project_script", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_project_script_help() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/bootstrap_project.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--mode" in proc.stdout
    assert "--dev" in proc.stdout
    assert "--check-sync" in proc.stdout


def test_check_dependency_sync_passes_for_aligned_files(tmp_path: Path) -> None:
    module = _load_bootstrap_module()
    (tmp_path / "requirements.txt").write_text("pandas>=2.2.0\nrequests>=2.32.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\npytest>=8.0.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'dependencies = ["pandas>=2.2.0", "requests>=2.32.0"]',
                '[project.optional-dependencies]',
                'dev = ["pytest>=8.0.0"]',
            ]
        ),
        encoding="utf-8",
    )
    ok, issues = module._check_dependency_sync(tmp_path)
    assert ok is True
    assert issues == []


def test_check_dependency_sync_reports_mismatch(tmp_path: Path) -> None:
    module = _load_bootstrap_module()
    (tmp_path / "requirements.txt").write_text("pandas>=2.2.0\nrequests>=2.32.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\npytest>=8.0.0\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'dependencies = ["pandas>=2.2.0"]',
                '[project.optional-dependencies]',
                'dev = ["httpx>=0.28.0"]',
            ]
        ),
        encoding="utf-8",
    )
    ok, issues = module._check_dependency_sync(tmp_path)
    assert ok is False
    joined = "\n".join(issues)
    assert "核心依赖不一致" in joined
    assert "开发依赖不一致" in joined
