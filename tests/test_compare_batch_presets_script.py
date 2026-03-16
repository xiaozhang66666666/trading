import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_compare_batch_presets_script_help():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "--no-run" in proc.stdout
    assert "--start" in proc.stdout
    assert "--end" in proc.stdout
    assert "--keep-snapshots" in proc.stdout
    assert "--snapshot-keep-start" in proc.stdout
    assert "--snapshot-keep-end" in proc.stdout
    assert "--cleanup-only" in proc.stdout
    assert "--keep-cleanup-history" in proc.stdout


def test_compare_batch_presets_script_requires_start_end_pair():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [sys.executable, str(script), "--start", "2020-01-01"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "--start 与 --end 需要同时提供" in proc.stderr


def test_compare_batch_presets_script_accepts_start_end_pair(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--no-run",
            "--start",
            "2020-01-01",
            "--end",
            "2025-12-31",
            "--output-dir",
            str(tmp_path / "outputs"),
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "Preset compare CSV:" in proc.stdout


def test_compare_batch_presets_script_writes_expected_artifacts(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")
    output_dir = tmp_path / "outputs"

    proc = subprocess.run(
        [sys.executable, str(script), "--no-run", "--output-dir", str(output_dir)],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    csv_path = output_dir / "preset_compare" / "preset_compare.csv"
    md_path = output_dir / "preset_compare" / "preset_compare.md"
    assert csv_path.exists()
    assert md_path.exists()
    df = pd.read_csv(csv_path)
    assert {"preset", "total_return", "sharpe", "failed_count", "run_duration_ms"}.issubset(df.columns)
    assert "保守/激进模板对比" in md_path.read_text(encoding="utf-8")


def test_compare_batch_presets_script_rejects_negative_keep_snapshots():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [sys.executable, str(script), "--keep-snapshots", "-1"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "--keep-snapshots 不能小于 0" in proc.stderr


def test_compare_batch_presets_script_help_without_pythonpath():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "一键运行并对比保守/激进批处理预设" in proc.stdout


def test_compare_batch_presets_script_accepts_snapshot_cleanup_range(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--no-run",
            "--snapshot-keep-start",
            "2026-03-01",
            "--snapshot-keep-end",
            "2026-03-31",
            "--output-dir",
            str(tmp_path / "outputs"),
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "Preset compare CSV:" in proc.stdout


def test_compare_batch_presets_script_cleanup_only(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")
    output_dir = tmp_path / "outputs"

    proc = subprocess.run(
        [sys.executable, str(script), "--cleanup-only", "--output-dir", str(output_dir)],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    cleanup_path = output_dir / "preset_compare" / "preset_compare_cleanup_latest.json"
    assert cleanup_path.exists()
    assert "Preset compare cleanup:" in proc.stdout
    assert "Preset compare CSV:" not in proc.stdout


def test_compare_batch_presets_script_rejects_invalid_snapshot_date():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [sys.executable, str(script), "--snapshot-keep-start", "bad-date", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "cleanup_keep_start 日期格式非法" in proc.stderr


def test_compare_batch_presets_script_rejects_negative_keep_cleanup_history():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "compare_batch_presets.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [sys.executable, str(script), "--keep-cleanup-history", "-1"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "--keep-cleanup-history 不能小于 0" in proc.stderr
