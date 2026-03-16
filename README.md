# 市场信号系统（Market Signal System）

本项目是一个本地可运行的中长线行情研究、回测与模拟交易系统，覆盖：
- `QQQ`（美股 ETF，优先 Yahoo，失败自动回退 Stooq）
- `ETH`（优先 Binance `ETHUSDT`，失败自动回退 Yahoo `ETH-USD`，再回退 CoinGecko `ethereum`）

当前实现遵循 MVP 优先：先打通 `数据接入 -> 策略 -> 回测 -> 模拟交易 -> 持久化`，再逐步增强。

Signal Pilot 独立文档：[`SIGNAL_PILOT.md`](SIGNAL_PILOT.md)  
多账号存储设计：[`STORAGE.md`](STORAGE.md)
Web 登录设计文档：[`docs/WEB_LOGIN_MVP_DESIGN.md`](docs/WEB_LOGIN_MVP_DESIGN.md)

`appdb` 已提供 PostgreSQL 迁移占位类（`Postgres*`），当前仅定义接口与错误提示，生产仍默认 SQLite。

## 功能清单

- 统一数据接入层：统一 OHLCV 抽象、历史拉取、增量更新、本地缓存、UTC 时区标准化、免费源多级回退（QQQ: Yahoo->Stooq，ETH: Binance->Yahoo->CoinGecko）
- 多标的共同时间轴对齐：`DataManager.get_aligned_history()` 统一裁剪组合研究/模拟的公共区间
- 周频支持：`--interval 1wk` 采用“日线拉取 + 本地重采样（W-FRI）”，避免依赖外部周线口径差异
- 数据质量诊断：缺失值、异常价格、OHLC 边界、时间跳点检测与异常行导出
- 基础回测引擎：支持多空/空仓、手续费/滑点、净值与关键指标输出
- 首批中长线策略（至少 3 个，当前内置 8 个）：
  - `ma_cross`（均线趋势）
  - `donchian`（通道突破）
  - `momentum`（中周期动量 + 波动率过滤）
  - `regime`（动量 + 长周期趋势过滤 + 波动率过滤）
  - `macd_regime`（MACD 趋势确认 + regime/波动率过滤）
  - `atr_regime`（ATR 归一化趋势强度 + 波动率分位过滤）
  - `score_regime`（多指标加权评分 + 波动率过滤）
  - `dual_momentum`（双周期动量共振 + 趋势/波动率过滤）
- 模拟交易核心：开仓/平仓、持仓、浮盈、已实现收益、累计收益、状态持久化恢复
- 模拟资金曲线：单标的 `simulate` 自动导出逐 bar `sim_equity_*.csv`，报告可汇总收益/回撤
- 组合账户模拟：`simulate-portfolio` 支持多标的共享资金账户
- CLI：`fetch` / `backtest` / `simulate`
- 研究增强：参数网格搜索 + walk-forward 滚动窗口稳健性评估
- 多策略排行榜：跨标的批量回测，导出综合评分榜单
- 配置驱动执行：`run-config` 从 JSON/YAML 文件复用研究任务
- 组合资金分配：支持 `equal` / `risk_parity` / `vol_target` / `cov_risk_parity` / `cov_vol_target`
- 组合归因导出：输出标的收益贡献、波动贡献、换手贡献
- 组合告警导出：相关性与拥挤度（`watch/high` 两级）
- 参数稳定性分析：基于 walk-forward 明细输出参数频次与稳定性摘要
- 基础测试：策略输出、指标计算、模拟交易核心

## 环境要求

- Python 3.10+

## 安装

```bash
python3 -m pip install -r requirements-dev.txt
```

推荐使用项目自带初始化脚本（支持 `pyproject + requirements` 双路径）：

```bash
python3 scripts/bootstrap_project.py --dev --mode hybrid
source .venv/bin/activate
```

仅使用 `pyproject`（editable）：

```bash
python3 scripts/bootstrap_project.py --dev --mode pyproject
```

校验 `pyproject.toml` 与 `requirements*.txt` 依赖是否一致：

```bash
python3 scripts/bootstrap_project.py --check-sync
```

压缩 `STATUS.md/DECISIONS.md` 并归档历史（默认 dry-run）：

```bash
python3 scripts/compact_project_docs.py --keep-sections 8
python3 scripts/compact_project_docs.py --keep-sections 8 --apply
```

## 推送到 GitHub（当前仓库）

已内置推送脚本（推送前会检查仓库是否 clean）：

```bash
./scripts/push_github.sh
```

若使用 PAT，可直接：

```bash
GITHUB_TOKEN=你的令牌 ./scripts/push_github.sh
```

## Web 登录 MVP（预置账号）

1) 预置账号（后台脚本）：

```bash
python3 scripts/admin_seed_account.py \
  --account-id acct_demo \
  --username demo \
  --password 'demo123456' \
  --display-name 'Demo User'
```

2) 启动 Web：

```bash
python3 scripts/run_web.py --host 0.0.0.0 --port 8080
```

可选登录限流参数（默认 5 次失败 / 300 秒窗口）：

