import os
import subprocess
import sys
from pathlib import Path


def test_smoke_simulate_resume_script_help():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "smoke_simulate_resume.py"
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
    assert "simulate 恢复链路离线冒烟脚本" in proc.stdout
    assert "--split-end" in proc.stdout
    assert "--keep-artifacts" in proc.stdout


def test_smoke_simulate_resume_script_runs_successfully():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "smoke_simulate_resume.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "simulate 恢复冒烟通过" in proc.stdout
    assert "second_trade_count" in proc.stdout


def test_smoke_simulate_resume_script_accepts_custom_split_and_params():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "smoke_simulate_resume.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--start",
            "2020-01-01",
            "--split-end",
            "2020-01-03",
            "--end",
            "2020-01-06",
            "--params",
            '{"fast_window":2,"slow_window":3}',
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "simulate 恢复冒烟通过" in proc.stdout


def test_smoke_simulate_resume_script_rejects_invalid_date_order():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "smoke_simulate_resume.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--start",
            "2020-01-03",
            "--split-end",
            "2020-01-03",
            "--end",
            "2020-01-06",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "start < split-end < end" in proc.stderr
