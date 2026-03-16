import json
import os
import subprocess
import sys
from pathlib import Path


def test_run_baseline_daily_script_help():
    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "scripts/run_baseline_daily.py", "--help"],
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "baseline" in proc.stdout.lower()


def test_run_baseline_daily_script_renders_config_with_overrides(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    output_config = tmp_path / "rendered.json"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_baseline_daily.py",
            "--config",
            "examples/config.batch.baseline.daily.json",
            "--start",
            "2021-01-01",
            "--end",
            "2026-03-16",
            "--as-of",
            "2026-03-16",
            "--output-config",
            str(output_config),
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert output_config.exists()

    payload = json.loads(output_config.read_text(encoding="utf-8"))
    assert payload["vars"]["start"] == "2021-01-01"
    assert payload["vars"]["end"] == "2026-03-16"
    assert payload["vars"]["as_of"] == "2026-03-16"
