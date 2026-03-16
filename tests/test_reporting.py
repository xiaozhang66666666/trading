import json
import gzip
import os

import pandas as pd

from market_signal_system.research.reporting import build_report_index, export_champion_switch_trend_csv


def test_build_report_index_collects_metrics(tmp_path):
    metrics = {
        "total_return": 0.12,
        "sharpe": 1.5,
        "max_drawdown": -0.1,
        "benchmark_total_return": 0.08,
        "excess_total_return": 0.04,
        "information_ratio": 0.66,
    }
    (tmp_path / "metrics_QQQ_ma_cross.json").write_text(json.dumps(metrics), encoding="utf-8")
    content = build_report_index(tmp_path)
    assert "单策略回测" in content
    assert "metrics_QQQ_ma_cross.json" in content
    assert "benchmark_total_return=0.0800" in content
    assert "excess_total_return=0.0400" in content


def test_build_report_index_collects_score_vs_macd_summary(tmp_path):
    (tmp_path / "metrics_QQQ_score_regime_score_base.json").write_text(
        json.dumps(
            {
                "total_return": 0.20,
                "sharpe": 1.10,
                "calmar": 0.80,
                "max_drawdown": -0.25,
                "win_rate": 0.48,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "metrics_QQQ_macd_regime_macd_base.json").write_text(
        json.dumps(
            {
                "total_return": 0.15,
                "sharpe": 0.90,
                "calmar": 0.70,
                "max_drawdown": -0.22,
                "win_rate": 0.44,
            }
        ),
        encoding="utf-8",
    )

    content = build_report_index(tmp_path)
    assert "策略对照摘要（score_regime vs macd_regime）" in content
    assert "QQQ.score_minus_macd.total_return=0.0500" in content
    assert "QQQ.score_minus_macd.sharpe=0.2000" in content


def test_build_report_index_collects_portfolio_attribution(tmp_path):
    pd.DataFrame(
        [
            {"symbol": "QQQ", "total_contribution": 0.12, "annualized_vol_contribution": 0.2},
            {"symbol": "ETH", "total_contribution": 0.05, "annualized_vol_contribution": 0.3},
        ]
    ).to_csv(tmp_path / "portfolio_attribution_momentum_QQQ_ETH.csv", index=False)
    content = build_report_index(tmp_path)
    assert "组合归因" in content
    assert "top_contrib=QQQ" in content


def test_build_report_index_collects_portfolio_metrics_with_benchmark(tmp_path):
    payload = {
        "total_return": 0.18,
        "sharpe": 1.2,
        "max_drawdown": -0.14,
        "benchmark_total_return": 0.11,
        "excess_total_return": 0.07,
        "information_ratio": 0.58,
    }
    (tmp_path / "portfolio_metrics_momentum_QQQ_ETH.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    content = build_report_index(tmp_path)
    assert "组合回测" in content
    assert "portfolio_metrics_momentum_QQQ_ETH.json" in content
    assert "benchmark_total_return=0.1100" in content


def test_build_report_index_collects_stability_summary(tmp_path):
    (tmp_path / "stability_summary_QQQ_donchian.json").write_text(
        json.dumps({"window_count": 6, "top_param_set_share": 0.5, "positive_sharpe_ratio": 0.67}),
        encoding="utf-8",
    )
    content = build_report_index(tmp_path)
    assert "参数稳定性" in content
    assert "stability_summary_QQQ_donchian.json" in content


def test_build_report_index_collects_portfolio_alerts(tmp_path):
    pd.DataFrame(
        [
            {"pair": "QQQ/ETH", "alert_level": "high"},
            {"pair": "QQQ/ETH", "alert_level": "watch"},
        ]
    ).to_csv(tmp_path / "portfolio_alerts_momentum_QQQ_ETH.csv", index=False)
    content = build_report_index(tmp_path)
    assert "相关性与拥挤度告警" in content
    assert "portfolio_alerts_momentum_QQQ_ETH.csv" in content


def test_build_report_index_collects_portfolio_weights(tmp_path):
    pd.DataFrame(
        [
            {"timestamp": "2024-01-01", "QQQ_weight": 0.5, "ETH_weight": -0.4},
            {"timestamp": "2024-01-02", "QQQ_weight": 0.4, "ETH_weight": -0.3},
        ]
    ).to_csv(tmp_path / "portfolio_weights_momentum_QQQ_ETH.csv", index=False)
    content = build_report_index(tmp_path)
    assert "组合权重快照" in content
    assert "portfolio_weights_momentum_QQQ_ETH.csv" in content


def test_build_report_index_collects_portfolio_drift(tmp_path):
    pd.DataFrame(
        [
            {
                "timestamp": "2024-01-01",
                "QQQ_weight_gap": 0.01,
                "ETH_weight_gap": -0.01,
                "abs_weight_gap_sum": 0.02,
                "drift_alert_level": "watch",
            },
            {
                "timestamp": "2024-01-02",
                "QQQ_weight_gap": -0.02,
                "ETH_weight_gap": 0.03,
                "abs_weight_gap_sum": 0.05,
                "drift_alert_level": "high",
            },
        ]
    ).to_csv(tmp_path / "portfolio_drift_momentum_QQQ_ETH.csv", index=False)
    content = build_report_index(tmp_path)
    assert "组合权重偏移" in content
    assert "portfolio_drift_momentum_QQQ_ETH.csv" in content
    assert "drift_alerts(high=1, watch=1, max_high_streak=1, high_segments=1)" in content


def test_build_report_index_collects_portfolio_capital_summary(tmp_path):
    pd.DataFrame(
        [
            {
                "timestamp": "2024-01-01",
                "total_equity": 100000.0,
                "gross_exposure": 50000.0,
                "gross_exposure_ratio": 0.5,
                "used_margin": 30000.0,
                "available_margin": 60000.0,
                "reserve_cash": 5000.0,
            },
            {
                "timestamp": "2024-01-02",
                "total_equity": 105000.0,
                "gross_exposure": 63000.0,
                "gross_exposure_ratio": 0.6,
                "used_margin": 42000.0,
                "available_margin": 52500.0,
                "reserve_cash": 5250.0,
            },
        ]
    ).to_csv(tmp_path / "sim_portfolio_capital_QQQ_ETH_momentum.csv", index=False)
    content = build_report_index(tmp_path)
    assert "组合资金占用摘要" in content
    assert "sim_portfolio_capital_QQQ_ETH_momentum.csv" in content
    assert "avg_exposure=0.5500" in content
    assert "avg_margin_util=0.3889" in content


def test_build_report_index_collects_sim_equity_summary(tmp_path):
    pd.DataFrame(
        [
            {"timestamp": "2024-01-01", "total_equity": 100000.0},
            {"timestamp": "2024-01-02", "total_equity": 102000.0},
            {"timestamp": "2024-01-03", "total_equity": 101000.0},
        ]
    ).to_csv(tmp_path / "sim_equity_ETH_momentum.csv", index=False)
    content = build_report_index(tmp_path)
    assert "单标的模拟资金曲线摘要" in content
    assert "sim_equity_ETH_momentum.csv" in content
    assert "total_return=0.0100" in content


def test_build_report_index_collects_portfolio_rebalance_summary(tmp_path):
    pd.DataFrame(
        [
            {"timestamp": "2024-01-01", "triggered": 1, "rebalance_turnover": 0.2, "rebalance_cost": 0.0004},
            {"timestamp": "2024-01-02", "triggered": 0, "rebalance_turnover": 0.0, "rebalance_cost": 0.0},
            {"timestamp": "2024-01-03", "triggered": 1, "rebalance_turnover": 0.1, "rebalance_cost": 0.0002},
        ]
    ).to_csv(tmp_path / "portfolio_rebalance_momentum_QQQ_ETH.csv", index=False)
    content = build_report_index(tmp_path)
    assert "漂移再平衡实验" in content
    assert "portfolio_rebalance_momentum_QQQ_ETH.csv" in content
    assert "triggers=2" in content
    assert "turnover=0.3000" in content


def test_build_report_index_ranks_rebalance_files(tmp_path):
    pd.DataFrame(
        [
            {"timestamp": "2024-01-01", "triggered": 1, "rebalance_turnover": 0.2, "rebalance_cost": 0.0004},
            {"timestamp": "2024-01-02", "triggered": 1, "rebalance_turnover": 0.1, "rebalance_cost": 0.0002},
        ]
    ).to_csv(tmp_path / "portfolio_rebalance_a.csv", index=False)
    pd.DataFrame(
        [
            {"timestamp": "2024-01-01", "triggered": 1, "rebalance_turnover": 0.4, "rebalance_cost": 0.0012},
            {"timestamp": "2024-01-02", "triggered": 1, "rebalance_turnover": 0.2, "rebalance_cost": 0.0008},
        ]
    ).to_csv(tmp_path / "portfolio_rebalance_b.csv", index=False)
    content = build_report_index(tmp_path)
    assert "best_by_avg_cost: `portfolio_rebalance_a.csv`" in content
    assert "worst_by_avg_cost: `portfolio_rebalance_b.csv`" in content


def test_build_report_index_collects_leaderboard_excess_top_bottom(tmp_path):
    pd.DataFrame(
        [
            {"symbol": "QQQ", "strategy": "score_regime", "composite_score": 0.90, "excess_total_return": 0.12},
            {"symbol": "QQQ", "strategy": "macd_regime", "composite_score": 0.70, "excess_total_return": -0.03},
            {"symbol": "ETH", "strategy": "atr_regime", "composite_score": 0.65, "excess_total_return": 0.05},
        ]
    ).to_csv(tmp_path / "leaderboard_QQQ_ETH.csv", index=False)
    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.88, "excess_total_return": 0.20},
            {"symbol": "ETH", "strategy": "macd_regime", "composite_score": 0.62, "excess_total_return": -0.08},
        ]
    ).to_csv(tmp_path / "leaderboard_ETH.csv", index=False)

    content = build_report_index(tmp_path)
    assert "多策略排行榜" in content
    assert "leaderboard_QQQ_ETH.csv" in content
    assert "excess_top=score_regime@QQQ (0.1200), excess_bottom=macd_regime@QQQ (-0.0300)" in content
    assert "aggregate_excess_top: `leaderboard_ETH.csv` score_regime@ETH (0.2000)" in content
    assert "aggregate_excess_bottom: `leaderboard_ETH.csv` macd_regime@ETH (-0.0800)" in content


