import os
import re
import subprocess
import sys
import time
from pathlib import Path


def test_run_score_vs_macd_script_help():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
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
    assert "--symbol" in proc.stdout
    assert "--naming-demo" in proc.stdout
    assert "--run" in proc.stdout
    assert "--dry-run" in proc.stdout
    assert "--start" in proc.stdout
    assert "--end" in proc.stdout
    assert "--report-file" in proc.stdout
    assert "--report-prefix" in proc.stdout
    assert "--report-tag" in proc.stdout
    assert "--report-dir" in proc.stdout
    assert "--emit-config" in proc.stdout
    assert "--emit-config-dir" in proc.stdout
    assert "--emit-prefix" in proc.stdout
    assert "--emit-tag" in proc.stdout
    assert "--emit-template" in proc.stdout
    assert "--emit-separator" in proc.stdout
    assert "--keep-emitted-configs" in proc.stdout
    assert "--no-run" in proc.stdout
    assert "--keep-temp-config" in proc.stdout
    assert "--print-config" in proc.stdout
    assert "score_vs_macd" in proc.stdout


def test_run_score_vs_macd_script_supports_qqq_and_eth_dry_run():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    qqq = subprocess.run(
        [sys.executable, str(script), "--symbol", "qqq", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert qqq.returncode == 0
    assert "config.batch.score_vs_macd_compare.json" in qqq.stdout

    eth = subprocess.run(
        [sys.executable, str(script), "--symbol", "eth", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert eth.returncode == 0
    assert "config.batch.score_vs_macd_compare.eth.json" in eth.stdout


def test_run_score_vs_macd_script_naming_demo_defaults_to_no_run_for_qqq():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "qqq", "--naming-demo"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Temp config:" in proc.stdout

    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"batch_prefix": "nightly"' in payload
    assert '"output_tag": "${batch_prefix}_${symbol}_score_regime_${batch_tag}"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_naming_demo_supports_eth_dry_run():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "eth", "--naming-demo", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "config.batch.score_vs_macd_naming_demo.eth.json" in proc.stdout


def test_run_score_vs_macd_script_rejects_run_with_dry_run():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "qqq", "--naming-demo", "--run", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--run 不能与 --no-run/--dry-run 同时使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_run_with_no_run():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "qqq", "--naming-demo", "--run", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--run 不能与 --no-run/--dry-run 同时使用" in proc.stderr


def test_run_score_vs_macd_script_no_run_supports_start_end_override():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--start",
            "2020-01-01",
            "--end",
            "2021-01-01",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "Temp config:" in proc.stdout
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"start": "2020-01-01"' in payload
    assert '"end": "2021-01-01"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_rejects_invalid_start_end_pair():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--start", "2020-01-01", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--start 与 --end 必须成对提供" in proc.stderr


def test_run_score_vs_macd_script_no_run_supports_report_file_override():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--report-file",
            "eth_custom_report.md",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "eth_custom_report.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_no_run_supports_report_prefix_override():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--report-prefix",
            "nightly",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "nightly_score_vs_macd_report.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_no_run_supports_report_prefix_with_tag():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--report-prefix",
            "daily",
            "--report-tag",
            "r2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "daily_score_vs_macd_eth_report_r2.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_rejects_blank_report_prefix():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--report-prefix",
            "   ",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--report-prefix 不能为空" in proc.stderr


def test_run_score_vs_macd_script_no_run_supports_report_tag_override():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--report-file",
            "weekly.md",
            "--report-tag",
            "r1",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "weekly_r1.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_no_run_supports_report_dir_override():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--report-dir",
            "outputs/custom_reports",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "outputs/custom_reports/score_vs_macd_eth_report.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_no_run_supports_report_dir_with_report_tag():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--report-dir",
            "outputs/custom_reports",
            "--report-tag",
            "daily",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert '"output_file": "outputs/custom_reports/score_vs_macd_report_daily.md"' in payload
    temp_path.unlink()


def test_run_score_vs_macd_script_report_tag_auto_uses_timestamp_suffix():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "eth", "--report-tag", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip())
    assert temp_path.exists()
    payload = temp_path.read_text(encoding="utf-8")
    assert re.search(r'"output_file": "score_vs_macd_eth_report_\d{8}T\d{6}Z\.md"', payload)
    temp_path.unlink()


def test_run_score_vs_macd_script_emit_config_writes_to_target_file(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target = tmp_path / "score_vs_macd_emit.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--start",
            "2020-01-01",
            "--end",
            "2021-01-01",
            "--emit-config",
            str(target),
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert f"Rendered config: {target}" in proc.stdout
    assert target.exists()
    payload = target.read_text(encoding="utf-8")
    assert '"start": "2020-01-01"' in payload
    assert '"end": "2021-01-01"' in payload


def test_run_score_vs_macd_script_emit_config_dir_writes_timestamped_file(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--emit-config-dir",
            str(target_dir),
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"score_vs_macd_eth_\d{8}T\d{6}Z\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_prefix(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config-dir",
            str(target_dir),
            "--emit-prefix",
            "nightly",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"nightly_score_vs_macd_qqq_\d{8}T\d{6}Z\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_tag(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--emit-config-dir",
            str(target_dir),
            "--emit-tag",
            "weekly",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"score_vs_macd_eth_\d{8}T\d{6}Z_weekly\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_separator(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--emit-config-dir",
            str(target_dir),
            "--emit-separator",
            "-",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"score-vs-macd-eth-\d{8}T\d{6}Z\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_separator_with_prefix_and_tag(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config-dir",
            str(target_dir),
            "--emit-prefix",
            "nightly",
            "--emit-tag",
            "r2",
            "--emit-separator",
            "-",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"nightly-score-vs-macd-qqq-\d{8}T\d{6}Z-r2\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_template(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config-dir",
            str(target_dir),
            "--emit-template",
            "nightly_{symbol}_{ts}_r2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"nightly_qqq_\d{8}T\d{6}Z_r2\.json", rendered.name)


def test_run_score_vs_macd_script_emit_config_dir_supports_emit_prefix_and_emit_tag(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    target_dir = tmp_path / "emitted_dir"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config-dir",
            str(target_dir),
            "--emit-prefix",
            "nightly",
            "--emit-tag",
            "r2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    match = re.search(r"Rendered config: (.+)", proc.stdout)
    assert match is not None
    rendered = Path(match.group(1).strip())
    assert rendered.exists()
    assert rendered.parent == target_dir
    assert re.match(r"nightly_score_vs_macd_qqq_\d{8}T\d{6}Z_r2\.json", rendered.name)


def test_run_score_vs_macd_script_rejects_emit_prefix_without_emit_config_dir():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--emit-prefix", "nightly", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-prefix 仅支持与 --emit-config-dir 一起使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_tag_without_emit_config_dir():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--emit-tag", "weekly", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-tag 仅支持与 --emit-config-dir 一起使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_template_without_emit_config_dir():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--emit-template", "demo_{symbol}_{ts}.json", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-template 仅支持与 --emit-config-dir 一起使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_template_with_emit_prefix(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-template",
            "demo_{symbol}_{ts}.json",
            "--emit-prefix",
            "nightly",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-template 不能与 --emit-prefix/--emit-tag 同时使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_template_missing_placeholders(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-template",
            "demo_fixed_name.json",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-template 必须包含 {symbol} 占位符" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_separator_without_emit_config_dir():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--emit-separator", "-", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-separator 仅支持与 --emit-config-dir 一起使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_blank_emit_prefix(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-prefix",
            "   ",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-prefix 不能为空" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_prefix_with_path_separator(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-prefix",
            "nightly/team",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-prefix 不能包含路径分隔符" in proc.stderr


def test_run_score_vs_macd_script_rejects_blank_emit_tag(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-tag",
            "   ",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-tag 不能为空" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_tag_with_path_separator(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-tag",
            "week\\r2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-tag 不能包含路径分隔符" in proc.stderr


def test_run_score_vs_macd_script_rejects_blank_emit_separator(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-separator",
            "   ",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-separator 不能为空" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_separator_with_path_separator(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--emit-separator",
            "/",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-separator 不能包含路径分隔符" in proc.stderr


def test_run_score_vs_macd_script_rejects_emit_config_with_emit_config_dir(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config",
            str(tmp_path / "fixed.json"),
            "--emit-config-dir",
            str(tmp_path / "dir"),
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--emit-config 与 --emit-config-dir 不能同时使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_keep_emitted_configs_without_ts_placeholder(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config",
            str(tmp_path / "fixed.json"),
            "--keep-emitted-configs",
            "2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--keep-emitted-configs 仅支持与包含 {ts} 的 --emit-config 一起使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_keep_temp_config_with_emit_config_dir(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config-dir",
            str(tmp_path / "rendered"),
            "--keep-temp-config",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--keep-temp-config 与 --emit-config/--emit-config-dir 不能同时使用" in proc.stderr


def test_run_score_vs_macd_script_keep_emitted_configs_cleans_old_files(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    config_dir = tmp_path / "rendered"
    config_dir.mkdir(parents=True, exist_ok=True)
    old1 = config_dir / "score_vs_macd_20240101T000000Z.json"
    old2 = config_dir / "score_vs_macd_20240102T000000Z.json"
    old3 = config_dir / "score_vs_macd_20240103T000000Z.json"
    for file in (old1, old2, old3):
        file.write_text("{}", encoding="utf-8")
        time.sleep(0.01)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config",
            str(config_dir / "score_vs_macd_{ts}.json"),
            "--keep-emitted-configs",
            "2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    remain = sorted(config_dir.glob("score_vs_macd_*.json"))
    assert len(remain) == 2
    assert "Emitted config cleanup:" in proc.stdout


def test_run_score_vs_macd_script_keep_emitted_configs_cleans_old_files_with_emit_dir(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    config_dir = tmp_path / "rendered_dir"
    config_dir.mkdir(parents=True, exist_ok=True)
    old1 = config_dir / "score_vs_macd_qqq_20240101T000000Z.json"
    old2 = config_dir / "score_vs_macd_qqq_20240102T000000Z.json"
    old3 = config_dir / "score_vs_macd_qqq_20240103T000000Z.json"
    for file in (old1, old2, old3):
        file.write_text("{}", encoding="utf-8")
        time.sleep(0.01)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "qqq",
            "--emit-config-dir",
            str(config_dir),
            "--keep-emitted-configs",
            "2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    remain = sorted(config_dir.glob("score_vs_macd_qqq_*.json"))
    assert len(remain) == 2
    assert "Emitted config cleanup:" in proc.stdout


def test_run_score_vs_macd_script_keep_emitted_configs_cleans_old_files_with_prefix_and_tag(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    config_dir = tmp_path / "rendered_dir"
    config_dir.mkdir(parents=True, exist_ok=True)
    old1 = config_dir / "nightly_score_vs_macd_eth_20240101T000000Z_weekly.json"
    old2 = config_dir / "nightly_score_vs_macd_eth_20240102T000000Z_weekly.json"
    old3 = config_dir / "nightly_score_vs_macd_eth_20240103T000000Z_weekly.json"
    for file in (old1, old2, old3):
        file.write_text("{}", encoding="utf-8")
        time.sleep(0.01)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--symbol",
            "eth",
            "--emit-config-dir",
            str(config_dir),
            "--emit-prefix",
            "nightly",
            "--emit-tag",
            "weekly",
            "--keep-emitted-configs",
            "2",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    remain = sorted(config_dir.glob("nightly_score_vs_macd_eth_*_weekly.json"))
    assert len(remain) == 2
    assert "Emitted config cleanup:" in proc.stdout


def test_run_score_vs_macd_script_no_run_can_print_rendered_config():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--symbol", "qqq", "--no-run", "--print-config"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "Rendered config:" in proc.stdout
    assert '"command": "batch"' in proc.stdout


def test_run_score_vs_macd_script_returns_1_when_subprocess_fails(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    failing_python = tmp_path / "python_fail.sh"
    failing_python.write_text("#!/usr/bin/env bash\nexit 3\n", encoding="utf-8")
    failing_python.chmod(0o755)

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(script), "--python-bin", str(failing_python)],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "score_vs_macd 批处理执行失败" in proc.stderr


def test_run_score_vs_macd_keep_temp_config_preserves_file_on_execute_path(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    failing_python = tmp_path / "python_fail_keep.sh"
    failing_python.write_text("#!/usr/bin/env bash\nexit 4\n", encoding="utf-8")
    failing_python.chmod(0o755)

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--python-bin",
            str(failing_python),
            "--start",
            "2020-01-01",
            "--end",
            "2021-01-01",
            "--keep-temp-config",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    temp_path = Path(proc.stdout.strip().split("Temp config:", 1)[1].strip().splitlines()[0].strip())
    assert temp_path.exists()
    temp_path.unlink()


def test_run_score_vs_macd_script_rejects_no_run_with_dry_run():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--no-run", "--dry-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--no-run 与 --dry-run 不能同时使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_keep_temp_config_with_emit_config(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--emit-config",
            str(tmp_path / "rendered.json"),
            "--keep-temp-config",
            "--no-run",
        ],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--keep-temp-config 与 --emit-config/--emit-config-dir 不能同时使用" in proc.stderr


def test_run_score_vs_macd_script_rejects_keep_temp_config_in_no_run_mode():
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_score_vs_macd.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, str(script), "--keep-temp-config", "--no-run"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "--keep-temp-config 仅在真实执行路径有效" in proc.stderr
