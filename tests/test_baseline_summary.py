import json

from market_signal_system.research.baseline_summary import build_baseline_daily_summary
from market_signal_system.storage import SQLiteStore


def test_build_baseline_daily_summary_collects_mvp_signal_and_report(tmp_path):
    (tmp_path / "mvp_summary_demo.json").write_text(
        json.dumps(
            {
                "run_tag": "demo",
                "symbols": ["QQQ", "ETH"],
                "strategies": ["ma_cross", "donchian", "momentum"],
                "backtest_topn_by_symbol": {
                    "QQQ": [{"rank": 1, "strategy": "momentum", "total_return": 0.12, "sharpe": 1.1, "max_drawdown": -0.1}],
                    "ETH": [{"rank": 1, "strategy": "donchian", "total_return": 0.21, "sharpe": 1.3, "max_drawdown": -0.2}],
                },
                "simulations": [
                    {"symbol": "QQQ", "trade_count": 8, "snapshot": {"total_equity": 103000, "cumulative_pnl": 3000, "return_pct": 0.03}},
                    {"symbol": "ETH", "trade_count": 6, "snapshot": {"total_equity": 98000, "cumulative_pnl": -2000, "return_pct": -0.02}},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "signal_pilot_alert_report_daily_20260316T000000Z.json").write_text(
        json.dumps(
            {
                "as_of": "2026-03-16T00:00:00+00:00",
                "windows": [7, 30, 60],
                "rows": [
                    {"window_days": 7, "symbol": "QQQ", "strategy": "score_regime", "signal_count": 2, "win_rate": 0.5, "avg_return_pct": 0.01},
                    {"window_days": 7, "symbol": "ETH", "strategy": "score_regime", "signal_count": 3, "win_rate": 2 / 3, "avg_return_pct": 0.02},
                    {"window_days": 30, "symbol": "QQQ", "strategy": "score_regime", "signal_count": 4, "win_rate": 0.75, "avg_return_pct": 0.03},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "baseline_daily_report_index.md").write_text(
        "\n".join(
            [
                "# 实验报告索引",
                "",
                "## 批处理执行摘要",
                "- run_config_batch_summary.json run_id=20260316T000000Z, tasks=6, success=6, failed=0",
                "- aggregate_all_runs: run_fail_rate=0.0000",
                "- aggregate_last_3_runs: run_fail_rate=0.0000",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "signal_alert_ledger.csv").write_text(
        "\n".join(
            [
                "alert_id,created_at,symbol,strategy,strategy_params,interval,side,alert_price,alert_reason,status,close_time,close_price,realized_pnl,realized_pnl_pct,current_price,current_pnl,current_pnl_pct,max_favorable_excursion,max_adverse_excursion,holding_bars,holding_days,notification_sent,notification_channel,notification_last_attempt_at,notification_last_sent_at,notification_fail_count",
                "a1,2026-03-16T00:00:00+00:00,QQQ,score_regime,{},1d,long,100,test,open,,,,,,,,,,0,0,false,,2026-03-16T00:00:00+00:00,,2",
                "a2,2026-03-16T00:00:00+00:00,ETH,score_regime,{},1d,long,100,test,open,,,,,,,,,,0,0,true,local_file,2026-03-16T00:00:00+00:00,2026-03-16T00:00:01+00:00,0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_baseline_daily_summary(tmp_path, as_of="2026-03-16", alert_ledger_file="signal_alert_ledger.csv")

    assert summary["sources"]["mvp_summary"] == "mvp_summary_demo.json"
    assert summary["sources"]["signal_report"] == "signal_pilot_alert_report_daily_20260316T000000Z.json"
    assert summary["sources"]["report_index"] == "baseline_daily_report_index.md"
    assert summary["account_id"] == "default"

    assert summary["mvp"]["backtest_best_by_symbol"]["QQQ"]["strategy"] == "momentum"
    assert summary["mvp"]["simulation_snapshot_by_symbol"]["ETH"]["trade_count"] == 6

    win7 = summary["signal_pilot"]["windows"]["7"]
    assert win7["signal_count"] == 5
    assert abs(win7["win_rate"] - 0.6) < 1e-9

    highlights = summary["report"]["highlights"]
    assert "aggregate_all_runs" in highlights
    assert "aggregate_last_3_runs" in highlights.get("aggregate_last", "")
    assert summary["signal_dispatch"]["open_alerts"] == 2
    assert summary["signal_dispatch"]["pending_notification"] == 1
    assert summary["signal_dispatch"]["failed_notification"] == 1
    assert abs(float(summary["signal_dispatch"]["failed_ratio"]) - 1.0) < 1e-9
    assert any(
        isinstance(a, dict) and str(a.get("metric", "")).startswith("dispatch.")
        for a in summary.get("alerts", [])
    )

    rows = summary["rows"]
    assert any(r["category"] == "mvp_backtest" and r["key"] == "QQQ.strategy" for r in rows)
    assert any(r["category"] == "signal_pilot" and r["key"] == "window_7.signal_count" for r in rows)
    assert any(r["category"] == "signal_dispatch" and r["key"] == "failed_ratio" for r in rows)


def test_build_baseline_daily_summary_collects_dispatch_metrics_from_ledger(tmp_path):
    (tmp_path / "mvp_summary_demo.json").write_text(
        json.dumps({"run_tag": "demo", "symbols": ["QQQ"], "strategies": ["score_regime"], "backtest_topn_by_symbol": {}, "simulations": []}),
        encoding="utf-8",
    )
    (tmp_path / "signal_pilot_alert_report_daily_20260316T000000Z.json").write_text(
        json.dumps({"as_of": "2026-03-16T00:00:00+00:00", "rows": []}),
        encoding="utf-8",
    )
    (tmp_path / "baseline_daily_report_index.md").write_text("# report", encoding="utf-8")

    state_dir = tmp_path.parent / "data" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = state_dir / "signal_alert_ledger.csv"
    ledger_path.write_text(
        "\n".join(
            [
                "alert_id,created_at,symbol,strategy,strategy_params,interval,side,alert_price,alert_reason,status,close_time,close_price,realized_pnl,realized_pnl_pct,current_price,current_pnl,current_pnl_pct,max_favorable_excursion,max_adverse_excursion,holding_bars,holding_days,notification_sent,notification_channel,notification_last_attempt_at,notification_last_sent_at,notification_fail_count",
                "a1,2026-03-16T00:00:00+00:00,QQQ,score_regime,{},1d,long,100,test,open,,,,,,,,,,0,0,false,,2026-03-16T00:10:00+00:00,,2",
                "a2,2026-03-16T00:00:00+00:00,QQQ,score_regime,{},1d,long,100,test,open,,,,,,,,,,0,0,false,,2026-03-16T00:11:00+00:00,,0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_baseline_daily_summary(
        tmp_path,
        as_of="2026-03-16",
        dispatch_max_failed_count=0,
        dispatch_max_failed_ratio=0.4,
    )
    dispatch = summary["signal_dispatch"]
    assert dispatch["open_alerts"] == 2
    assert dispatch["pending_notification"] == 2
    assert dispatch["failed_notification"] == 1
    assert abs(dispatch["failed_ratio"] - 0.5) < 1e-9
    assert any(a["metric"] == "dispatch.failed_ratio" for a in summary["alerts"])


def test_build_baseline_daily_summary_resolves_relative_ledger_to_state_dir(tmp_path):
    (tmp_path / "mvp_summary_demo.json").write_text(
        json.dumps({"run_tag": "demo", "symbols": ["QQQ"], "strategies": ["score_regime"], "backtest_topn_by_symbol": {}, "simulations": []}),
        encoding="utf-8",
    )
    (tmp_path / "signal_pilot_alert_report_daily_20260316T000000Z.json").write_text(
        json.dumps({"as_of": "2026-03-16T00:00:00+00:00", "rows": []}),
        encoding="utf-8",
    )
    (tmp_path / "baseline_daily_report_index.md").write_text("# report", encoding="utf-8")

    state_dir = tmp_path.parent / "data" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = state_dir / "signal_alert_ledger.custom.csv"
    ledger_path.write_text(
        "\n".join(
            [
                "alert_id,created_at,symbol,strategy,strategy_params,interval,side,alert_price,alert_reason,status,close_time,close_price,realized_pnl,realized_pnl_pct,current_price,current_pnl,current_pnl_pct,max_favorable_excursion,max_adverse_excursion,holding_bars,holding_days,notification_sent,notification_channel,notification_last_attempt_at,notification_last_sent_at,notification_fail_count",
                "a1,2026-03-16T00:00:00+00:00,QQQ,score_regime,{},1d,long,100,test,open,,,,,,,,,,0,0,false,,2026-03-16T00:10:00+00:00,,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = build_baseline_daily_summary(
        tmp_path,
        as_of="2026-03-16",
        alert_ledger_file="signal_alert_ledger.custom.csv",
        db_file=str(tmp_path / "isolated.db"),
    )
    assert summary["signal_dispatch"]["open_alerts"] == 1
    assert summary["sources"]["alert_ledger"] == "signal_alert_ledger.custom.csv"


def test_build_baseline_daily_summary_generates_threshold_alerts(tmp_path):
    (tmp_path / "mvp_summary_demo.json").write_text(
        json.dumps(
            {
                "run_tag": "demo",
                "backtest_topn_by_symbol": {
                    "QQQ": [{"rank": 1, "strategy": "momentum", "total_return": 0.12, "sharpe": 1.1}],
                },
                "simulations": [
                    {"symbol": "QQQ", "trade_count": 3, "snapshot": {"total_equity": 98000, "cumulative_pnl": -2000, "return_pct": -0.02}},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "signal_pilot_alert_report_daily_20260316T000000Z.json").write_text(
        json.dumps(
            {
                "as_of": "2026-03-16T00:00:00+00:00",
                "rows": [
                    {"window_days": 7, "symbol": "QQQ", "strategy": "score_regime", "signal_count": 1, "win_rate": 0.2, "avg_return_pct": -0.01},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "baseline_daily_report_index.md").write_text("# 实验报告索引\n", encoding="utf-8")

    summary = build_baseline_daily_summary(
        tmp_path,
        as_of="2026-03-16",
        signal_alert_window_days=7,
        signal_min_count=3,
        signal_min_win_rate=0.5,
        signal_min_avg_return_pct=0.0,
        simulation_min_return_pct=0.0,
    )

    assert summary["alert_rules"]["signal_alert_window_days"] == 7
    assert summary["alert_rules"]["signal_min_count"] == 3
    assert len(summary["alerts"]) == 4
    assert any(a["metric"] == "signal.window_7.signal_count" for a in summary["alerts"])
    assert any(a["metric"] == "signal.window_7.win_rate" for a in summary["alerts"])
    assert any(a["metric"] == "signal.window_7.avg_return_pct" for a in summary["alerts"])
    assert any(a["metric"] == "simulation.QQQ.return_pct" for a in summary["alerts"])
    assert any(r["category"] == "alerts" and r["key"].endswith(".metric") for r in summary["rows"])


def test_build_baseline_daily_summary_includes_dispatch_health_from_sqlite(tmp_path):
    (tmp_path / "mvp_summary_demo.json").write_text(
        json.dumps({"run_tag": "demo", "backtest_topn_by_symbol": {}, "simulations": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "signal_pilot_alert_report_daily_20260316T000000Z.json").write_text(
        json.dumps({"as_of": "2026-03-16T00:00:00+00:00", "rows": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "baseline_daily_report_index.md").write_text("# report", encoding="utf-8")

    db_path = tmp_path / "pilot.db"
    store = SQLiteStore(db_path)
    store.append_dispatch_records(
        "acct_ops",
        [
            {"alert_id": "a1", "event_time": "2026-03-15T01:00:00+00:00", "channel": "webhook", "status": "sent", "used_retry": True, "retry_count": 1},
            {"alert_id": "a2", "event_time": "2026-03-15T02:00:00+00:00", "channel": "webhook", "status": "failed", "used_retry": False, "retry_count": 0},
            {"alert_id": "a3", "event_time": "2026-01-01T00:00:00+00:00", "channel": "webhook", "status": "failed", "used_retry": False, "retry_count": 0},
        ],
    )

    summary = build_baseline_daily_summary(
        tmp_path,
        as_of="2026-03-16",
        account_id="acct_ops",
        db_file=str(db_path),
        dispatch_window_days=30,
    )
    health = summary["signal_dispatch_health"]
    assert summary["account_id"] == "acct_ops"
    assert health["dispatch_window_days"] == 30
    assert health["attempt_count"] == 2
    assert health["sent_count"] == 1
    assert health["failed_count"] == 1
    assert abs(float(health["failed_ratio"]) - 0.5) < 1e-9
    assert health["retry_used_count"] == 1
    assert health["retry_count_sum"] == 1
    assert abs(float(health["retry_hit_rate"]) - 0.5) < 1e-9
    assert health["last_event_time"] == "2026-03-15T02:00:00+00:00"
    assert any(
        row["category"] == "signal_dispatch_health" and row["key"] == "attempt_count"
        for row in summary.get("rows", [])
    )
