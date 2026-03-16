import os
import subprocess
import sys
import uuid
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_module_entry_works_without_pythonpath():
    project_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    proc = subprocess.run(
        [sys.executable, "-m", "market_signal_system", "--help"],
        cwd=str(project_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "市场信号系统 CLI" in proc.stdout


def test_simulate_cli_can_resume_state_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    state_dir = project_root / "data" / "state"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"resume_{run_id}"
    cache_path = cache_dir / f"QQQ_{interval}.csv"
    state_file = f"simulate_resume_{run_id}.json"
    state_path = state_dir / state_file

    cache_path.write_text(
        "\n".join(
            [
                ",open,high,low,close,volume",
                "2020-01-01T00:00:00+00:00,10,10,10,10,100",
                "2020-01-02T00:00:00+00:00,11,11,11,11,100",
                "2020-01-03T00:00:00+00:00,12,12,12,12,100",
                "2020-01-04T00:00:00+00:00,11,11,11,11,100",
                "2020-01-05T00:00:00+00:00,10,10,10,10,100",
                "2020-01-06T00:00:00+00:00,9,9,9,9,100",
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    base_cmd = [
        sys.executable,
        "-m",
        "market_signal_system",
        "simulate",
        "--symbol",
        "QQQ",
        "--strategy",
        "ma_cross",
        "--params",
        '{"fast_window":2,"slow_window":3}',
        "--start",
        "2020-01-01",
        "--interval",
        interval,
        "--state-file",
        state_file,
    ]

    try:
        first = subprocess.run(
            [*base_cmd, "--end", "2020-01-04"],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert first.returncode == 0, first.stderr
        assert state_path.exists()
        first_state = json.loads(state_path.read_text(encoding="utf-8"))
        first_trade_count = len(first_state.get("trades", []))

        second = subprocess.run(
            [*base_cmd, "--end", "2020-01-06"],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert second.returncode == 0, second.stderr
        second_state = json.loads(state_path.read_text(encoding="utf-8"))
        second_trade_count = len(second_state.get("trades", []))

        assert second_trade_count > first_trade_count
        assert "State persisted: data/state/" in second.stdout
    finally:
        if cache_path.exists():
            cache_path.unlink()
        if state_path.exists():
            state_path.unlink()


def test_backtest_cli_output_tag_avoids_overwrite_via_subprocess():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"backtest_{run_id}"
    output_tag = f"macd_{run_id}"
    cache_path = cache_dir / f"QQQ_{interval}.csv"
    metrics_path = output_dir / f"metrics_QQQ_macd_regime_{output_tag}.json"
    equity_path = output_dir / f"equity_QQQ_macd_regime_{output_tag}.csv"
    trades_path = output_dir / f"trades_QQQ_macd_regime_{output_tag}.csv"
    signals_path = output_dir / f"signals_QQQ_macd_regime_{output_tag}.csv"

    cache_path.write_text(
        "\n".join(
            [
                ",open,high,low,close,volume",
                "2020-01-01T00:00:00+00:00,100,100,100,100,1000",
                "2020-01-02T00:00:00+00:00,101,101,101,101,1000",
                "2020-01-03T00:00:00+00:00,102,102,102,102,1000",
                "2020-01-04T00:00:00+00:00,100,100,100,100,1000",
                "2020-01-05T00:00:00+00:00,99,99,99,99,1000",
                "2020-01-06T00:00:00+00:00,103,103,103,103,1000",
                "2020-01-07T00:00:00+00:00,104,104,104,104,1000",
                "2020-01-08T00:00:00+00:00,98,98,98,98,1000",
                "2020-01-09T00:00:00+00:00,97,97,97,97,1000",
                "2020-01-10T00:00:00+00:00,101,101,101,101,1000",
                "2020-01-11T00:00:00+00:00,102,102,102,102,1000",
                "2020-01-12T00:00:00+00:00,96,96,96,96,1000",
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "backtest",
                "--symbol",
                "QQQ",
                "--strategy",
                "macd_regime",
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-12",
                "--interval",
                interval,
                "--params",
                '{"fast_span":2,"slow_span":4,"signal_span":2,"regime_window":3,"volatility_window":2,"macd_ratio_threshold":0.0}',
                "--output-tag",
                output_tag,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert metrics_path.exists()
        assert equity_path.exists()
        assert trades_path.exists()
        assert signals_path.exists()
    finally:
        if cache_path.exists():
            cache_path.unlink()
        for path in (metrics_path, equity_path, trades_path, signals_path):
            if path.exists():
                path.unlink()


def test_compare_cli_default_strategies_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"compare_{run_id}"
    qqq_cache = cache_dir / f"QQQ_{interval}.csv"
    eth_cache = cache_dir / f"ETH_{interval}.csv"
    leaderboard_path = output_dir / "leaderboard_QQQ_ETH.csv"
    by_symbol_path = output_dir / "leaderboard_by_symbol_QQQ_ETH.csv"

    rows = [",open,high,low,close,volume"]
    start_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for day in range(420):
        ts = start_ts + timedelta(days=day)
        price = 100 + day * 0.2 + (2 if day % 17 == 0 else 0) - (1 if day % 29 == 0 else 0)
        rows.append(
            f"{ts.isoformat()},{price:.4f},{price + 1:.4f},{price - 1:.4f},{price:.4f},1000"
        )
    qqq_cache.write_text("\n".join(rows), encoding="utf-8")
    eth_cache.write_text("\n".join(rows), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "compare",
                "--symbols",
                "QQQ,ETH",
                "--start",
                "2020-01-01",
                "--end",
                "2020-12-31",
                "--interval",
                interval,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert leaderboard_path.exists()
        assert by_symbol_path.exists()
        csv_text = leaderboard_path.read_text(encoding="utf-8")
        by_symbol_text = by_symbol_path.read_text(encoding="utf-8")
        assert "score_regime" in csv_text
        assert "atr_regime" in csv_text
        assert "dual_momentum" in csv_text
        assert "symbol_rank" in by_symbol_text
    finally:
        if qqq_cache.exists():
            qqq_cache.unlink()
        if eth_cache.exists():
            eth_cache.unlink()
        if leaderboard_path.exists():
            leaderboard_path.unlink()
        if by_symbol_path.exists():
            by_symbol_path.unlink()


def test_update_cache_cli_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"update_cache_{run_id}"
    qqq_cache = cache_dir / f"QQQ_{interval}.csv"
    eth_cache = cache_dir / f"ETH_{interval}.csv"

    rows = [
        ",open,high,low,close,volume",
        "2020-01-01T00:00:00+00:00,100,101,99,100,1000",
        "2020-01-02T00:00:00+00:00,101,102,100,101,1100",
        "2020-01-03T00:00:00+00:00,102,103,101,102,1200",
    ]
    qqq_cache.write_text("\n".join(rows), encoding="utf-8")
    eth_cache.write_text("\n".join(rows), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "update-cache",
                "--symbols",
                "QQQ,ETH",
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-03",
                "--interval",
                interval,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["command"] == "update-cache"
        assert payload["symbol_count"] == 2
        assert len(payload["results"]) == 2
    finally:
        if qqq_cache.exists():
            qqq_cache.unlink()
        if eth_cache.exists():
            eth_cache.unlink()


def test_simulate_cli_output_tag_avoids_overwrite_via_subprocess():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    state_dir = project_root / "data" / "state"
    output_dir = project_root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"sim_tag_{run_id}"
    output_tag = f"v1_{run_id}"
    cache_path = cache_dir / f"QQQ_{interval}.csv"
    state_file = f"sim_output_tag_{run_id}.json"
    state_path = state_dir / state_file
    signal_path = output_dir / f"sim_signals_QQQ_ma_cross_{output_tag}.csv"
    equity_path = output_dir / f"sim_equity_QQQ_ma_cross_{output_tag}.csv"
    summary_path = output_dir / f"sim_summary_QQQ_ma_cross_{output_tag}.json"

    cache_path.write_text(
        "\n".join(
            [
                ",open,high,low,close,volume",
                "2020-01-01T00:00:00+00:00,100,100,100,100,1000",
                "2020-01-02T00:00:00+00:00,101,101,101,101,1000",
                "2020-01-03T00:00:00+00:00,102,102,102,102,1000",
                "2020-01-04T00:00:00+00:00,99,99,99,99,1000",
                "2020-01-05T00:00:00+00:00,98,98,98,98,1000",
                "2020-01-06T00:00:00+00:00,103,103,103,103,1000",
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "simulate",
                "--symbol",
                "QQQ",
                "--strategy",
                "ma_cross",
                "--params",
                '{"fast_window":2,"slow_window":3}',
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-06",
                "--interval",
                interval,
                "--state-file",
                state_file,
                "--output-tag",
                output_tag,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert signal_path.exists()
        assert equity_path.exists()
        assert summary_path.exists()
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        assert payload["output_tag"] == output_tag
    finally:
        if cache_path.exists():
            cache_path.unlink()
        if state_path.exists():
            state_path.unlink()
        for path in (signal_path, equity_path, summary_path):
            if path.exists():
                path.unlink()


def test_compare_cli_weekly_interval_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    qqq_cache = cache_dir / "QQQ_1d.csv"
    eth_cache = cache_dir / "ETH_1d.csv"
    qqq_backup = cache_dir / f"QQQ_1d.{run_id}.bak"
    eth_backup = cache_dir / f"ETH_1d.{run_id}.bak"
    leaderboard_path = output_dir / "leaderboard_QQQ_ETH.csv"
    by_symbol_path = output_dir / "leaderboard_by_symbol_QQQ_ETH.csv"

    if qqq_cache.exists():
        qqq_cache.rename(qqq_backup)
    if eth_cache.exists():
        eth_cache.rename(eth_backup)

    rows = [",open,high,low,close,volume"]
    start_ts = datetime(2018, 1, 1, tzinfo=timezone.utc)
    for day in range(900):
        ts = start_ts + timedelta(days=day)
        base_price = 100 + day * 0.15 + (1.2 if day % 13 == 0 else 0.0) - (0.8 if day % 23 == 0 else 0.0)
        rows.append(
            f"{ts.isoformat()},{base_price:.4f},{base_price + 1.0:.4f},{base_price - 1.0:.4f},{base_price:.4f},1200"
        )
    qqq_cache.write_text("\n".join(rows), encoding="utf-8")
    eth_cache.write_text("\n".join(rows), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "compare",
                "--symbols",
                "QQQ,ETH",
                "--strategies",
                "ma_cross,dual_momentum",
                "--start",
                "2019-01-01",
                "--end",
                "2020-12-31",
                "--interval",
                "1wk",
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert leaderboard_path.exists()
        assert by_symbol_path.exists()
        csv_text = leaderboard_path.read_text(encoding="utf-8")
        assert "dual_momentum" in csv_text
    finally:
        if qqq_cache.exists():
            qqq_cache.unlink()
        if eth_cache.exists():
            eth_cache.unlink()
        if qqq_backup.exists():
            qqq_backup.rename(qqq_cache)
        if eth_backup.exists():
            eth_backup.rename(eth_cache)
        if leaderboard_path.exists():
            leaderboard_path.unlink()
        if by_symbol_path.exists():
            by_symbol_path.unlink()


def test_mvp_cli_runs_end_to_end_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    state_dir = project_root / "data" / "state"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"mvp_{run_id}"
    run_tag = f"test_{run_id}"
    state_prefix = f"mvp_state_{run_id}"
    qqq_cache = cache_dir / f"QQQ_{interval}.csv"
    eth_cache = cache_dir / f"ETH_{interval}.csv"
    summary_path = output_dir / f"mvp_summary_{run_tag}.json"
    qqq_state = state_dir / f"{state_prefix}_QQQ.json"
    eth_state = state_dir / f"{state_prefix}_ETH.json"

    rows = [",open,high,low,close,volume"]
    start_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for day in range(120):
        ts = start_ts + timedelta(days=day)
        qqq_price = 100 + day * 0.1 + (1 if day % 13 == 0 else 0)
        eth_price = 200 + day * 0.4 - (2 if day % 19 == 0 else 0)
        rows.append(
            f"{ts.isoformat()},{qqq_price:.4f},{qqq_price + 1:.4f},{qqq_price - 1:.4f},{qqq_price:.4f},1000"
        )
    qqq_cache.write_text("\n".join(rows), encoding="utf-8")

    eth_rows = [",open,high,low,close,volume"]
    for day in range(120):
        ts = start_ts + timedelta(days=day)
        eth_price = 200 + day * 0.4 - (2 if day % 19 == 0 else 0)
        eth_rows.append(
            f"{ts.isoformat()},{eth_price:.4f},{eth_price + 2:.4f},{eth_price - 2:.4f},{eth_price:.4f},2000"
        )
    eth_cache.write_text("\n".join(eth_rows), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "mvp",
                "--start",
                "2020-01-01",
                "--end",
                "2020-04-29",
                "--interval",
                interval,
                "--run-tag",
                run_tag,
                "--state-prefix",
                state_prefix,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["symbols"] == ["QQQ", "ETH"]
        assert len(summary["backtests"]) == 6
        assert len(summary["simulations"]) == 2
        assert "backtest_topn_by_symbol" in summary
        assert "QQQ" in summary["backtest_topn_by_symbol"]
        assert len(summary["backtest_topn_by_symbol"]["QQQ"]) >= 1
        assert "backtest_topn_overall" in summary
        assert len(summary["backtest_topn_overall"]) >= 1
        assert "mvp_acceptance" in summary
        assert "overall_passed" in summary["mvp_acceptance"]
        assert isinstance(summary["mvp_acceptance"].get("checks"), list)
        assert qqq_state.exists()
        assert eth_state.exists()
    finally:
        if qqq_cache.exists():
            qqq_cache.unlink()
        if eth_cache.exists():
            eth_cache.unlink()
        if qqq_state.exists():
            qqq_state.unlink()
        if eth_state.exists():
            eth_state.unlink()
        for path in output_dir.glob(f"mvp_*_{run_tag}.*"):
            path.unlink()
        if summary_path.exists():
            summary_path.unlink()


def test_mvp_cli_strict_acceptance_fails_when_not_covering_short_signal():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    state_dir = project_root / "data" / "state"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"mvp_strict_{run_id}"
    run_tag = f"strict_{run_id}"
    state_prefix = f"mvp_state_strict_{run_id}"
    qqq_cache = cache_dir / f"QQQ_{interval}.csv"
    eth_cache = cache_dir / f"ETH_{interval}.csv"
    summary_path = output_dir / f"mvp_summary_{run_tag}.json"
    qqq_state = state_dir / f"{state_prefix}_QQQ.json"
    eth_state = state_dir / f"{state_prefix}_ETH.json"

    qqq_rows = [",open,high,low,close,volume"]
    eth_rows = [",open,high,low,close,volume"]
    start_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    for day in range(180):
        ts = start_ts + timedelta(days=day)
        qqq_price = 100 + day * 0.6
        eth_price = 300 + day * 1.2
        qqq_rows.append(
            f"{ts.isoformat()},{qqq_price:.4f},{qqq_price + 1:.4f},{qqq_price - 1:.4f},{qqq_price:.4f},1000"
        )
        eth_rows.append(
            f"{ts.isoformat()},{eth_price:.4f},{eth_price + 2:.4f},{eth_price - 2:.4f},{eth_price:.4f},1500"
        )
    qqq_cache.write_text("\n".join(qqq_rows), encoding="utf-8")
    eth_cache.write_text("\n".join(eth_rows), encoding="utf-8")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "mvp",
                "--start",
                "2020-01-01",
                "--end",
                "2020-06-28",
                "--interval",
                interval,
                "--run-tag",
                run_tag,
                "--state-prefix",
                state_prefix,
                "--strict-acceptance",
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        acceptance = summary.get("mvp_acceptance", {})
        assert acceptance.get("overall_passed") is False
        assert "supports_long_short_flat" in acceptance.get("failed_check_ids", [])
    finally:
        if qqq_cache.exists():
            qqq_cache.unlink()
        if eth_cache.exists():
            eth_cache.unlink()
        if qqq_state.exists():
            qqq_state.unlink()
        if eth_state.exists():
            eth_state.unlink()
        for path in output_dir.glob(f"mvp_*_{run_tag}.*"):
            path.unlink()
        if summary_path.exists():
            summary_path.unlink()


def test_diagnose_data_cli_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    cache_dir = project_root / "data" / "cache"
    output_dir = project_root / "outputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    interval = f"diagnose_{run_id}"
    cache_path = cache_dir / f"QQQ_{interval}.csv"
    report_path = output_dir / f"data_quality_QQQ_{interval}.json"

    cache_path.write_text(
        "\n".join(
            [
                ",open,high,low,close,volume",
                "2020-01-01T00:00:00+00:00,100,101,99,100,1000",
                "2020-01-02T00:00:00+00:00,101,102,100,101,1000",
                "2020-01-03T00:00:00+00:00,102,103,101,102,1000",
                "2020-01-04T00:00:00+00:00,103,104,102,103,1000",
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "diagnose-data",
                "--symbol",
                "QQQ",
                "--start",
                "2020-01-01",
                "--end",
                "2020-01-04",
                "--interval",
                interval,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert report_path.exists()
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["row_count"] == 4
    finally:
        if cache_path.exists():
            cache_path.unlink()
        if report_path.exists():
            report_path.unlink()


def test_baseline_summary_cli_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    mvp_file = output_dir / f"mvp_summary_{run_id}.json"
    signal_file = output_dir / f"signal_pilot_alert_report_daily_{run_id}.json"
    report_file = output_dir / f"baseline_daily_report_index_{run_id}.md"
    out_json = output_dir / f"baseline_daily_digest_{run_id}.json"
    out_csv = output_dir / f"baseline_daily_digest_{run_id}.csv"
    alert_queue = output_dir / f"baseline_alert_queue_{run_id}.jsonl"

    mvp_file.write_text(
        json.dumps(
            {
                "run_tag": run_id,
                "symbols": ["QQQ", "ETH"],
                "strategies": ["ma_cross", "donchian", "momentum"],
                "backtest_topn_by_symbol": {
                    "QQQ": [{"rank": 1, "strategy": "momentum", "total_return": 0.12, "sharpe": 1.0}],
                    "ETH": [{"rank": 1, "strategy": "donchian", "total_return": 0.18, "sharpe": 1.1}],
                },
                "simulations": [
                    {
                        "symbol": "QQQ",
                        "trade_count": 2,
                        "snapshot": {"total_equity": 101000, "cumulative_pnl": 1000, "return_pct": 0.01},
                    },
                    {
                        "symbol": "ETH",
                        "trade_count": 3,
                        "snapshot": {"total_equity": 99000, "cumulative_pnl": -1000, "return_pct": -0.01},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    signal_file.write_text(
        json.dumps(
            {
                "as_of": "2026-03-16T00:00:00+00:00",
                "rows": [
                    {
                        "window_days": 7,
                        "symbol": "QQQ",
                        "strategy": "score_regime",
                        "signal_count": 2,
                        "win_rate": 0.5,
                        "avg_return_pct": 0.01,
                    },
                    {
                        "window_days": 30,
                        "symbol": "ETH",
                        "strategy": "score_regime",
                        "signal_count": 3,
                        "win_rate": 0.66,
                        "avg_return_pct": 0.02,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_file.write_text(
        "\n".join(
            [
                "# 实验报告索引",
                "",
                "## 批处理执行摘要",
                "- aggregate_all_runs: run_fail_rate=0.0000",
            ]
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "baseline-summary",
                "--mvp-summary-file",
                mvp_file.name,
                "--signal-report-json-file",
                signal_file.name,
                "--report-index-file",
                report_file.name,
                "--output-json",
                out_json.name,
                "--output-csv",
                out_csv.name,
                "--as-of",
                "2026-03-16",
                "--emit-alert-queue",
                "--alert-queue-file",
                alert_queue.name,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert out_json.exists()
        assert out_csv.exists()
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        assert payload["sources"]["mvp_summary"] == mvp_file.name
        assert payload["sources"]["signal_report"] == signal_file.name
        assert payload["sources"]["report_index"] == report_file.name
        assert "alert_rules" in payload
        assert alert_queue.exists()
    finally:
        for path in (mvp_file, signal_file, report_file, out_json, out_csv, alert_queue):
            if path.exists():
                path.unlink()


def test_dispatch_alerts_cli_runs_via_subprocess_without_network():
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "outputs"
    state_dir = project_root / "data" / "state"
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    queue_file = output_dir / f"signal_pilot_notifications_{run_id}.jsonl"
    sink_file = output_dir / f"signal_pilot_notifications_dispatched_{run_id}.jsonl"
    ledger_file = state_dir / f"signal_alert_ledger_{run_id}.csv"

    queue_file.write_text(json.dumps({"alert_id": f"a_{run_id}", "symbol": "QQQ"}, ensure_ascii=False) + "\n", encoding="utf-8")
    ledger_file.write_text(
        "\n".join(
            [
                "alert_id,created_at,symbol,strategy,strategy_params,interval,side,alert_price,alert_reason,status,close_time,close_price,realized_pnl,realized_pnl_pct,current_price,current_pnl,current_pnl_pct,max_favorable_excursion,max_adverse_excursion,holding_bars,holding_days,notification_sent,notification_channel",
                f"a_{run_id},2026-03-16T00:00:00+00:00,QQQ,score_regime,{{}},1d,long,100,test,open,,,,,,,,,,0,0,false,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "market_signal_system",
                "dispatch-alerts",
                "--queue-file",
                queue_file.name,
                "--sink-file",
                sink_file.name,
                "--ledger-file",
                ledger_file.name,
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert sink_file.exists()
        assert "\"sent\": 1" in proc.stdout
    finally:
        for path in (queue_file, sink_file, ledger_file):
            if path.exists():
                path.unlink()
