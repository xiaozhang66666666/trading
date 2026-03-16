# 存储设计（SQLite + 多账号命名空间）

## 目标
- 在本地单机环境下提供可扩展的多账号隔离存储。
- `account_id` 作为核心命名空间键，优先覆盖：
  - Signal Pilot alerts 台账
  - 通知派发记录
  - 模拟交易状态元数据

## 默认存储
- SQLite 文件：`data/state/market_signal_system.db`
- 默认账号：`default`

说明：
- Signal Pilot 读写优先走 SQLite。
- 兼容层会同步写 CSV（默认 `data/state/signal_alert_ledger.csv`）；非默认账号自动命名为 `signal_alert_ledger.<account_id>.csv`。

## Schema

### 1) `accounts`
- 主键：`account_id`
- 字段：`display_name`、`namespace`、`created_at`、`updated_at`、`meta_json`

### 2) `signal_alerts`
- 复合主键：`(account_id, alert_id)`
- 核心字段：`created_at/symbol/strategy/strategy_params/interval/side/alert_price/alert_reason/status`
- 收益跟踪：`current_*`、`realized_*`、`max_favorable_excursion`、`max_adverse_excursion`、`holding_*`
- 通知状态：`notification_sent/channel/last_attempt_at/last_sent_at/fail_count`

### 3) `notification_dispatch_records`
- 主键：`id`（自增）
- 字段：`account_id`、`alert_id`、`event_time`、`channel`、`status`
- 错误/重试：`error_type/error_message/used_retry/retry_count`
- 原始载荷：`payload_json`

### 4) `sim_state_meta`
- 复合主键：`(account_id, state_key)`
- 字段：`backend`、`state_path`、`updated_at`、`meta_json`
- 用途：登记 `simulate/simulate-portfolio` 的状态文件和上下文元信息

## CLI 命名空间参数

以下命令支持：
- `scan-alerts --account-id --db-file`
- `dispatch-alerts --account-id --db-file`
- `update-alerts --account-id --db-file`
- `report-alerts --account-id --db-file`
- `simulate --account-id --db-file`
- `simulate-portfolio --account-id --db-file`

其中 Signal Pilot 四命令已优先按 `account_id` 隔离数据。

## 兼容策略
- 未指定 `account_id` 时等价于 `default`，保持旧行为。
- 旧 CSV 台账可被自动导入 SQLite（按当前 `account_id`）。
- 现有 JSONL 通知队列格式保持兼容，仅增加可选 `account_id` 字段。