def test_build_report_index_collects_symbol_group_champions(tmp_path):
    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.81, "symbol_rank": 1},
            {"symbol": "ETH", "strategy": "macd_regime", "composite_score": 0.62, "symbol_rank": 2},
            {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.77, "symbol_rank": 1},
            {"symbol": "QQQ", "strategy": "donchian", "composite_score": 0.69, "symbol_rank": 2},
        ]
    ).to_csv(tmp_path / "leaderboard_by_symbol_QQQ_ETH.csv", index=False)

    content = build_report_index(tmp_path)
    assert "分组排行榜（按标的）" in content
    assert "leaderboard_by_symbol_QQQ_ETH.csv" in content
    assert "ETH:score_regime(0.8100)" in content
    assert "QQQ:atr_regime(0.7700)" in content


def test_build_report_index_collects_symbol_group_champion_stability(tmp_path):
    file_a = tmp_path / "leaderboard_by_symbol_QQQ_ETH_a.csv"
    file_b = tmp_path / "leaderboard_by_symbol_QQQ_ETH_b.csv"
    file_c = tmp_path / "leaderboard_by_symbol_QQQ_ETH_c.csv"

    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.81, "symbol_rank": 1},
            {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.77, "symbol_rank": 1},
        ]
    ).to_csv(file_a, index=False)
    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "macd_regime", "composite_score": 0.82, "symbol_rank": 1},
            {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.79, "symbol_rank": 1},
        ]
    ).to_csv(file_b, index=False)
    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "macd_regime", "composite_score": 0.78, "symbol_rank": 1},
            {"symbol": "QQQ", "strategy": "donchian", "composite_score": 0.80, "symbol_rank": 1},
        ]
    ).to_csv(file_c, index=False)

    os.utime(file_a, (1000, 1000))
    os.utime(file_b, (2000, 2000))
    os.utime(file_c, (3000, 3000))

    content = build_report_index(tmp_path)
    assert "分组冠军稳定性" in content
    assert "ETH: samples=3, switches=1, unique_champions=2, latest=macd_regime" in content
    assert "QQQ: samples=3, switches=1, unique_champions=2, latest=donchian" in content
    assert "alert=watch" in content


