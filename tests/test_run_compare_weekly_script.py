import json
import os
import subprocess
import sys
from pathlib import Path


def test_run_compare_weekly_script_help():
    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "scripts/run_compare_weekly.py", "--help"],
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "weekly" in proc.stdout.lower()


def test_run_compare_weekly_script_renders_config_with_overrides(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    output_config = tmp_path / "rendered_weekly_compare.json"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_compare_weekly.py",
            "--config",
            "examples/config.compare.weekly.json",
            "--start",
            "2021-01-01",
            "--end",
            "2026-03-16",
            "--symbols",
            "QQQ,ETH",
            "--strategies",
            "score_regime,macd_regime",
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
    assert payload["start"] == "2021-01-01"
    assert payload["end"] == "2026-03-16"
    assert payload["interval"] == "1wk"
    assert payload["symbols"] == ["QQQ", "ETH"]
    assert payload["strategies"] == ["score_regime", "macd_regime"]
