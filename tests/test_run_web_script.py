from __future__ import annotations

import os
import subprocess
import sys


def test_run_web_script_help() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "scripts/run_web.py", "--help"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert "--db-path" in result.stdout