```bash
python3 scripts/run_web.py \
  --login-rate-limit-max-attempts 5 \
  --login-rate-limit-window-seconds 300
```

3) 浏览器访问：
- `http://127.0.0.1:8080/login`
- 登录后进入 `/signal-pilot`，仅显示当前账号下的 Signal Pilot 数据。
- 登录与退出已启用 CSRF 校验（表单内置 token）。
- 登录态 API：
  - `GET /api/me`：返回当前登录账号（未登录返回 `401`）
  - `GET /api/signal-pilot/alerts`：返回当前账号的 Signal Pilot 告警数据（按 `account_id` 隔离）

### Web 部署模板（systemd + Nginx）
- 环境变量样例：`.env.web.example`
- systemd 样例：`deploy/systemd/mss-web.service.example`
- Nginx 反代样例：`deploy/nginx/mss-web.nginx.conf.example`

## 快速开始

### 0) 一键跑通 MVP（推荐）

```bash
PYTHONPATH=src python3 -m market_signal_system mvp \
  --start 2020-01-01 \
  --end 2025-01-01
```

或使用配置模板：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.mvp.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.mvp.yaml
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.mvp_daily.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.mvp_daily.yaml
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.refresh_mvp_daily.json
```

输出：
- `outputs/mvp_summary_<run_tag>.json`
- `outputs/mvp_metrics_*` / `outputs/mvp_equity_*` / `outputs/mvp_trades_*` / `outputs/mvp_signals_*`
- `outputs/mvp_sim_signals_*` / `outputs/mvp_sim_trades_*` / `outputs/mvp_sim_equity_*`
- `mvp_summary` 内含 `backtest_topn_by_symbol`（每标的 Top3）与 `backtest_topn_overall`（全局 Top5）
- `mvp_summary` 内含 `mvp_acceptance`（MVP 最低标准验收检查结果）

如需在不达标时直接失败（便于 CI / 批处理守门），可开启严格模式：

```bash
PYTHONPATH=src python3 -m market_signal_system mvp \
  --start 2020-01-01 \
  --end 2025-01-01 \
  --strict-acceptance
```

将 `mvp_summary` 生成分组排行榜与简报：

```bash
python3 scripts/mvp_report.py
```

离线烟雾验证（不依赖外网，快速验证 `回测 + 策略 + 模拟交易` 主链路）：

```bash
python3 scripts/mvp_offline_smoke.py --bars 300
```

### 1) 拉取行情（QQQ / ETH）

```bash
PYTHONPATH=src python3 -m market_signal_system fetch --symbol QQQ --start 2024-01-01 --end 2024-03-01
PYTHONPATH=src python3 -m market_signal_system fetch --symbol ETH --start 2024-01-01 --end 2024-03-01
```

增量更新本地缓存（显式命令，支持多标的）：

```bash
PYTHONPATH=src python3 -m market_signal_system update-cache \
  --symbols QQQ,ETH \
  --start 2020-01-01 \
  --end 2025-01-01
```

周频（中长线常用）示例：

```bash
PYTHONPATH=src python3 -m market_signal_system fetch --symbol QQQ --interval 1wk --start 2020-01-01 --end 2025-01-01
```

周频多策略对比可用一键脚本（自动渲染 `config.compare.weekly.json` 并执行）：

```bash
python3 scripts/run_compare_weekly.py --start 2020-01-01 --end 2025-01-01
```

### 1.5) 诊断数据质量（缺失值/异常价格/跳点）

```bash
PYTHONPATH=src python3 -m market_signal_system diagnose-data \
  --symbol QQQ \
  --start 2020-01-01 \
  --end 2025-01-01
```

输出：
- `outputs/data_quality_<symbol>_<interval>.json`
- 若存在异常行：`outputs/data_quality_anomalies_<symbol>_<interval>.csv`

### 2) 回测

```bash
PYTHONPATH=src python3 -m market_signal_system backtest \
  --symbol QQQ \
  --strategy ma_cross \
  --start 2020-01-01 \
  --end 2025-01-01
```

支持策略参数注入（JSON）：

```bash
PYTHONPATH=src python3 -m market_signal_system backtest \
  --symbol QQQ \
  --strategy ma_cross \
  --params '{"fast_window":40,"slow_window":180}' \
  --start 2020-01-01 \
  --end 2025-01-01
```

支持可选回测风控（最大回撤保护）：

```bash
PYTHONPATH=src python3 -m market_signal_system backtest \
  --symbol QQQ \
  --strategy donchian \
  --start 2020-01-01 \
  --end 2025-01-01 \
  --max-drawdown 0.2 \
  --cooldown-bars 20
```

输出：
- `outputs/metrics_<symbol>_<strategy>.json`
- `outputs/equity_<symbol>_<strategy>.csv`
- `outputs/trades_<symbol>_<strategy>.csv`
- `outputs/signals_<symbol>_<strategy>.csv`（含每根 bar 的信号原因）

`metrics_*.json` 默认包含策略指标，并附带同标的买入持有基准对比字段（如 `benchmark_total_return`、`excess_total_return`、`information_ratio`）。

### 3) 模拟交易（历史驱动）

```bash
PYTHONPATH=src python3 -m market_signal_system simulate \
  --symbol ETH \
  --strategy momentum \
  --start 2022-01-01 \
  --end 2025-01-01 \
  --state-file eth_paper.json
