import json
from pathlib import Path

import pandas as pd
import pytest

from market_signal_system.research.preset_compare import compare_presets


def test_compare_presets_builds_csv_and_markdown_from_existing_artifacts(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )

    metrics = {
        "total_return": 0.2,
        "sharpe": 1.1,
        "calmar": 0.8,
        "max_drawdown": -0.15,
    }
    (output_dir / "portfolio_metrics_momentum_QQQ_ETH.json").write_text(
        json.dumps(metrics, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "total_equity": 100000.0,
                "gross_exposure_ratio": 0.5,
                "used_margin": 30000.0,
                "available_margin": 60000.0,
                "reserve_cash": 5000.0,
            },
            {
                "total_equity": 110000.0,
                "gross_exposure_ratio": 0.6,
                "used_margin": 40000.0,
                "available_margin": 55000.0,
                "reserve_cash": 5500.0,
            },
        ]
    ).to_csv(output_dir / "sim_portfolio_capital_QQQ_ETH_momentum.csv", index=False)
    (output_dir / "batch_conservative_summary.json").write_text(
        json.dumps({"failed_count": 0, "run_duration_ms": 1234.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "batch_aggressive_summary.json").write_text(
        json.dumps({"failed_count": 1, "run_duration_ms": 2345.0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "report_index_conservative.md").write_text("# conservative\n", encoding="utf-8")
    (output_dir / "report_index_aggressive.md").write_text("# aggressive\n", encoding="utf-8")

    csv_path, md_path = compare_presets(project_root=project_root, output_dir=output_dir, run_batches=False)

    assert csv_path.exists()
    assert md_path.exists()
    snapshots = list((output_dir / "preset_compare").glob("preset_compare_*.csv"))
    assert snapshots
    table = pd.read_csv(csv_path)
    assert set(table["preset"].tolist()) == {"conservative", "aggressive"}
    agg_row = table[table["preset"] == "aggressive"].iloc[0]
    assert int(agg_row["failed_count"]) == 1
    assert float(agg_row["run_duration_ms"]) == 2345.0
    content = md_path.read_text(encoding="utf-8")
    assert "保守/激进模板对比" in content
    assert "激进 - 保守（差值）" in content


def test_compare_presets_raises_when_batch_process_failed(tmp_path, monkeypatch):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)

    cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    cfg["vars"]["tag"] = "aggressive"
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(cfg, ensure_ascii=False),
        encoding="utf-8",
    )

    class _DummyCompleted:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    monkeypatch.setattr(
        "market_signal_system.research.preset_compare.subprocess.run",
        lambda *args, **kwargs: _DummyCompleted(returncode=2),
    )

    with pytest.raises(RuntimeError) as exc:
        compare_presets(project_root=project_root, output_dir=output_dir, run_batches=True)
    assert "批处理预设执行失败" in str(exc.value)


def test_compare_presets_applies_vars_override_when_running_batch(tmp_path, monkeypatch):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative", "start": "2018-01-01"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive", "start": "2018-01-01"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "portfolio_metrics_momentum_QQQ_ETH.json").write_text("{}", encoding="utf-8")
    pd.DataFrame([{"total_equity": 100000.0, "gross_exposure_ratio": 0.0}]).to_csv(
        output_dir / "sim_portfolio_capital_QQQ_ETH_momentum.csv",
        index=False,
    )
    (output_dir / "batch_conservative_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "batch_aggressive_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "report_index_conservative.md").write_text("# conservative\n", encoding="utf-8")
    (output_dir / "report_index_aggressive.md").write_text("# aggressive\n", encoding="utf-8")

    captured: list[dict[str, str]] = []

    class _DummyCompleted:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def _fake_run(cmd, **kwargs):
        file_idx = cmd.index("--file") + 1
        cfg_path = Path(cmd[file_idx])
        payload = json.loads(cfg_path.read_text(encoding="utf-8"))
        captured.append(payload.get("vars", {}))
        return _DummyCompleted(returncode=0)

    monkeypatch.setattr("market_signal_system.research.preset_compare.subprocess.run", _fake_run)

    compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=True,
        vars_override={"start": "2020-01-01", "end": "2025-12-31"},
    )

    assert len(captured) == 2
    assert all(v["start"] == "2020-01-01" for v in captured)
    assert all(v["end"] == "2025-12-31" for v in captured)


