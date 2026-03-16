import json
import os
import subprocess
import sys
import gzip
from pathlib import Path


def test_demo_strict_failure_report_script_help():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "demo_strict_failure_report.py"
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
    assert "strict 模式失败任务 + 报告汇总演示" in proc.stdout
    assert "--config" in proc.stdout
    assert "--report-file" in proc.stdout


def test_demo_strict_failure_report_script_runs_with_expected_failure(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "demo_strict_failure_report.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(project_root / "src")

    cfg = {
        "command": "batch",
        "on_error": "continue",
        "compress_naming": "strict",
        "summary_compress": "gzip",
        "summary_json": "strict_failure_summary.json.gz",
        "summary_csv": "strict_failure_summary.csv.gz",
        "tasks": [
            {"command": "report", "output_file": "strict_failure_demo_pre.md"},
            {"command": "unknown-task"},
            {"command": "report", "output_file": "strict_failure_demo_post.md"},
        ],
    }
    cfg_path = tmp_path / "strict_failure_demo.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            str(cfg_path),
            "--report-file",
            "strict_failure_demo_report_test.md",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "run-config returncode:" in proc.stdout
    assert "summary json:" in proc.stdout
    assert "report:" in proc.stdout

    outputs_dir = project_root / "outputs"
    summary_json = outputs_dir / "strict_failure_summary.json.gz"
    summary_csv = outputs_dir / "strict_failure_summary.csv.gz"
    report_path = outputs_dir / "strict_failure_demo_report_test.md"

    assert summary_json.exists()
    assert summary_csv.exists()
    assert report_path.exists()

    with gzip.open(summary_json, "rt", encoding="utf-8") as fp:
        payload = json.load(fp)
    assert int(payload.get("failed_count", 0)) >= 1
    assert int(payload.get("success_count", 0)) >= 1

    report_text = report_path.read_text(encoding="utf-8")
    assert "批处理执行摘要" in report_text
