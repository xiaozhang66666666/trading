# Web 登录 MVP 设计（2026-03-16）

## 1. 目标与边界
- 本阶段目标：交付可部署的网页登录 MVP。
- 覆盖范围：预置账号、登录页、session/cookie 鉴权、Signal Pilot 数据按账号隔离展示。
- 非目标：页面注册、OAuth、权限分级、分布式会话、复杂后台管理。

## 2. 分层设计

### 2.1 模型层（`appdb.models`）
- `Account`：账号基础信息。
- `AccountCredential`：密码哈希信息。
- `WebSession`：会话元数据。
- `SignalAlertView`：Signal Pilot 只读视图模型。

### 2.2 Repository 抽象层（`appdb.repositories`）
- `AuthRepository`：账号、凭据、会话 CRUD 协议。
- `SignalPilotRepository`：Signal Pilot 按账号读取协议。
- 目标：将存储细节从业务层剥离，方便替换存储后端。

### 2.3 SQLite 实现层（`appdb.sqlite_backend`）
- `SQLiteConnectionFactory`：连接工厂。
- `SQLiteSchemaManager`：schema 初始化与迁移（兼容旧表结构）。
- `SQLiteAuthRepository` / `SQLiteSignalPilotRepository`：SQLite 实现。
- 约束：SQL 仅集中在该实现层，避免散落到业务层和 Web 层。

### 2.4 Service 层（`appdb.services`）
- `AuthService`：账号预置、登录、会话校验、登出。
- `SignalPilotService`：按 `account_id` 查询近期告警。
- 特点：Service 只依赖 Repository 协议，不依赖具体 SQLite 类。

### 2.5 Web 层（`web.app`）
- FastAPI + Jinja2。
- 路由：`/login`、`/logout`、`/signal-pilot`、`/api/me`、`/api/signal-pilot/alerts`、`/healthz`。
- 责任：HTTP 与模板渲染、cookie 设置、登录态检查。

## 3. 数据库 Schema（SQLite）

### 3.1 `accounts`
- 主键：`account_id`。
- 登录字段：`username`（唯一）、`display_name`、`is_active`。
- 审计字段：`created_at`、`updated_at`。

### 3.2 `account_credentials`
- 主键：`account_id`。
- 字段：`password_hash`、`password_algo`、`updated_at`。

### 3.3 `web_sessions`
- 主键：`session_id`（随机 token）。
- 字段：`account_id`、`created_at`、`expires_at`、`last_seen_at`、`user_agent`、`ip_addr`。
- 索引：`expires_at`。

### 3.4 `signal_alerts`
- 复合主键：`(account_id, alert_id)`。
- Signal Pilot 业务字段沿用现有模型。
- 关键隔离键：`account_id`。

## 4. 鉴权设计
- 密码算法：`pbkdf2_sha256`。
- 登录成功后签发随机 `session_id`，写入 `web_sessions`。
- Cookie：`mss_session`，`HttpOnly`，`SameSite=Lax`，可选 `Secure`。
- 每次受保护请求：
  1. 读取 cookie。
  2. 查会话并清理过期会话。
  3. 验证账号状态。
  4. 滚动续期（延长会话 TTL）。

## 5. 账号预置策略
- 不开放页面注册。
- 使用脚本 `scripts/admin_seed_account.py` 后台预置/更新账号。
- 支持参数：`account_id`、`username`、`password`、`display_name`、`db_path`。

## 6. SQLite -> PostgreSQL/MySQL 迁移策略
- 保持 `Repository + Service` 接口稳定。
- 新增 `PostgresAuthRepository` / `PostgresSignalPilotRepository` 或 MySQL 实现。
- 迁移步骤：
  1. 新库实现同样协议。
  2. 保持 Service/Web 层不变。
  3. 通过配置切换 Repository 实现。
  4. 用双写或离线迁移脚本搬迁历史数据。

## 7. 部署与运行
- 启动：`python3 scripts/run_web.py --host 0.0.0.0 --port 8080`（脚本内自动注入 `src/`，无需额外 `PYTHONPATH`）。
- 健康检查：`GET /healthz`。
- 反向代理建议：Nginx/Traefik 终止 TLS 后回源 FastAPI。

## 8. 风险与后续
- 当前单机 SQLite，写并发能力有限。
- 当前无 RBAC，仅账号级隔离。
- 后续优先项：
  1. 会话固定攻击防护增强（登录后轮换策略、可选 IP 绑定）。
  2. 审计日志（登录成功/失败）。
  3. CSRF 防护（当前主要为内网站点 MVP，后续补齐）。