def test_compare_presets_cleans_old_snapshots(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    snapshot_dir = output_dir / "preset_compare"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)
    snapshot_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "portfolio_metrics_momentum_QQQ_ETH.json").write_text("{}", encoding="utf-8")
    pd.DataFrame([{"total_equity": 100000.0, "gross_exposure_ratio": 0.0}]).to_csv(
        output_dir / "sim_portfolio_capital_QQQ_ETH_momentum.csv",
        index=False,
    )
    (output_dir / "batch_conservative_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "batch_aggressive_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "report_index_conservative.md").write_text("# conservative\n", encoding="utf-8")
    (output_dir / "report_index_aggressive.md").write_text("# aggressive\n", encoding="utf-8")

    for stamp in ("20260315T090000Z", "20260315T100000Z", "20260315T110000Z"):
        pd.DataFrame([{"preset": "conservative", "total_return": 0.0}]).to_csv(
            snapshot_dir / f"preset_compare_{stamp}.csv",
            index=False,
        )

    compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=False,
        keep_snapshot_count=2,
    )

    snapshots = sorted(snapshot_dir.glob("preset_compare_*.csv"))
    assert len(snapshots) == 2
    assert all("20260315T090000Z" not in p.name for p in snapshots)


def test_compare_presets_writes_cleanup_diagnostics(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    snapshot_dir = output_dir / "preset_compare"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)
    snapshot_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "portfolio_metrics_momentum_QQQ_ETH.json").write_text("{}", encoding="utf-8")
    pd.DataFrame([{"total_equity": 100000.0, "gross_exposure_ratio": 0.0}]).to_csv(
        output_dir / "sim_portfolio_capital_QQQ_ETH_momentum.csv",
        index=False,
    )
    (output_dir / "batch_conservative_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "batch_aggressive_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "report_index_conservative.md").write_text("# conservative\n", encoding="utf-8")
    (output_dir / "report_index_aggressive.md").write_text("# aggressive\n", encoding="utf-8")

    for stamp in ("20260315T090000Z", "20260315T100000Z"):
        pd.DataFrame([{"preset": "conservative", "total_return": 0.0}]).to_csv(
            snapshot_dir / f"preset_compare_{stamp}.csv",
            index=False,
        )

    compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=False,
        keep_snapshot_count=2,
    )

    cleanup_path = snapshot_dir / "preset_compare_cleanup_latest.json"
    assert cleanup_path.exists()
    payload = json.loads(cleanup_path.read_text(encoding="utf-8"))
    assert payload["before_count"] >= payload["after_count"]
    assert payload["after_count"] == len(list(snapshot_dir.glob("preset_compare_*.csv")))
    assert payload["keep_snapshot_count"] == 2
    assert payload["before_count"] == 3
    assert payload["after_count"] == 2
    assert payload["removed_by_count"] == 1
    history_files = list(snapshot_dir.glob("preset_compare_cleanup_*.json"))
    assert any(path.name != "preset_compare_cleanup_latest.json" for path in history_files)


def test_compare_presets_cleans_snapshots_by_date_range(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    snapshot_dir = output_dir / "preset_compare"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)
    snapshot_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "portfolio_metrics_momentum_QQQ_ETH.json").write_text("{}", encoding="utf-8")
    pd.DataFrame([{"total_equity": 100000.0, "gross_exposure_ratio": 0.0}]).to_csv(
        output_dir / "sim_portfolio_capital_QQQ_ETH_momentum.csv",
        index=False,
    )
    (output_dir / "batch_conservative_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "batch_aggressive_summary.json").write_text("{}", encoding="utf-8")
    (output_dir / "report_index_conservative.md").write_text("# conservative\n", encoding="utf-8")
    (output_dir / "report_index_aggressive.md").write_text("# aggressive\n", encoding="utf-8")

    for stamp in ("20260315T090000Z", "20260315T100000Z", "20260315T110000Z"):
        pd.DataFrame([{"preset": "conservative", "total_return": 0.0}]).to_csv(
            snapshot_dir / f"preset_compare_{stamp}.csv",
            index=False,
        )

    compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=False,
        keep_snapshot_count=0,
        cleanup_keep_start="2026-03-15",
        cleanup_keep_end="20260315T105959Z",
    )

    snapshots = sorted(snapshot_dir.glob("preset_compare_*.csv"))
    names = [p.name for p in snapshots]
    assert "preset_compare_20260315T090000Z.csv" in names
    assert "preset_compare_20260315T100000Z.csv" in names
    assert "preset_compare_20260315T110000Z.csv" not in names
    cleanup_payload = json.loads((snapshot_dir / "preset_compare_cleanup_latest.json").read_text(encoding="utf-8"))
    assert cleanup_payload["before_count"] == 4
    assert cleanup_payload["after_count"] == 3
    assert cleanup_payload["removed_by_date_range"] == 1


