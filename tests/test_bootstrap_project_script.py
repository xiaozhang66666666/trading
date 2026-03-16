from __future__ import annotations

import subprocess
import sys


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
