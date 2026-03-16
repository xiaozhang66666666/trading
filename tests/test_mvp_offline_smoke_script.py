from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mvp_offline_smoke_script_help() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/mvp_offline_smoke.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--bars" in proc.stdout
    assert "--state-prefix" in proc.stdout


def test_mvp_offline_smoke_script_generates_summary(tmp_path: Path) -> None:
    output_file = tmp_path / "offline_smoke.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/mvp_offline_smoke.py",
            "--bars",
            "200",
            "--state-prefix",
            "ut_smoke",
            "--output-file",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert output_file.exists()

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["symbols"] == ["QQQ", "ETH"]
    assert payload["strategies"] == ["ma_cross", "momentum", "donchian"]
    assert len(payload["backtests"]) == 6
    assert len(payload["simulations"]) == 2
    assert "mvp_acceptance" in payload
    assert isinstance(payload["mvp_acceptance"].get("checks"), list)