def test_build_report_index_symbol_group_champions_tolerates_missing_composite_score(tmp_path):
    pd.DataFrame(
        [
            {"symbol": "ETH", "strategy": "score_regime", "symbol_rank": 1},
            {"symbol": "QQQ", "strategy": "atr_regime", "symbol_rank": 1},
        ]
    ).to_csv(tmp_path / "leaderboard_by_symbol_QQQ_ETH.csv", index=False)

    content = build_report_index(tmp_path)
    assert "分组排行榜（按标的）" in content
    assert "ETH:score_regime(0.0000)" in content
    assert "QQQ:atr_regime(0.0000)" in content


def test_build_report_index_collects_run_config_summary(tmp_path):
    payload = {
        "run_id": "20260315T120000Z",
        "task_count": 3,
        "success_count": 2,
        "failed_count": 1,
        "on_error": "continue",
        "run_duration_ms": 3210.5,
        "results": [
            {"command": "fetch", "duration_ms": 510.0},
            {"command": "portfolio", "duration_ms": 1900.0},
            {"command": "report", "duration_ms": 800.5},
        ],
    }
    (tmp_path / "run_config_batch_summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "批处理执行摘要" in content
    assert "run_config_batch_summary.json" in content
    assert "run_id=20260315T120000Z" in content
    assert "duration=3.21s" in content
    assert "slowest=portfolio(1900.0ms)" in content


def test_build_report_index_collects_run_config_symbol_group_champions(tmp_path):
    payload = {
        "run_id": "20260315T120000Z",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 1200.0,
        "symbol_group_champions": [
            {
                "task_index": 1,
                "command": "compare",
                "status": "success",
                "champion_count": 2,
                "champions": [
                    {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.81},
                    {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.77},
                ],
            }
        ],
        "results": [
            {"command": "compare", "status": "success", "duration_ms": 1200.0},
        ],
    }
    (tmp_path / "run_config_batch_summary.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "compare_task#1 champions=ETH:score_regime(0.8100), QQQ:atr_regime(0.7700)" in content


def test_build_report_index_collects_gzip_run_config_summary(tmp_path):
    payload = {
        "run_id": "20260315T120000Z",
        "task_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 2100.0,
        "results": [
            {"command": "fetch", "status": "success", "duration_ms": 800.0},
            {"command": "report", "status": "success", "duration_ms": 1300.0},
        ],
    }
    with gzip.open(tmp_path / "run_config_batch_summary.json.gz", "wt", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False)

    content = build_report_index(tmp_path)
    assert "批处理执行摘要" in content
    assert "run_config_batch_summary.json.gz" in content
    assert "run_id=20260315T120000Z" in content


def test_build_report_index_collects_failed_top_commands(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 2,
        "success_count": 0,
        "failed_count": 2,
        "on_error": "continue",
        "run_duration_ms": 1200.0,
        "results": [
            {"command": "fetch", "status": "failed", "duration_ms": 500.0},
            {"command": "portfolio", "status": "failed", "duration_ms": 700.0},
        ],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 2,
        "success_count": 1,
        "failed_count": 1,
        "on_error": "continue",
        "run_duration_ms": 900.0,
        "results": [
            {"command": "fetch", "status": "failed", "duration_ms": 300.0},
            {"command": "report", "status": "success", "duration_ms": 600.0},
        ],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "failed_top_commands: fetch:2, portfolio:1" in content


def test_build_report_index_collects_run_config_aggregate_all_and_recent(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 1000.0,
        "run_ended_at": "2026-03-15T10:00:00Z",
        "results": [
            {"command": "fetch", "status": "success", "duration_ms": 400.0},
            {"command": "report", "status": "success", "duration_ms": 600.0},
        ],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 2,
        "success_count": 1,
        "failed_count": 1,
        "on_error": "continue",
        "run_duration_ms": 3000.0,
        "run_ended_at": "2026-03-15T11:00:00Z",
        "results": [
            {"command": "fetch", "status": "failed", "duration_ms": 1200.0},
            {"command": "report", "status": "success", "duration_ms": 1800.0},
        ],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "aggregate_all_runs: run_fail_rate=0.5000" in content
    assert "task_fail_rate=0.2500" in content
    assert "aggregate_last_2_runs: run_fail_rate=0.5000" in content


def test_build_report_index_collects_run_config_champion_switch_trend(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 1000.0,
        "run_ended_at": "2026-03-15T10:00:00Z",
        "symbol_group_champions": [
            {
                "task_index": 1,
                "command": "compare",
                "status": "success",
                "champion_count": 2,
                "champions": [
                    {"symbol": "ETH", "strategy": "score_regime", "composite_score": 0.81},
                    {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.77},
                ],
            }
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 1000.0}],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 900.0,
        "run_ended_at": "2026-03-15T12:00:00Z",
        "symbol_group_champions": [
            {
                "task_index": 1,
                "command": "compare",
                "status": "success",
                "champion_count": 2,
                "champions": [
                    {"symbol": "ETH", "strategy": "macd_regime", "composite_score": 0.83},
                    {"symbol": "QQQ", "strategy": "atr_regime", "composite_score": 0.79},
                ],
            }
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 900.0}],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "champion_switch_last_2_runs:" in content
    assert "ETH(samples=2,switches=1,unique=2,latest=macd_regime)" in content
    assert "QQQ(samples=2,switches=0,unique=1,latest=atr_regime)" in content
    assert "[alert=watch]" in content


def test_build_report_index_champion_switch_alert_threshold_override(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_ended_at": "2026-03-15T10:00:00Z",
        "symbol_group_champions": [
            {
                "task_index": 1,
                "command": "compare",
                "status": "success",
                "champions": [{"symbol": "ETH", "strategy": "score_regime"}],
            }
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 1000.0}],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_ended_at": "2026-03-15T12:00:00Z",
        "symbol_group_champions": [
            {
                "task_index": 1,
                "command": "compare",
                "status": "success",
                "champions": [{"symbol": "ETH", "strategy": "macd_regime"}],
            }
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 900.0}],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(
        tmp_path,
        champion_switch_watch_threshold=2,
        champion_switch_high_threshold=3,
        champion_switch_recent_runs=2,
    )
    assert "ETH(samples=2,switches=1,unique=2,latest=macd_regime)[alert=none]" in content


def test_export_champion_switch_trend_csv(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_ended_at": "2026-03-15T10:00:00Z",
        "symbol_group_champions": [
            {"task_index": 1, "command": "compare", "status": "success", "champions": [{"symbol": "ETH", "strategy": "score_regime"}]}
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 1000.0}],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "on_error": "continue",
        "run_ended_at": "2026-03-15T12:00:00Z",
        "symbol_group_champions": [
            {"task_index": 1, "command": "compare", "status": "success", "champions": [{"symbol": "ETH", "strategy": "macd_regime"}]}
        ],
        "results": [{"command": "compare", "status": "success", "duration_ms": 900.0}],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    out = export_champion_switch_trend_csv(
        tmp_path,
        output_file="trend/champion_switch.csv",
        recent_runs=2,
        watch_threshold=1,
        high_threshold=2,
    )
    assert out is not None
    assert out.name == "champion_switch.csv"
    df = pd.read_csv(out)
    assert list(df["symbol"]) == ["ETH"]
    assert int(df.iloc[0]["switches"]) == 1
    assert str(df.iloc[0]["alert_level"]) == "watch"
    assert str(df.iloc[0]["first_run_time"]).startswith("2026-03-15T10:00:00")
    assert str(df.iloc[0]["latest_run_time"]).startswith("2026-03-15T12:00:00")


def test_build_report_index_collects_run_summary_aggregate(tmp_path):
    payload_a = {
        "run_id": "run_a",
        "task_count": 3,
        "success_count": 2,
        "failed_count": 1,
        "on_error": "continue",
        "run_duration_ms": 1000.0,
        "run_ended_at": "2026-03-15T12:00:00Z",
        "results": [{"command": "fetch", "status": "failed", "duration_ms": 500.0}],
    }
    payload_b = {
        "run_id": "run_b",
        "task_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "on_error": "continue",
        "run_duration_ms": 3000.0,
        "run_ended_at": "2026-03-15T12:10:00Z",
        "results": [{"command": "report", "status": "success", "duration_ms": 800.0}],
    }
    (tmp_path / "run_config_batch_summary_a.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "run_config_batch_summary_b.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "aggregate_last_2_runs: run_fail_rate=0.5000, task_fail_rate=0.2000" in content
    assert "avg_duration=2.00s" in content


def test_build_report_index_collects_retry_efficiency_aggregate(tmp_path):
    payload = {
        "run_id": "run_retry",
        "task_count": 3,
        "success_count": 1,
        "failed_count": 2,
        "on_error": "continue",
        "run_duration_ms": 1800.0,
        "results": [
            {
                "command": "fetch",
                "status": "success",
                "attempts": 3,
                "retries_used": 2,
                "retry_retryable_only": True,
                "retry_count": 2,
            },
            {
                "command": "report",
                "status": "failed",
                "attempts": 1,
                "retries_used": 0,
                "retry_retryable_only": True,
                "retry_count": 2,
            },
            {
                "command": "portfolio",
                "status": "failed",
                "attempts": 2,
                "retries_used": 1,
                "retry_retryable_only": False,
                "retry_count": 2,
            },
        ],
    }
    (tmp_path / "run_config_batch_summary_retry.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    content = build_report_index(tmp_path)
    assert "retry_hit_rate=0.5000" in content
    assert "total_retries_used=3" in content
    assert "non_retryable_fail_share=0.5000" in content


def test_build_report_index_collects_preset_compare_summary(tmp_path):
    preset_dir = tmp_path / "preset_compare"
    preset_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "preset": "conservative",
                "total_return": 0.10,
                "sharpe": 1.00,
                "calmar": 0.80,
                "max_drawdown": -0.20,
                "avg_exposure": 0.40,
                "avg_margin_util": 0.25,
                "peak_margin_util": 0.50,
                "avg_reserve_cash_ratio": 0.20,
                "failed_count": 0,
                "run_duration_ms": 1200.0,
            },
            {
                "preset": "aggressive",
                "total_return": 0.16,
                "sharpe": 1.30,
                "calmar": 1.00,
                "max_drawdown": -0.26,
                "avg_exposure": 0.55,
                "avg_margin_util": 0.35,
                "peak_margin_util": 0.66,
                "avg_reserve_cash_ratio": 0.12,
                "failed_count": 1,
                "run_duration_ms": 1500.0,
            },
        ]
    ).to_csv(preset_dir / "preset_compare.csv", index=False)

    content = build_report_index(tmp_path)
    assert "预设对比摘要" in content
    assert "preset_compare/preset_compare.csv" in content
    assert "aggressive_minus_conservative.total_return=0.0600" in content
    assert "aggressive_minus_conservative.failed_count=1.0000" in content


def test_build_report_index_collects_retry_budget_trace_summary_aggregate(tmp_path):
    pd.DataFrame(
        [
            {
                "run_id": "run_a",
                "index": 1,
                "command": "fetch",
                "status": "success",
                "attempts": 2,
                "retries_used": 1,
                "budget_before": 3,
                "budget_after": 2,
            },
            {
                "run_id": "run_a",
                "index": 2,
                "command": "portfolio",
                "status": "failed",
                "attempts": 3,
                "retries_used": 2,
                "budget_before": 2,
                "budget_after": 0,
            },
        ]
    ).to_csv(tmp_path / "run_config_retry_budget_trace.csv", index=False)

    content = build_report_index(tmp_path)
    assert "重试预算轨迹" in content
    assert "run_config_retry_budget_trace.csv" in content
    assert "depleted_events=1" in content
    assert "failed_rows=1" in content
    assert "depleted_failed=1" in content
    assert "aggregate: files=1, rows=2" in content


def test_build_report_index_collects_preset_compare_history(tmp_path):
    preset_dir = tmp_path / "preset_compare"
    preset_dir.mkdir(parents=True, exist_ok=True)

    latest_df = pd.DataFrame(
        [
            {"preset": "conservative", "total_return": 0.10},
            {"preset": "aggressive", "total_return": 0.18},
        ]
    )
    prev_df = pd.DataFrame(
        [
            {"preset": "conservative", "total_return": 0.11},
            {"preset": "aggressive", "total_return": 0.16},
        ]
    )
    latest_df.to_csv(preset_dir / "preset_compare.csv", index=False)
    prev_df.to_csv(preset_dir / "preset_compare_20260315T120000Z.csv", index=False)
    latest_df.to_csv(preset_dir / "preset_compare_20260315T130000Z.csv", index=False)

    content = build_report_index(tmp_path)
    assert "history.latest_snapshot=`preset_compare_20260315T130000Z.csv`, total_return_gap=0.0800" in content
    assert "history.prev_snapshot=`preset_compare_20260315T120000Z.csv`, total_return_gap=0.0500, delta=0.0300" in content
    assert "history.aggregate_last_2_snapshots: avg_gap=0.0650, min_gap=0.0500, max_gap=0.0800" in content


def test_build_report_index_collects_preset_cleanup_summary(tmp_path):
    preset_dir = tmp_path / "preset_compare"
    preset_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"preset": "conservative", "total_return": 0.10},
            {"preset": "aggressive", "total_return": 0.16},
        ]
    ).to_csv(preset_dir / "preset_compare.csv", index=False)
    (preset_dir / "preset_compare_cleanup_latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-15T20:40:00+00:00",
                "before_count": 8,
                "after_count": 5,
                "removed_by_date_range": 2,
                "removed_by_count": 1,
                "keep_snapshot_count": 20,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    content = build_report_index(tmp_path)
    assert "cleanup.latest: generated_at=2026-03-15T20:40:00+00:00, before=8, after=5, removed_by_date_range=2, removed_by_count=1, keep_snapshot_count=20" in content


def test_build_report_index_collects_preset_cleanup_trend(tmp_path):
    preset_dir = tmp_path / "preset_compare"
    preset_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"preset": "conservative", "total_return": 0.10},
            {"preset": "aggressive", "total_return": 0.16},
        ]
    ).to_csv(preset_dir / "preset_compare.csv", index=False)
    (preset_dir / "preset_compare_cleanup_latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-15T20:40:00+00:00",
                "before_count": 8,
                "after_count": 5,
                "removed_by_date_range": 2,
                "removed_by_count": 1,
                "keep_snapshot_count": 20,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (preset_dir / "preset_compare_cleanup_20260315T190000Z.json").write_text(
        json.dumps({"generated_at": "2026-03-15T19:00:00+00:00", "removed_by_date_range": 1, "removed_by_count": 0}),
        encoding="utf-8",
    )
    (preset_dir / "preset_compare_cleanup_20260315T200000Z.json").write_text(
        json.dumps({"generated_at": "2026-03-15T20:00:00+00:00", "removed_by_date_range": 1, "removed_by_count": 2}),
        encoding="utf-8",
    )

    content = build_report_index(tmp_path)
    assert "cleanup.aggregate_last_2_runs: first_generated_at=2026-03-15T19:00:00+00:00" in content
    assert "latest_generated_at=2026-03-15T20:00:00+00:00" in content
    assert "history_files=2, valid_runs=2" in content
    assert "avg_removed_total=2.00" in content
    assert "max_removed_total=3" in content
    assert "skipped_invalid_time=0" in content
    assert "rows_with_invalid_numeric=0" in content
    assert "abnormal_ratio=0.0000" in content


def test_build_report_index_tolerates_invalid_preset_cleanup_history_rows(tmp_path):
    preset_dir = tmp_path / "preset_compare"
    preset_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"preset": "conservative", "total_return": 0.10},
            {"preset": "aggressive", "total_return": 0.16},
        ]
    ).to_csv(preset_dir / "preset_compare.csv", index=False)
    (preset_dir / "preset_compare_cleanup_latest.json").write_text(
        json.dumps(
            {
                "generated_at": "bad-time",
                "before_count": "oops",
                "after_count": None,
                "removed_by_date_range": "x",
                "removed_by_count": "y",
                "keep_snapshot_count": "N/A",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (preset_dir / "preset_compare_cleanup_20260315T190000Z.json").write_text(
        json.dumps({"generated_at": "invalid", "removed_by_date_range": "foo", "removed_by_count": "bar"}),
        encoding="utf-8",
    )
    (preset_dir / "preset_compare_cleanup_20260315T200000Z.json").write_text(
        json.dumps({"generated_at": "2026-03-15T20:00:00+00:00", "removed_by_date_range": "3", "removed_by_count": "bad"}),
        encoding="utf-8",
    )

    content = build_report_index(tmp_path)
    assert "cleanup.latest: generated_at=bad-time, before=0, after=0, removed_by_date_range=0, removed_by_count=0, keep_snapshot_count=0" in content
    assert "cleanup.aggregate_last_1_runs: first_generated_at=2026-03-15T20:00:00+00:00" in content
    assert "history_files=2, valid_runs=1" in content
    assert "avg_removed_total=3.00" in content
    assert "max_removed_total=3" in content
    assert "skipped_invalid_time=1" in content
    assert "rows_with_invalid_numeric=1" in content
    assert "abnormal_ratio=1.0000" in content


def test_build_report_index_collects_retry_budget_trace_summary(tmp_path):
    pd.DataFrame(
        [
            {"task_index": 0, "command": "fetch", "budget_before": 3, "budget_after": 2, "retries_used": 1},
            {"task_index": 1, "command": "portfolio", "budget_before": 2, "budget_after": 0, "retries_used": 2},
            {"task_index": 2, "command": "report", "budget_before": 0, "budget_after": 0, "retries_used": 0},
        ]
    ).to_csv(tmp_path / "run_config_retry_budget_trace.csv", index=False)

    content = build_report_index(tmp_path)
    assert "重试预算轨迹" in content
    assert "run_config_retry_budget_trace.csv" in content
    assert "depleted_events=1" in content
    assert "depleted_top_commands=portfolio:1" in content
    assert "aggregate: files=1, rows=3, depleted_events=1" in content
    assert "aggregate_depleted_top_commands: portfolio:1" in content


def test_build_report_index_collects_gzip_retry_budget_trace_summary(tmp_path):
    pd.DataFrame(
        [
            {"task_index": 0, "command": "fetch", "budget_before": 2, "budget_after": 1, "retries_used": 1},
            {"task_index": 1, "command": "report", "budget_before": 1, "budget_after": 1, "retries_used": 0},
        ]
    ).to_csv(tmp_path / "run_config_retry_budget_trace.csv.gz", index=False, compression="gzip")

    content = build_report_index(tmp_path)
    assert "重试预算轨迹" in content
    assert "run_config_retry_budget_trace.csv.gz" in content
    assert "depleted_events=0" in content


def test_build_report_index_collects_retry_budget_trend_last_runs(tmp_path):
    pd.DataFrame(
        [
            {
                "run_id": "20260315T090000Z",
                "index": 1,
                "command": "fetch",
                "status": "success",
                "attempts": 1,
                "retries_used": 0,
                "budget_before": 2,
                "budget_after": 2,
            },
            {
                "run_id": "20260315T090000Z",
                "index": 2,
                "command": "portfolio",
                "status": "success",
                "attempts": 2,
                "retries_used": 1,
                "budget_before": 2,
                "budget_after": 1,
            },
        ]
    ).to_csv(tmp_path / "run_config_retry_budget_trace_a.csv", index=False)
    pd.DataFrame(
        [
            {
                "run_id": "20260315T100000Z",
                "index": 1,
                "command": "fetch",
                "status": "failed",
                "attempts": 3,
                "retries_used": 2,
                "budget_before": 2,
                "budget_after": 0,
            },
            {
                "run_id": "20260315T100000Z",
                "index": 2,
                "command": "report",
                "status": "success",
                "attempts": 1,
                "retries_used": 0,
                "budget_before": 0,
                "budget_after": 0,
            },
            {
                "run_id": "20260315T110000Z",
                "index": 1,
                "command": "fetch",
                "status": "success",
                "attempts": 2,
                "retries_used": 1,
                "budget_before": 1,
                "budget_after": 0,
            },
        ]
    ).to_csv(tmp_path / "run_config_retry_budget_trace_b.csv", index=False)

    content = build_report_index(tmp_path)
    assert "aggregate_last_3_runs: depleted_run_rate=0.6667" in content
    assert "avg_depleted_rate=0.5000" in content
    assert "avg_failed_ratio=0.1667" in content