```

同策略多参数并行实验可追加输出标签，避免工件被覆盖：

```bash
PYTHONPATH=src python3 -m market_signal_system simulate \
  --symbol ETH \
  --strategy momentum \
  --params '{"lookback":63}' \
  --start 2022-01-01 \
  --end 2025-01-01 \
  --output-tag lb63
```

按权益比例自动计算下单数量（中长线仓位管理）：

```bash
PYTHONPATH=src python3 -m market_signal_system simulate \
  --symbol ETH \
  --strategy momentum \
  --allocation-per-signal 0.2 \
  --min-quantity 0.01 \
  --start 2022-01-01 \
  --end 2025-01-01 \
  --state-file eth_alloc_paper.json
```

多标的共享账户模拟：

```bash
PYTHONPATH=src python3 -m market_signal_system simulate-portfolio \
  --symbols QQQ,ETH \
  --strategy momentum \
  --output-tag base_case \
  --allocation-per-signal 0.3 \
  --max-symbol-allocation 0.4 \
  --max-total-allocation 1.0 \
  --initial-margin-rate 1.0 \
  --cash-reserve-ratio 0.05 \
  --max-portfolio-drawdown 0.2 \
  --risk-cooldown-bars 20 \
  --start 2022-01-01 \
  --end 2025-01-01 \
  --state-file paper_portfolio.json
```

`simulate` 恢复链路可用离线冒烟脚本一键验证（自动构造本地缓存、连续两段运行并校验交易条数递增）：

```bash
python3 scripts/smoke_simulate_resume.py
```

`simulate` 对同一 `state-file + symbol` 新增幂等恢复保护：若重跑覆盖已处理时间区间，会自动跳过重复 bar，避免重复开平仓与重复记账。

`simulate-portfolio` 同样支持幂等恢复：重跑同一 `state-file + symbols` 时间窗口时会跳过重复 bar，并在 `sim_portfolio_summary` 中输出本次增量审计字段。

恢复执行最佳实践：
- 同一策略连续运行时复用同一个 `state-file`，通过分段 `start/end` 续跑。
- 对并行实验使用不同 `state-file`（或不同 `account-id`）隔离状态。
- 回放验证优先查看 `sim_summary` / `sim_portfolio_summary` 中的 `skipped_duplicate_bars_*` 字段。

`simulate` 输出文件：
- `outputs/sim_signals_<symbol>_<strategy>.csv`
- `outputs/sim_trades_<symbol>_<strategy>.csv`（若有成交）
- `outputs/sim_equity_<symbol>_<strategy>.csv`（逐 bar 资金曲线，含持仓快照列：`position_side/position_quantity/position_entry_price/position_mark_price/position_unrealized_pnl`）
- `outputs/sim_summary_<symbol>_<strategy>.json`（结构化快照：持仓/浮盈/已实现/累计收益）
  - 快照附带恢复幂等审计字段：`skipped_duplicate_bars_total`、`skipped_duplicate_bars_by_symbol`

### 4) Signal Pilot（信号观察台账）

1) 扫描新信号并写入台账（含去重）：

```bash
PYTHONPATH=src python3 -m market_signal_system scan-alerts \
  --symbols QQQ,ETH \
  --strategy score_regime \
  --interval 1d \
  --account-id default
```

2) 刷新 open alert 的观察收益（可按反向信号关闭/超时过期）：

```bash
PYTHONPATH=src python3 -m market_signal_system update-alerts \
  --max-holding-days 60 \
  --close-on-reverse \
  --account-id default
```

3) 生成 7/30/60 天观察报告（Markdown/CSV/JSON）：

```bash
PYTHONPATH=src python3 -m market_signal_system report-alerts \
  --windows 7,30,60 \
  --account-id default
```

可选：派发本地待通知队列（默认落盘到本地文件；可切换 webhook）：

```bash
PYTHONPATH=src python3 -m market_signal_system dispatch-alerts \
  --queue-file signal_pilot_notifications.jsonl \
  --sink-file signal_pilot_notifications_dispatched.jsonl \
  --account-id default \
  --retry-count 1 \
  --retry-delay-ms 800 \
  --idempotency-window-minutes 30
```

说明：
- `--account-id`：账号命名空间，Signal Pilot 台账/派发记录按账号隔离。
- `--db-file`：可选 SQLite 文件路径（默认 `data/state/market_signal_system.db`）。
- `--retry-count`：Webhook 失败后的最大重试次数（仅重试超时/限流/5xx 等可重试错误）。
- `--retry-delay-ms`：重试间隔毫秒。
- `--idempotency-window-minutes`：幂等窗口，窗口内同一 `alert_id` 若已有派发尝试则跳过，降低重复通知风险。

使用 `run-config` 模板串行执行 `scan -> dispatch -> update -> report`：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.json
```

