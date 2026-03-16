# 批处理预设对比说明（保守 vs 激进）

本文用于说明两套一体化批处理模板的参数取向和复盘口径：

- 保守模板：`examples/config.batch.portfolio_conservative.json`
- 激进模板：`examples/config.batch.portfolio_aggressive.json`

## 运行方式

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.portfolio_conservative.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.portfolio_aggressive.json
```

主要输出：

- 批处理摘要：`outputs/batch_conservative_summary.json/csv`、`outputs/batch_aggressive_summary.json/csv`
- 报告文件：`outputs/report_index_conservative.md`、`outputs/report_index_aggressive.md`
- 组合指标：`outputs/portfolio_metrics_*.json`
- 组合模拟资金快照：`outputs/sim_portfolio_capital_*.csv`

一键执行并产出对比表：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py
```

临时覆盖日期区间（同时覆盖两套预设的 `vars.start/end`）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py \
  --start 2018-01-01 \
  --end 2025-12-31
```

仅复用现有工件（不重跑批处理）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py --no-run
```

对比输出：`outputs/preset_compare/preset_compare.csv` 与 `outputs/preset_compare/preset_compare.md`。
历史快照 `preset_compare_<timestamp>.csv` 默认仅保留最近 20 份，可通过 `--keep-snapshots N` 调整（`0` 表示不清理）。
可使用 `--cleanup-only` 仅执行快照清理与诊断落盘（`preset_compare_cleanup_latest.json`），不生成新的对比表。
也可通过 `--snapshot-keep-start/--snapshot-keep-end` 按时间窗口清理快照（支持 `YYYY-MM-DD` 或 `YYYYMMDDTHHMMSSZ`）。
清理诊断历史 `preset_compare_cleanup_<timestamp>.json` 默认仅保留最近 50 份，可通过 `--keep-cleanup-history N` 调整。

## strict 失败演示与复盘清单

用于验证 `compress_naming=strict` 下的失败链路与报告汇总是否可用：

```bash
PYTHONPATH=src python3 scripts/demo_strict_failure_report.py
```

该脚本会执行：

1. 运行 `examples/config.batch.strict_failure_demo.json`（包含一个故意失败任务）。
2. 在批处理失败后继续生成报告索引。
3. 打印关键工件路径，便于快速核对。

复盘 checklist（建议按顺序核对）：

1. 终端应出现 `run-config returncode:` 且返回码为非 `0`（默认预期失败）。
2. `outputs/strict_failure_summary.json.gz` 存在，且 `failed_count >= 1`。
3. `outputs/strict_failure_summary.csv.gz` 存在，且包含失败任务行（`status=failed`）。
4. `outputs/strict_failure_retry_trace.csv.gz` 存在（若配置启用了重试预算轨迹）。
5. `outputs/strict_failure_demo_report.md`（或自定义 `--report-file`）存在，且包含批处理摘要段落。
6. 若第 2-5 任一步骤缺失，优先检查 strict 命名路径是否都显式以 `.gz` 结尾。

## 参数差异

- 保守：更低仓位、更高现金保留、更低杠杆、更严格回撤阈值。
- 激进：更高仓位、更低现金保留、允许杠杆、更积极再平衡。

## 建议对比指标

优先比较以下指标：

1. 收益风险：
   - `total_return`
   - `sharpe`
   - `max_drawdown`
2. 资金占用：
   - 平均暴露率（`avg_exposure`）
   - 平均/峰值保证金利用率（`avg_margin_util` / `peak_margin_util`）
   - 平均预留现金占比（`avg_reserve_cash_ratio`）
3. 执行稳定性：
   - 批处理失败任务数（`failed_count`）
   - 批处理总耗时（`run_duration_ms`）
   - 最慢任务（`slowest`）

## 解读建议

1. 若激进模板在 `total_return` 提升有限但 `max_drawdown` 与 `peak_margin_util` 显著上升，优先保守模板。
2. 若激进模板在 `sharpe` 与 `calmar` 同时改善，且失败率不升高，可考虑作为主实验线路。
3. 当两者收益接近时，优先选择失败率更低、耗时更稳定的一档，便于自动化回归与持续运行。