def test_compare_presets_rejects_invalid_cleanup_date_range(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    examples_dir = project_root / "examples"
    output_dir.mkdir(parents=True)
    examples_dir.mkdir(parents=True)

    conservative_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "conservative"},
        "tasks": [{"command": "report", "output_file": "report_index_conservative.md"}],
    }
    aggressive_cfg = {
        "command": "batch",
        "vars": {"symbols": "QQQ,ETH", "strategy": "momentum", "tag": "aggressive"},
        "tasks": [{"command": "report", "output_file": "report_index_aggressive.md"}],
    }
    (examples_dir / "config.batch.portfolio_conservative.json").write_text(
        json.dumps(conservative_cfg, ensure_ascii=False),
        encoding="utf-8",
    )
    (examples_dir / "config.batch.portfolio_aggressive.json").write_text(
        json.dumps(aggressive_cfg, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        compare_presets(
            project_root=project_root,
            output_dir=output_dir,
            run_batches=False,
            cleanup_keep_start="2026-03-16",
            cleanup_keep_end="2026-03-15",
        )
    assert "cleanup_keep_start" in str(exc.value)


def test_compare_presets_cleanup_only_writes_cleanup_diagnostics(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    snapshot_dir = output_dir / "preset_compare"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for stamp in ("20260315T090000Z", "20260315T100000Z", "20260315T110000Z"):
        pd.DataFrame([{"preset": "conservative", "total_return": 0.0}]).to_csv(
            snapshot_dir / f"preset_compare_{stamp}.csv",
            index=False,
        )

    csv_path, md_path = compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=False,
        keep_snapshot_count=1,
        cleanup_only=True,
    )

    assert csv_path == snapshot_dir / "preset_compare.csv"
    assert md_path == snapshot_dir / "preset_compare.md"
    assert not csv_path.exists()
    assert not md_path.exists()
    snapshots = sorted(snapshot_dir.glob("preset_compare_*.csv"))
    assert len(snapshots) == 1
    payload = json.loads((snapshot_dir / "preset_compare_cleanup_latest.json").read_text(encoding="utf-8"))
    assert payload["before_count"] == 3
    assert payload["after_count"] == 1
    assert payload["removed_by_count"] == 2
    history_files = list(snapshot_dir.glob("preset_compare_cleanup_*.json"))
    assert any(path.name != "preset_compare_cleanup_latest.json" for path in history_files)


def test_compare_presets_cleans_old_cleanup_history(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    snapshot_dir = output_dir / "preset_compare"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for stamp in ("20260315T090000Z", "20260315T100000Z", "20260315T110000Z"):
        (snapshot_dir / f"preset_compare_cleanup_{stamp}.json").write_text(
            json.dumps({"generated_at": "2026-03-15T10:00:00+00:00"}, ensure_ascii=False),
            encoding="utf-8",
        )
    for stamp in ("20260315T090000Z", "20260315T100000Z"):
        pd.DataFrame([{"preset": "conservative", "total_return": 0.0}]).to_csv(
            snapshot_dir / f"preset_compare_{stamp}.csv",
            index=False,
        )

    compare_presets(
        project_root=project_root,
        output_dir=output_dir,
        run_batches=False,
        cleanup_only=True,
        keep_snapshot_count=1,
        keep_cleanup_history_count=2,
    )

    cleanup_histories = sorted(
        path.name
        for path in snapshot_dir.glob("preset_compare_cleanup_*.json")
        if path.name != "preset_compare_cleanup_latest.json"
    )
    assert len(cleanup_histories) == 2
    assert "preset_compare_cleanup_20260315T090000Z.json" not in cleanup_histories


def test_compare_presets_rejects_negative_keep_cleanup_history(tmp_path):
    project_root = tmp_path / "proj"
    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError) as exc:
        compare_presets(
            project_root=project_root,
            output_dir=output_dir,
            run_batches=False,
            cleanup_only=True,
            keep_cleanup_history_count=-1,
        )
    assert "keep_cleanup_history_count" in str(exc.value)