多账号日常模板（`default/prod/research`）：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.default.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.prod.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.research.json
```

Signal Pilot 默认工件：
- SQLite：`data/state/market_signal_system.db`
- 台账 CSV 兼容镜像：`data/state/signal_alert_ledger.csv`（非 default 账号为 `signal_alert_ledger.<account_id>.csv`）
- 待通知队列：`outputs/signal_pilot_notifications.jsonl`
- 已派发记录：`outputs/signal_pilot_notifications_dispatched.jsonl`
- 观察报告：`outputs/signal_pilot_alert_report_<ts>.csv/.json/.md`

### 4.5) Baseline Daily 去重摘要（MVP + Signal + Report）

为减少日常巡检时重复阅读成本，可生成统一摘要：

```bash
PYTHONPATH=src python3 -m market_signal_system baseline-summary \
  --output-json baseline_daily_digest.json \
  --output-csv baseline_daily_digest.csv
```

默认会自动选取 `outputs` 下最新的：
- `mvp_summary_*.json`
- `signal_pilot_alert_report_daily_*.json`（若不存在则回退 `signal_pilot_alert_report_*.json`）
- `baseline_daily_report_index.md`（若不存在则回退 `report_index.md`）

并输出：
- `outputs/baseline_daily_digest.json`（结构化摘要）
- `outputs/baseline_daily_digest.csv`（扁平 KPI 表，便于二次消费）

可选：直接在 `baseline-summary` 里启用阈值告警与队列输出（JSONL），用于后续通知派发链路：

```bash
PYTHONPATH=src python3 -m market_signal_system baseline-summary \
  --signal-alert-window-days 30 \
  --signal-min-count 3 \
  --signal-min-win-rate 0.5 \
  --signal-min-avg-return-pct 0.0 \
  --simulation-min-return-pct -0.05 \
  --emit-alert-queue \
  --alert-queue-file baseline_summary_alerts.jsonl
```

说明：
- 告警会写入 `baseline_daily_digest.json` 的 `alerts/alert_rules` 字段。
- 启用 `--emit-alert-queue` 后会输出 `outputs/baseline_summary_alerts.jsonl`，便于接入既有 `dispatch-alerts` 派发流程。

也可直接使用模板：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.baseline.summary.alerts.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.baseline.summary.alerts.yaml
```

如果希望每日链路自动完成“基线批处理 + 告警摘要 + 本地派发记录”，可使用：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.baseline.alerts.daily.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.baseline.alerts.daily.yaml
```

`examples/config.batch.baseline.daily.json` 已默认串联：
`mvp -> scan-alerts -> dispatch-alerts -> update-alerts -> report-alerts -> report -> baseline-summary`。

如需每天自动注入日期并执行，可用脚本：

```bash
python3 scripts/run_baseline_daily.py \
  --start 2021-01-01 \
  --end 2026-03-16 \
  --as-of 2026-03-16
```

仅渲染配置不执行：

```bash
python3 scripts/run_baseline_daily.py --no-run --output-config outputs/baseline_daily_rendered.json
```

### 5) 参数研究与 Walk-Forward

```bash
PYTHONPATH=src python3 -m market_signal_system research \
  --symbol QQQ \
  --strategy donchian \
  --start 2018-01-01 \
  --end 2025-01-01 \
  --train-bars 504 \
  --test-bars 126 \
  --objective sharpe
```

### 6) 多策略对比排行榜

```bash
PYTHONPATH=src python3 -m market_signal_system compare \
  --symbols QQQ,ETH \
  --strategies ma_cross,donchian,momentum,regime,macd_regime,atr_regime,score_regime,dual_momentum \
  --start 2020-01-01 \
  --end 2025-01-01
```

`leaderboard_*.csv` 的综合评分会同时考虑绝对收益与相对买入持有基准的超额收益（`score_excess_return`）。
同时会额外生成 `leaderboard_by_symbol_*.csv`，包含 `symbol_rank` 组内排名，便于同资产内比较策略优劣。

### 7) 配置文件驱动执行

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.backtest.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.update_cache.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.diagnose.qqq.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.backtest.macd_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.backtest.atr_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.backtest.score_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.backtest.dual_momentum.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.research.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.research.macd_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.research.atr_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.research.score_regime.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.research.dual_momentum.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.compare.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.compare.weekly.json
python3 scripts/run_compare_weekly.py
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.portfolio.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.portfolio.loose_alerts.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.portfolio.strict_alerts.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.portfolio.rebalance.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.simulate.allocation.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.simulate_portfolio.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.simulate_portfolio.margin.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.stability.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.report.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.daily.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.daily.strict_gzip.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.daily.strict_gzip_trace.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.portfolio_pipeline.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.portfolio_conservative.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.portfolio_aggressive.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.macd_sensitivity.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.atr_regime_stability.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.score_regime_stability.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.score_vs_macd_compare.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.score_vs_macd_compare.eth.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.output_tag_compare.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.simulate_resume.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.signal_pilot.scan.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.signal_pilot.dispatch.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.signal_pilot.update.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.signal_pilot.report.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.yaml
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.default.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.prod.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.signal_pilot.daily.research.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.baseline.daily.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.baseline.daily.yaml
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.strict_compress.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.mvp_daily.yaml
```

