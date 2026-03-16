import json
import os
import subprocess
import sys
from pathlib import Path


def test_mvp_report_script_help():
    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "scripts/mvp_report.py", "--help"],
        cwd=str(project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "mvp_summary" in proc.stdout


def test_mvp_report_script_builds_outputs_from_summary(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    summary_path = tmp_path / "mvp_summary_unit.json"
    output_dir = tmp_path / "out"
    output_prefix = "unit_report"

    payload = {
        "run_tag": "unit",
        "symbols": ["QQQ", "ETH"],
        "strategies": ["ma_cross", "donchian", "momentum"],
        "backtests": [
            {
                "symbol": "QQQ",
                "strategy": "ma_cross",
                "bars": 100,
                "total_return": 0.12,
                "max_drawdown": -0.08,
                "sharpe": 1.1,
                "metrics_file": "m1.json",
            },
            {
                "symbol": "QQQ",
                "strategy": "momentum",
                "bars": 100,
                "total_return": 0.2,
                "max_drawdown": -0.1,
                "sharpe": 1.3,
                "metrics_file": "m2.json",
            },
            {
                "symbol": "ETH",
                "strategy": "donchian",
                "bars": 100,
                "total_return": 0.18,
                "max_drawdown": -0.2,
                "sharpe": 1.0,
                "metrics_file": "m3.json",
            },
        ],
        "simulations": [],
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/mvp_report.py",
            "--summary-file",
            str(summary_path),
            "--output-dir",
            str(output_dir),
            "--output-prefix",
            output_prefix,
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    csv_path = output_dir / f"{output_prefix}.csv"
    md_path = output_dir / f"{output_prefix}.md"
    assert csv_path.exists()
    assert md_path.exists()

    csv_text = csv_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    assert "symbol_rank" in csv_text
    assert "QQQ" in csv_text
    assert "ETH" in csv_text
    assert "分组冠军" in md_text
    assert "momentum" in md_text
