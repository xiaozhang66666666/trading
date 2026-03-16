# Signal Pilot 功能文档

## 1. 功能目标
Signal Pilot 是“先观察、后决策”的信号跟踪模块。  
它不直接下实盘单，而是把策略信号按生命周期落盘、跟踪、汇总，帮助你在 1~2 个月内判断：

- 信号是否稳定（胜率、盈亏分布、回撤容忍度）
- 哪些标的/策略组合值得升级到模拟交易或实盘
- 当前信号是否发生漂移（反向、超时、通知执行异常）

## 2. 适用场景
- 新策略刚上线，需要先做“纸上观察”
- 同时跟踪多标的（如 QQQ + ETH），避免人工记账
- 需要每天低频巡检，不想实时盯盘
- 需要给后续自动化（通知、告警、报表）保留结构化数据基础

## 3. 生命周期：scan -> dispatch -> update -> report

### 3.1 scan-alerts（扫描新信号）
作用：
- 对给定标的和策略计算最新信号
- 仅当最新信号是 `long/short` 时创建 alert（`flat` 跳过）
- 若 ledger 中已存在“同标的+同策略+同参数+同方向+open”则去重，不重复创建
- 新 alert 写入 ledger，并追加到待通知队列 `outputs/signal_pilot_notifications.jsonl`

示例：
```bash
PYTHONPATH=src python3 -m market_signal_system scan-alerts \
  --symbols QQQ,ETH \
  --strategy score_regime \
  --interval 1d
```

### 3.2 dispatch-alerts（派发通知）
作用：
- 读取待通知队列 JSONL
- 默认写入本地派发 sink（可选 webhook）
- 对已发送过的 alert 自动跳过
- 派发成功后回写 ledger：`notification_sent=true`、`notification_channel=...`

示例：
```bash
PYTHONPATH=src python3 -m market_signal_system dispatch-alerts \
  --queue-file signal_pilot_notifications.jsonl \
  --sink-file signal_pilot_notifications_dispatched.jsonl
```

### 3.3 update-alerts（更新观察收益与状态）
作用：
- 刷新 open alert 的当前价格、当前收益、MFE/MAE、持有时长
- 可按反向信号自动关闭（`status=closed`）
- 超过最大观察天数自动过期（`status=expired`）

示例：
```bash
PYTHONPATH=src python3 -m market_signal_system update-alerts \
  --max-holding-days 60 \
  --close-on-reverse
```

### 3.4 report-alerts（输出观察报告）
作用：
- 按窗口（默认 7/30/60 天）统计 `symbol + strategy` 维度表现
- 同时导出 CSV/JSON/Markdown
- 收益口径优先使用已实现收益，未平仓时回退到当前浮动收益

示例：
```bash
PYTHONPATH=src python3 -m market_signal_system report-alerts \
  --windows 7,30,60
```

## 4. Alert Ledger 字段说明
默认文件：`data/state/signal_alert_ledger.csv`

| 字段 | 含义 |
|---|---|
| `alert_id` | Alert 唯一 ID |
| `created_at` | Alert 创建时间（UTC） |
| `symbol` | 标的，如 `QQQ`/`ETH` |
| `strategy` | 策略名，如 `score_regime` |
| `strategy_params` | 策略参数 JSON（规范化字符串） |
| `interval` | K 线周期，如 `1d` |
| `side` | 方向：`long` / `short` |
| `alert_price` | 触发价格 |
| `alert_reason` | 触发原因（来自策略 explain） |
| `status` | 状态：`open` / `closed` / `expired` |
| `close_time` | 关闭/过期时间 |
| `close_price` | 关闭/过期价格 |
| `realized_pnl` | 已实现收益（价格差额口径） |
| `realized_pnl_pct` | 已实现收益率 |
| `current_price` | 当前观察价格 |
| `current_pnl` | 当前浮动收益（价格差额口径） |
| `current_pnl_pct` | 当前浮动收益率 |
| `max_favorable_excursion` | MFE（观察期内最大有利收益率） |
| `max_adverse_excursion` | MAE（观察期内最大不利收益率） |
| `holding_bars` | 持有 bar 数 |
| `holding_days` | 持有天数 |
| `notification_sent` | 是否已派发通知 |
| `notification_channel` | 通知通道（`local_file`/`webhook`/`dry_run`） |

## 5. 日常运行方式（推荐）

### 5.1 单命令批处理（推荐）
使用模板串行执行：
```bash
PYTHONPATH=src python3 -m market_signal_system run-config \
  --file examples/config.batch.signal_pilot.daily.json
```

该模板默认链路：`scan -> dispatch -> update -> report`。

### 5.2 分步执行（排障时）
按生命周期四步分别执行，便于定位是“信号没出”“通知失败”还是“收益更新异常”。

## 6. 如何看 1~2 个月观察结果

建议每周固定复盘一次，主要看 `report-alerts` 的 30/60 天窗口：

1. 看覆盖面  
`signal_count` 是否足够。样本太少时，不要过早下结论。

2. 看收益质量  
优先看 `avg_return_pct`、`max_loss_pct`、`win_rate` 三者是否匹配。

3. 看持有效率  
`avg_holding_days` 是否符合你的中长线节奏（太短像噪音，太长可能效率低）。

4. 看路径风险  
`avg_mfe` 与 `avg_mae` 对比可判断“先亏后赚”是否可接受。

5. 看状态结构  
ledger 中 `open/closed/expired` 分布是否健康；`expired` 过高常意味着信号迟钝或退出条件偏弱。

结论建议：
- 连续 1~2 个月（至少覆盖 30/60 天窗口）仍稳定的组合，优先进入 `simulate` 或 `simulate-portfolio`。
- 若收益依赖极少数 alert，先继续观察，避免样本幻觉。

## 7. 当前限制
- 当前是低频本地 CLI 流程，不是实时流式系统
- 通知重试与去重窗口机制较简化（默认幂等依赖 ledger 的 `notification_sent`）
- 关闭条件目前以“反向信号/超时”为主，未内建更细粒度止盈止损
- 报告以聚合统计为主，暂未内建分层可视化分析

## 8. 后续扩展方向
- 增加通知重试策略、失败回放与 dead-letter 队列
- 增加 alert 分级（强/中/弱）与信号置信度字段
- 增加更丰富的关闭条件（止盈、止损、波动率收缩/放大）
- 增加按标的/策略的稳定性告警阈值
- 将报告扩展为可追踪趋势的周/月对比视图

## 9. 相关文件与工件
- 代码：
  - `src/market_signal_system/signal_pilot/ledger.py`
  - `src/market_signal_system/signal_pilot/pilot.py`
  - `src/market_signal_system/signal_pilot/notify.py`
- 模板：
  - `examples/config.signal_pilot.scan.json`
  - `examples/config.signal_pilot.dispatch.json`
  - `examples/config.signal_pilot.update.json`
  - `examples/config.signal_pilot.report.json`
  - `examples/config.batch.signal_pilot.daily.json`
- 关键产物：
  - `data/state/signal_alert_ledger.csv`
  - `outputs/signal_pilot_notifications.jsonl`
  - `outputs/signal_pilot_notifications_dispatched.jsonl`
  - `outputs/signal_pilot_alert_report_<ts>.csv/.json/.md`