`run-config` 现支持批处理清单（`command: "batch"` + `tasks`），可在一个配置中顺序执行多个任务；`tasks` 每项既可写内联任务对象，也可引用其他配置文件路径（相对路径按批处理配置文件所在目录解析）。
批处理配置支持 `vars` 变量占位符，使用 `${name}` 在 `tasks/summary_json/summary_csv` 中复用统一参数。
若占位符缺变量，或 `vars` 不是 JSON/YAML 对象，解析阶段会直接报错并中断执行。
`run-config` 会对已支持命令做最小 schema 校验：拦截未知字段、缺失必填字段、类型不匹配、非法 `choices` 与常见数值边界错误，尽量在执行前暴露配置问题。
批处理可通过 `on_error` 指定错误策略：`fail_fast`（默认，遇错立即中断）或 `continue`（继续执行并在结尾汇总失败任务）。
批处理支持可选重试参数：`retry_count`（重试次数）与 `retry_delay_ms`（重试间隔毫秒）。
重试开关支持 `retry_enabled`（默认当 `retry_count>0` 时自动开启）与 `retry_retryable_only`（默认 `true`，仅对网络/超时/限流类可重试错误重试）。
可选 `max_total_retries` 可限制整个批处理的总重试预算（跨任务共享），预算耗尽后不再重试。
可选 `retry_budget_trace_csv` 可导出重试预算轨迹（每任务预算前后变化），未显式配置且设置了 `max_total_retries` 时默认写入 `outputs/run_config_retry_budget_trace.csv`。
可选 `retry_budget_trace_compress` 可压缩预算轨迹：`none`（默认）或 `gzip`，开启后输出 `.csv.gz` 工件。
可选 `summary_compress` 可压缩批处理摘要：`none`（默认）或 `gzip`。开启 `gzip` 时，`summary_json/summary_csv` 会输出 `.gz` 工件（未带后缀时自动补齐）。
可选 `compress_naming` 控制压缩输出命名策略：`auto_suffix`（默认，自动补 `.gz`）或 `strict`（要求路径显式以 `.gz` 结尾，否则报错）。
可直接参考 `examples/config.batch.daily.strict_gzip.json` 作为严格命名模式模板。
若同时启用预算轨迹压缩，可参考 `examples/config.batch.daily.strict_gzip_trace.json`（摘要与轨迹均为 strict + `.gz`）。
可直接参考 `examples/config.batch.strict_compress.json` 作为 `compress_naming=strict` 的最小模板。
可在任务级通过 `tasks[].retry` 或 `tasks.file.retry` 覆盖：`enabled/count/delay_ms/retryable_only`。
若错误被判定为非可重试（如配置错误、未知命令），默认不会盲目重试。
批处理还支持执行摘要导出：`summary_json` / `summary_csv`（相对路径默认写入 `outputs/`）。
当 `on_error=continue` 且存在失败任务时，`run-config` 会在执行完全部任务后抛出汇总异常，避免 CI 误判成功。
摘要 JSON 额外包含整次运行的 `run_started_at` / `run_ended_at` / `run_duration_ms`，用于批处理耗时追踪。
任务明细会记录 `attempts` 与 `retries_used`，并在摘要顶层记录 `max_total_retries` 与 `retry_budget_remaining`。
若批处理包含 `compare` 任务，摘要 JSON 还会新增 `symbol_group_champions`（任务级分组冠军快照），并在任务行追加 `symbol_group_champion_count/symbol_group_champions` 便于巡检。
可直接参考 `examples/config.batch.portfolio_template.json`（含 `${tag}` 等占位符）快速复制一体化流水线配置。
`backtest` 支持 `output_tag`，用于同策略多参数批处理时避免 `metrics/equity/trades/signals` 文件互相覆盖。
建议将 `output_tag` 设计为“`symbol + strategy + 关键参数`”结构（例如：`qqq_macd_fast12_slow26_regime150`），便于后续 `report` 与文件系统直接定位参数组合。
可直接参考 `examples/config.batch.output_tag_compare.json`（同一策略三组参数对照 + 自动汇总报告）。
可直接参考 `examples/config.batch.score_vs_macd_compare.json`（同窗下 `score_regime` 与 `macd_regime` 专项对照 + 自动汇总报告）。
可直接参考 `examples/config.batch.score_vs_macd_compare.eth.json`（ETH 默认参数版本，便于跨资产对照复盘）。
可直接参考 `examples/config.batch.score_vs_macd_naming_demo.json`（按 `batch_prefix + symbol + strategy + batch_tag` 统一命名 `output_tag/report`）。
可直接参考 `examples/config.batch.score_vs_macd_naming_demo.eth.json`（ETH 命名演示版本，参数与 ETH 专项模板一致）。
按模板一键执行命名演示：

```bash
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.score_vs_macd_naming_demo.json
PYTHONPATH=src python3 -m market_signal_system run-config --file examples/config.batch.score_vs_macd_naming_demo.eth.json
```
可用一键脚本按标的执行专项模板：

