# 数据源方案（T1 / T2）

## 目标
为多资产实时看盘与策略模拟平台确定可落地的数据源接入方案，覆盖：
- 美股实时 / 准实时行情
- 美股盘前 / 盘后（前提是数据源支持）
- Crypto 实时行情与 K 线
- 后续回测 / 模拟运行可复用的数据接口

## 结论（当前推荐）

### 1. Crypto（T1 直接落地）
**主数据源：Binance 官方 API**

推荐原因：
- 官方文档明确，REST + WebSocket 都有
- Spot 市场数据接口完整
- 支持最新价、成交、订单簿、K 线
- WebSocket 可直接用于实时更新
- 适合 ETH / BTC / SOL 等首期 Crypto 标的

可用能力：
- REST：
  - `/api/v3/klines`
  - `/api/v3/uiKlines`
  - `/api/v3/ticker/price`
  - `/api/v3/ticker/24hr`
  - `/api/v3/depth`
- WebSocket：
  - `wss://stream.binance.com:9443`
  - 支持 trade / aggTrade / depth / kline 等流

T1 落地建议：
- 历史 K 线：先接 REST `klines`
- 实时看盘：先接 WebSocket `kline` / `trade`
- 数据状态：前端展示 `实时 / 延迟 / 断连`

### 2. 美股（T1 推荐分层）
美股这块不要一开始就绑死单一供应商，建议做成“适配层 + 主备源”的结构。

#### 方案 A：Alpaca（推荐优先评估）
优点：
- 提供美股 market data
- 文档里明确区分 IEX 与 SIP feed
- 支持 live stream 与历史数据
- 有 feed 概念，适合后续扩展
- 文档明确提到 `v2/iex`（免费 live IEX）与 `v2/sip`（更完整，通常受订阅限制）

限制：
- 认证要求明确
- 更完整实时 / 最近 15 分钟 SIP 等能力可能依赖订阅
- 扩展时段（盘前 / 盘后）能力要结合具体 feed / plan 验证

适合用途：
- T1 作为美股实时源优先候选
- 先实现 provider adapter，不把业务层写死

#### 方案 B：Twelve Data（推荐作为快速接入候选 / 备选）
优点：
- 文档显示覆盖 Stocks / ETFs / Crypto
- 有 time series / quote / latest price / websocket / symbol search
- 同一个服务可同时覆盖美股与 Crypto，接入成本低
- 文档中可见有 extended hours data 相关内容

限制：
- 免费额度 / 实时能力 / WebSocket 能力要看套餐
- 真正高频实时能力可能不如交易型供应商稳

适合用途：
- T1 快速打通原型
- 或作为美股备选 / fallback

#### 方案 C：Finnhub（适合备选）
优点：
- 覆盖 realtime stock / forex / crypto
- 有统一 API 体验

限制：
- 当前抓到的公开文档摘要较浅，接入细节还需二次验证
- 免费层实时与调用频率限制要评估

适合用途：
- 备选 provider

#### 方案 D：Polygon / Massive（适合增强版）
优点：
- 市场数据能力强，适合专业行情
- 美股数据生态成熟

限制：
- 成本和套餐门槛通常更高
- T1 先上会增加复杂度与费用风险

适合用途：
- T2 或商业化增强

## 推荐落地架构

### T1 推荐组合
- Crypto：**Binance 官方 API（确定）**
- 美股：**先做 provider 抽象层，默认优先接 Alpaca；若认证/套餐限制卡住，则先用 Twelve Data 打通页面与流程**

### 统一抽象
后端统一抽象成：
- `MarketDataProvider`
- `search_symbols(query)`
- `get_quote(symbol)`
- `get_klines(symbol, interval, start, end)`
- `get_market_session(symbol)`
- `get_provider_status()`
- `subscribe_stream(symbols, interval)`（后续 WebSocket / SSE）

这样好处：
- 业务层不依赖单一第三方
- 美股可以后续切换 Alpaca / Twelve Data / Finnhub / Polygon
- Crypto 也能从 Binance 扩到更多交易所

## 会话 / 交易时段处理

### 美股
前端展示统一状态：
- 盘前
- 正常盘
- 盘后
- 休市

规则：
- 若 provider 明确返回 session / extended hours 信息，则优先使用 provider 数据
- 若 provider 不直接返回，则由后端根据交易所时区和时间规则推导
- 要额外区分：
  - 行情可用但非正常盘
  - 数据源在线但扩展时段数据不可用

### Crypto
前端展示：
- `7x24`
- 实时 / 延迟 / 断连

## T1 实施建议

### T1-01
- 完成 symbol / market / provider 抽象
- `QQQ / TQQQ / ETH` 搜索与自选
- provider 状态面板
- market session 状态展示
- Binance adapter 真接入
- 美股 provider 先做 adapter 骨架，优先接 Alpaca 或 Twelve Data

### T1-02
- 接 K 线数据
- Crypto 先用 Binance 实时流
- 美股优先用已接通 provider 的 quote + bar
- 扩展时段明确标注

### T1-03
- 支持 CSV / Parquet 下载
- 缓存与缺失检测

## 当前建议（执行口径）
1. **Crypto 不再讨论，直接接 Binance。**
2. **美股先做 provider 适配层。**
3. **优先试 Alpaca；如果权限/套餐限制导致推进慢，就先切 Twelve Data 打通 T1。**
4. **盘前 / 盘后能力保留在接口层和 UI 层，不要等全部 provider 完美再设计。**
5. **所有数据源都要在页面上显示状态：在线 / 限制 / 断连 / 延迟。**