```bash
python3 scripts/run_score_vs_macd.py --symbol qqq
python3 scripts/run_score_vs_macd.py --symbol eth
```

一键切换到命名演示模板（`--naming-demo` 默认只渲染不执行，便于先审阅命名结果）：

```bash
python3 scripts/run_score_vs_macd.py --symbol qqq --naming-demo
python3 scripts/run_score_vs_macd.py --symbol eth --naming-demo --dry-run
```

若确认需要直接执行命名演示模板，可显式加 `--run` 覆盖默认安全模式：

```bash
python3 scripts/run_score_vs_macd.py --symbol qqq --naming-demo --run
```

按命令行覆盖专项模板时间窗（同时覆盖 `vars.start/end`）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --start 2020-01-01 \
  --end 2025-01-01
```

仅生成临时配置并打印命令（不执行批处理）：

```bash
python3 scripts/run_score_vs_macd.py --symbol eth --no-run
```

巡检时直接打印渲染后的批处理配置：

```bash
python3 scripts/run_score_vs_macd.py --symbol qqq --no-run --print-config
```

真实执行时保留临时配置（用于审计留档）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --keep-temp-config
```

覆盖专项报告输出文件名（避免多轮结果互相覆盖）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol eth \
  --report-file score_vs_macd_eth_weekly.md
```

给报告文件名追加统一前缀（适合按批次命名，同样可与 `--report-tag/--report-dir` 叠加）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --report-prefix nightly
```

仅覆盖专项报告输出目录（保留模板文件名，便于按目录分环境归档）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --report-dir outputs/reports/daily
```

给报告文件名自动追加标签后缀（不传值时自动使用 UTC 时间戳）：

```bash
python3 scripts/run_score_vs_macd.py --symbol qqq --report-tag
python3 scripts/run_score_vs_macd.py --symbol eth --report-tag weekly
```

将渲染后的配置写到指定路径（可与 `--no-run` 组合做审计留档）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --start 2020-01-01 \
  --end 2024-12-31 \
  --emit-config outputs/score_vs_macd_custom.json \
  --no-run
```

仅指定输出目录并自动生成标准配置文件名（`score_vs_macd_<symbol>_{ts}.json`）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol eth \
  --emit-config-dir outputs/rendered_configs \
  --no-run
```

给渲染配置文件名追加统一前缀（仅与 `--emit-config-dir` 搭配）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --emit-config-dir outputs/rendered_configs \
  --emit-prefix nightly \
  --no-run
```

给渲染配置文件名追加批次后缀（仅与 `--emit-config-dir` 搭配，可与 `--emit-prefix` 叠加）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol eth \
  --emit-config-dir outputs/rendered_configs \
  --emit-tag weekly \
  --no-run
```

统一目录级渲染配置命名分隔符（默认 `_`，可改为 `-` 等风格）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --emit-config-dir outputs/rendered_configs \
  --emit-prefix nightly \
  --emit-tag weekly \
  --emit-separator - \
  --no-run
```

按模板自定义目录级渲染配置文件名（需包含 `{symbol}` 与 `{ts}`）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --emit-config-dir outputs/rendered_configs \
  --emit-template nightly_{symbol}_{ts}_r2.json \
  --no-run
```

使用 `{ts}` 占位符输出时间戳配置，并自动仅保留最近 N 份（旧文件移动到 `.trash/score_vs_macd_emitted/`）：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol qqq \
  --emit-config outputs/score_vs_macd_{ts}.json \
  --keep-emitted-configs 20 \
  --no-run
```

结合 `--emit-prefix/--emit-tag` 做同目录多专题多批次归档，并保留最近 N 份：

```bash
python3 scripts/run_score_vs_macd.py \
  --symbol eth \
  --emit-config-dir outputs/rendered_configs \
  --emit-prefix nightly \
  --emit-tag weekly \
  --keep-emitted-configs 10 \
  --no-run
```

参数约束：
- `--no-run` 与 `--dry-run` 不能同时使用。
- `--keep-temp-config` 仅适用于真实执行路径，且不能与 `--emit-config` / `--emit-config-dir` 同时使用（渲染配置默认保留文件）。
- `--emit-config` 与 `--emit-config-dir` 不能同时使用。
- `--keep-emitted-configs` 需与 `--emit-config` / `--emit-config-dir` 一起使用；当使用 `--emit-config` 时必须包含 `{ts}`。
- `--emit-prefix` 仅支持与 `--emit-config-dir` 一起使用，且不能为空白字符串。
- `--emit-tag` 仅支持与 `--emit-config-dir` 一起使用，且不能为空白字符串。
- `--emit-template` 仅支持与 `--emit-config-dir` 一起使用，且不能与 `--emit-prefix/--emit-tag/--emit-separator` 同时使用。
- `--emit-template` 必须包含 `{symbol}` 与 `{ts}` 占位符，并且不能包含路径分隔符（`/` 或 `\\`）。
- `--emit-separator` 仅支持与 `--emit-config-dir` 一起使用，且不能为空白字符串。
- `--emit-prefix` / `--emit-tag` 不能包含路径分隔符（`/` 或 `\\`）。
- `--emit-separator` 不能包含路径分隔符（`/` 或 `\\`）。

保守/激进预设的复盘口径可见 [BATCH_PRESETS.md](./BATCH_PRESETS.md)。

一键运行并对比保守/激进预设：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py
```

按命令行覆盖回测区间（同时覆盖两套预设的 `vars.start/end`）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py \
  --start 2018-01-01 \
  --end 2025-12-31
```

仅基于已有工件生成对比（不重新执行批处理）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py --no-run
```

仅清理历史快照并落盘清理统计（不生成新的对比表）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py \
  --cleanup-only \
  --keep-snapshots 20 \
  --snapshot-keep-start 2026-03-01 \
  --snapshot-keep-end 2026-03-31
```

控制历史快照保留数量（默认保留最近 20 份；`0` 表示不清理）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py --keep-snapshots 30
```

按快照时间窗口清理历史（仅保留区间内快照；支持 `YYYY-MM-DD` 或 `YYYYMMDDTHHMMSSZ`）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py \
  --snapshot-keep-start 2026-03-01 \
  --snapshot-keep-end 2026-03-31
```

控制清理诊断历史保留数量（默认保留最近 50 份；`0` 表示不清理）：

```bash
PYTHONPATH=src python3 scripts/compare_batch_presets.py --keep-cleanup-history 30
```

strict 压缩策略失败演示（故意包含失败任务，随后自动生成报告汇总）：

```bash
PYTHONPATH=src python3 scripts/demo_strict_failure_report.py
```

输出：
- `outputs/preset_compare/preset_compare.csv`
- `outputs/preset_compare/preset_compare.md`
- `outputs/preset_compare/preset_compare_<UTC时间戳>.csv`（按 `--keep-snapshots` 保留最近 N 份）
- `outputs/preset_compare/preset_compare_cleanup_latest.json`（最近一次清理统计：清理前后数量与删减来源）

### 8) 多标的组合回测（等权/风险平价/目标波动率）

```bash
PYTHONPATH=src python3 -m market_signal_system portfolio \
  --symbols QQQ,ETH \
  --strategy momentum \
  --allocation-mode cov_vol_target \
  --target-vol 0.15 \
  --max-leverage 1.5 \
  --corr-watch-threshold 0.75 \
  --corr-high-threshold 0.85 \
  --crowding-watch-threshold 0.15 \
  --crowding-high-threshold 0.2 \
  --drift-watch-threshold 0.08 \
  --drift-high-threshold 0.15 \
  --rebalance-on-drift \
  --rebalance-trigger high \
  --rebalance-scale 1.0 \
  --start 2020-01-01 \
  --end 2025-01-01
```

### 9) 自动汇总报告

```bash
PYTHONPATH=src python3 -m market_signal_system report --output-file report_index.md
PYTHONPATH=src python3 -m market_signal_system report \
  --output-file report_index.md \
  --champion-switch-csv-file champion_switch_last_runs.csv \
  --champion-switch-recent-runs 10 \
  --champion-switch-watch-threshold 1 \
  --champion-switch-high-threshold 2
```

报告会自动汇总单策略/组合回测、告警、权重偏移，以及组合模拟资金占用摘要（平均暴露率、平均/峰值保证金利用率、平均预留现金占比）。
当存在 `leaderboard_*.csv` 时，报告会输出每个榜单文件的 `excess_top/excess_bottom`，并给出跨文件 `aggregate_excess_top/aggregate_excess_bottom`。
当存在 `leaderboard_by_symbol_*.csv` 时，报告会新增“分组排行榜（按标的）”，自动汇总每个 symbol 的组内冠军策略。
报告还会基于最近 10 份 `leaderboard_by_symbol_*.csv` 输出“分组冠军稳定性”（`samples/switches/unique_champions/latest/alert`），用于观察冠军策略切换频率。
若存在同标的 `score_regime` 与 `macd_regime` 回测工件，报告会新增“策略对照摘要”并输出 `score_minus_macd` 关键差值。
当存在 `run_config*_summary*.json` 或 `run_config*_summary*.json.gz` 时，报告还会输出批处理执行摘要（run_id、任务成功/失败计数、总耗时、最慢任务）。
若摘要中存在 `symbol_group_champions`，报告会追加 `compare_task#N champions=...`，直接展示该次 compare 的按标的冠军策略。
报告还会在批处理聚合段输出 `champion_switch_last_N_runs`，统计最近 N 次 run 每个 symbol 的冠军切换次数、最新冠军与 `alert` 级别。
`report` 命令默认会额外导出 `champion_switch_last_runs.csv`，输出每个 symbol 的 `samples/switches/unique_champions/latest/alert_level/first_run_time/latest_run_time`，便于外部监控系统直接消费。
若存在失败任务，报告还会给出 `failed_top_commands`（失败最多的命令 TopN）。
报告会额外汇总近 N 次批处理的跨文件统计：运行失败率、任务失败率、平均耗时、P50/P90 耗时。
批处理聚合段还会输出重试效率：`retry_hit_rate`、`total_retries_used`、`non_retryable_fail_share`。
当存在多个 `portfolio_rebalance_*.csv` 时，报告还会给出按“单次触发平均成本”排序的 best/worst 对比。
当存在 `outputs/preset_compare/preset_compare.csv` 时，报告会输出“预设对比摘要”，并自动给出激进-保守关键指标差值。
若存在多个 `preset_compare_<timestamp>.csv`，报告还会输出最新/上一次快照的 `total_return_gap` 与变动 `delta`。
报告会进一步输出最近 N 次快照的趋势聚合（`avg_gap/min_gap/max_gap/improving_ratio`，默认最近 10 次）。
若存在 `preset_compare_cleanup_latest.json`，报告会附带 `cleanup.latest`（generated_at + before/after/removed_by_date_range/removed_by_count）。
若存在 `preset_compare_cleanup_<timestamp>.json`，报告会附带最近 N 次清理聚合（首末执行时间、时间跨度、历史样本数 `history_files`、有效样本数 `valid_runs`、平均/最大清理量、`skipped_invalid_time`、`rows_with_invalid_numeric`、`abnormal_ratio`）。
当存在 `*retry_budget_trace*.csv` 或 `*retry_budget_trace*.csv.gz` 时，报告会输出“重试预算轨迹”摘要（预算耗尽事件、平均预算消耗、汇总统计）。
预算轨迹摘要会额外输出 `depleted_top_commands` 与 `aggregate_depleted_top_commands`，用于定位最易耗尽预算的命令。
预算轨迹摘要还会输出失败分布指标：`failed_rows`、`failed_ratio`、`depleted_failed`。

### 10) 参数稳定性分析

```bash
PYTHONPATH=src python3 -m market_signal_system stability \
  --walk-forward-file outputs/walk_forward_QQQ_donchian.csv
```

输出：
- 交易日志：`outputs/sim_trades_<symbol>_<strategy>.csv`
- 信号日志：`outputs/sim_signals_<symbol>_<strategy>.csv`
- 组合信号日志：`outputs/sim_portfolio_signals_<symbols>_<strategy>.csv`
- 组合交易日志：`outputs/sim_portfolio_trades_<symbols>_<strategy>.csv`
- 组合资金快照：`outputs/sim_portfolio_capital_<symbols>_<strategy>.csv`
- 组合模拟摘要：`outputs/sim_portfolio_summary_<symbols>_<strategy>.json`
  - 若设置 `--output-tag`，文件名会追加 `_<tag>` 后缀，便于同策略多参数并存。
  - 含恢复幂等增量审计：`skipped_duplicate_bars_run_delta.total`、`skipped_duplicate_bars_run_delta.by_symbol`
- 状态文件：`data/state/<state-file>`（支持重启恢复）
- 参数网格报告：`outputs/grid_<symbol>_<strategy>.csv`
- Walk-Forward 明细：`outputs/walk_forward_<symbol>_<strategy>.csv`
- Walk-Forward 汇总：`outputs/walk_forward_summary_<symbol>_<strategy>.json`
- 稳定性摘要：`outputs/stability_summary_*.json`
- 参数频次：`outputs/stability_freq_*.csv`
- 排行榜报告：`outputs/leaderboard_<symbols>.csv`
- 分组排行榜：`outputs/leaderboard_by_symbol_<symbols>.csv`（含 `symbol_rank`、`symbol_strategy_count`）
- 组合回测：`outputs/portfolio_metrics_*.json` / `portfolio_equity_*.csv` / `portfolio_positions_*.csv`
  - `portfolio_metrics_*.json` 同步包含组合 vs 等权持有基准的对比字段（`benchmark_total_return/excess_total_return/information_ratio`）
- 组合归因：`outputs/portfolio_contrib_*.csv` / `portfolio_attribution_*.csv`
- 组合告警：`outputs/portfolio_alerts_*.csv`
- 组合权重：`outputs/portfolio_weights_*.csv`
- 权重偏移：`outputs/portfolio_drift_*.csv`（目标权重 vs 漂移后权重）
- 漂移再平衡：`outputs/portfolio_rebalance_*.csv`（触发次数、额外换手与成本）
- 汇总报告：`outputs/report_index.md`
- Baseline 去重摘要：`outputs/baseline_daily_digest.json` / `baseline_daily_digest.csv`
- 快照清理诊断：`outputs/preset_compare/preset_compare_cleanup_latest.json` / `preset_compare_cleanup_<timestamp>.json`

## 策略说明

详见 [STRATEGIES.md](./STRATEGIES.md)。

## 运行测试

```bash
python3 -m pytest -q
```

## 项目结构

```text
market-signal-system/
  src/market_signal_system/
    data/           # 数据接入与缓存
    strategies/     # 策略实现
    backtest/       # 回测引擎与指标
    research/       # 参数研究与 walk-forward
    simulation/     # 模拟交易核心
    cli.py          # 命令行入口
  tests/
  data/
    cache/
    state/
  outputs/
  STATUS.md
  DECISIONS.md
```

## 当前边界

- 当前以日线中长线为主，未覆盖分钟级高频场景。
- 回测与模拟交易使用单品种单信号执行模型，后续可扩展组合级资金分配。
