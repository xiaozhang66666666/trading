import { useEffect, useMemo, useState } from "react";

import {
  buildHistoryDownloadUrl,
  buildLogsExportUrl,
  checkDatasourceNotifications,
  changeRunStatus,
  copyRun,
  createRun,
  copyStrategy,
  deleteRun,
  createStrategy,
  deleteStrategy,
  getDataSources,
  getPnlSummary,
  getHistoryKlines,
  listPositionLogs,
  listStrategies,
  listTradeLogs,
  listRuns,
  listNotifications,
  listSignals,
  markNotificationsRead,
  getMarketKlines,
  getMarketOverview,
  refreshHistoryKlines,
  runBacktest,
  searchSymbols,
  tickSignalEngine,
} from "./api";
import type {
  BacktestResult,
  DataSourceStatus,
  DataState,
  HistoryDataset,
  Kline,
  MarketOverview,
  NotificationRecord,
  PnlSummary,
  PositionLog,
  RunInstance,
  RunInstancePayload,
  SignalRecord,
  StrategyPayload,
  StrategyRecord,
  StrategyTemplate,
  SymbolView,
  TradeLog,
} from "./types";

const intervals = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

const dataStateText: Record<DataState, string> = {
  REALTIME: "实时",
  DELAYED: "延迟",
  DISCONNECTED: "断开",
  RESERVED: "预留",
};

const marketText = {
  US_EQUITY: "美股",
  CRYPTO: "Crypto",
};

type IndicatorKey = "MA" | "EMA" | "RSI" | "MACD" | "BOLL";

const defaultDsl = JSON.stringify(
  {
    strategy: { name: "模板策略", version: "1.0.0" },
    indicators: [{ name: "ma", params: { short: 5, long: 20 } }],
    conditions: { logic: "AND" },
    entry_long: { when: "ma_short_cross_over_ma_long" },
    exit_long: { when: "ma_short_cross_below_ma_long" },
    entry_short: { when: "ma_short_cross_below_ma_long" },
    exit_short: { when: "ma_short_cross_over_ma_long" },
    risk: { take_profit: 3, stop_loss: 1.2, cooldown_bars: 2, notifications: { in_app: true } },
  },
  null,
  2,
);

function formatNumber(value: number, fraction = 2): string {
  return Number.isFinite(value) ? value.toLocaleString("zh-CN", { maximumFractionDigits: fraction }) : "-";
}

function sma(data: number[], period: number): Array<number | null> {
  return data.map((_, index) => {
    if (index + 1 < period) return null;
    const slice = data.slice(index + 1 - period, index + 1);
    return slice.reduce((acc, item) => acc + item, 0) / period;
  });
}

function ema(data: number[], period: number): Array<number | null> {
  const k = 2 / (period + 1);
  let previous: number | null = null;
  return data.map((value, index) => {
    if (index === 0) {
      previous = value;
      return value;
    }
    if (previous == null) return null;
    previous = value * k + previous * (1 - k);
    return previous;
  });
}

function stdDev(data: number[]): number {
  const mean = data.reduce((acc, value) => acc + value, 0) / data.length;
  const variance = data.reduce((acc, value) => acc + (value - mean) ** 2, 0) / data.length;
  return Math.sqrt(variance);
}

function computeIndicators(candles: Kline[]) {
  const closes = candles.map((item) => item.close);
  const ma = sma(closes, 20);
  const emaValues = ema(closes, 20);

  const rsi = closes.map((_, index) => {
    if (index < 14) return null;
    let gains = 0;
    let losses = 0;
    for (let i = index - 13; i <= index; i += 1) {
      const change = closes[i] - closes[i - 1];
      if (change > 0) gains += change;
      if (change < 0) losses += Math.abs(change);
    }
    if (losses === 0) return 100;
    const rs = gains / losses;
    return 100 - 100 / (1 + rs);
  });

  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = closes.map((_, index) => {
    if (ema12[index] == null || ema26[index] == null) return null;
    return (ema12[index] as number) - (ema26[index] as number);
  });
  const signalLine = ema(macdLine.map((item) => item ?? 0), 9);

  const boll = closes.map((_, index) => {
    if (index < 19) return { upper: null, middle: null, lower: null };
    const sample = closes.slice(index - 19, index + 1);
    const middle = sample.reduce((acc, value) => acc + value, 0) / sample.length;
    const dev = stdDev(sample);
    return { upper: middle + dev * 2, middle, lower: middle - dev * 2 };
  });

  return { ma, ema: emaValues, rsi, macdLine, signalLine, boll };
}

function CandleChart({ candles, enabledIndicators }: { candles: Kline[]; enabledIndicators: Set<IndicatorKey> }) {
  if (candles.length === 0) {
    return <div className="chart-empty">K 线加载失败或无可用数据</div>;
  }

  const width = 980;
  const height = 420;
  const priceMin = Math.min(...candles.map((item) => item.low));
  const priceMax = Math.max(...candles.map((item) => item.high));
  const priceRange = Math.max(priceMax - priceMin, 1e-6);
  const candleWidth = Math.max(width / candles.length - 1, 2);
  const indicator = computeIndicators(candles);

  const yFromPrice = (price: number) => height - ((price - priceMin) / priceRange) * (height - 24) - 12;

  function linePath(values: Array<number | null>): string {
    let path = "";
    values.forEach((value, index) => {
      if (value == null) return;
      const x = (index / Math.max(candles.length - 1, 1)) * (width - 8) + 4;
      const y = yFromPrice(value);
      path += path ? ` L ${x} ${y}` : `M ${x} ${y}`;
    });
    return path;
  }

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="K线图">
        <rect x="0" y="0" width={width} height={height} fill="url(#chartBg)" />
        <defs>
          <linearGradient id="chartBg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0d1726" />
            <stop offset="100%" stopColor="#090f19" />
          </linearGradient>
        </defs>

        {candles.map((candle, index) => {
          const x = (index / candles.length) * width;
          const openY = yFromPrice(candle.open);
          const closeY = yFromPrice(candle.close);
          const highY = yFromPrice(candle.high);
          const lowY = yFromPrice(candle.low);
          const color = candle.close >= candle.open ? "#35d07f" : "#f05f66";
          return (
            <g key={candle.open_time}>
              <line x1={x + candleWidth / 2} y1={highY} x2={x + candleWidth / 2} y2={lowY} stroke={color} strokeWidth="1" />
              <rect
                x={x}
                y={Math.min(openY, closeY)}
                width={candleWidth}
                height={Math.max(Math.abs(closeY - openY), 1.5)}
                fill={color}
              />
            </g>
          );
        })}

        {enabledIndicators.has("MA") ? <path d={linePath(indicator.ma)} stroke="#59a8ff" strokeWidth="1.5" fill="none" /> : null}
        {enabledIndicators.has("EMA") ? <path d={linePath(indicator.ema)} stroke="#ffd166" strokeWidth="1.5" fill="none" /> : null}
        {enabledIndicators.has("BOLL") ? (
          <>
            <path d={linePath(indicator.boll.map((item) => item.upper))} stroke="#9d7dff" strokeWidth="1" fill="none" />
            <path d={linePath(indicator.boll.map((item) => item.middle))} stroke="#7aa2f7" strokeWidth="1" fill="none" />
            <path d={linePath(indicator.boll.map((item) => item.lower))} stroke="#9d7dff" strokeWidth="1" fill="none" />
          </>
        ) : null}
      </svg>
    </div>
  );
}

export default function App() {
  const [symbols, setSymbols] = useState<SymbolView[]>([]);
  const [sources, setSources] = useState<DataSourceStatus[]>([]);
  const [activeSymbol, setActiveSymbol] = useState("QQQ");
  const [activeInterval, setActiveInterval] = useState<(typeof intervals)[number]>("15m");
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [klines, setKlines] = useState<Kline[]>([]);
  const [keyword, setKeyword] = useState("");
  const [enabledIndicators, setEnabledIndicators] = useState<Set<IndicatorKey>>(
    () => new Set<IndicatorKey>(["MA", "EMA"]),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<HistoryDataset | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [strategies, setStrategies] = useState<StrategyRecord[]>([]);
  const [strategyError, setStrategyError] = useState("");
  const [strategySaving, setStrategySaving] = useState(false);
  const [backtestError, setBacktestError] = useState("");
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [runs, setRuns] = useState<RunInstance[]>([]);
  const [runError, setRunError] = useState("");
  const [runForm, setRunForm] = useState<RunInstancePayload>({
    name: "ETH 15m + 策略A",
    strategy_id: "",
    symbol: "ETH",
    interval: "15m",
    fee_rate: 0.0005,
    slippage_rate: 0.0005,
    risk_limit: 0.2,
    notify_in_app: true,
  });
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const [signalError, setSignalError] = useState("");
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [positionLogs, setPositionLogs] = useState<PositionLog[]>([]);
  const [tradeLogs, setTradeLogs] = useState<TradeLog[]>([]);
  const [pnlSummary, setPnlSummary] = useState<PnlSummary | null>(null);
  const [strategyForm, setStrategyForm] = useState<StrategyPayload>({
    name: "策略A",
    template: "MA_CROSS",
    interval: "15m",
    open_condition: "MA5 上穿 MA20",
    close_condition: "MA5 下穿 MA20",
    take_profit: 3,
    stop_loss: 1.2,
    position_size: 0.3,
    direction: { allow_long: true, allow_short: true, include_extended_hours: false },
    json_dsl: defaultDsl,
  });

  const filteredSymbols = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    if (!key) return symbols;
    return symbols.filter((item) => `${item.code}${item.name}`.toLowerCase().includes(key));
  }, [keyword, symbols]);

  async function refreshSources() {
    setSources(await getDataSources());
  }

  async function refreshStrategies() {
    const items = await listStrategies();
    setStrategies(items);
    if (items.length > 0) {
      setRunForm((prev) => ({ ...prev, strategy_id: prev.strategy_id || items[0].id }));
    }
  }

  async function refreshRuns() {
    setRuns(await listRuns());
  }

  async function refreshSignals() {
    setSignals(await listSignals());
  }

  async function refreshNotifications() {
    setNotifications(await listNotifications());
  }

  async function refreshLogs() {
    const [positions, trades, pnl] = await Promise.all([listPositionLogs(), listTradeLogs(), getPnlSummary()]);
    setPositionLogs(positions);
    setTradeLogs(trades);
    setPnlSummary(pnl);
  }

  async function loadHistory(symbol = activeSymbol, interval = activeInterval, force = false) {
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const data = force ? await refreshHistoryKlines(symbol, interval) : await getHistoryKlines(symbol, interval);
      setHistory(data);
    } catch (err: unknown) {
      setHistoryError(err instanceof Error ? err.message : "历史数据加载失败");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function submitStrategy() {
    setStrategySaving(true);
    setStrategyError("");
    try {
      await createStrategy(strategyForm);
      await refreshStrategies();
    } catch (err: unknown) {
      setStrategyError(err instanceof Error ? err.message : "策略保存失败");
    } finally {
      setStrategySaving(false);
    }
  }

  async function onCopyStrategy(strategyId: string) {
    await copyStrategy(strategyId);
    await refreshStrategies();
  }

  async function onDeleteStrategy(strategyId: string) {
    await deleteStrategy(strategyId);
    await refreshStrategies();
  }

  async function startBacktest() {
    if (strategies.length === 0) {
      setBacktestError("请先创建策略");
      return;
    }
    setBacktestError("");
    setBacktestLoading(true);
    try {
      const result = await runBacktest({
        strategy_id: strategies[0].id,
        symbol: activeSymbol,
        interval: activeInterval,
        initial_capital: 100000,
        fee_rate: 0.0005,
        slippage_rate: 0.0005,
        allow_long: true,
        allow_short: true,
        include_extended_hours: false,
      });
      setBacktestResult(result);
    } catch (err: unknown) {
      setBacktestError(err instanceof Error ? err.message : "回测失败");
    } finally {
      setBacktestLoading(false);
    }
  }

  async function createRunInstance() {
    setRunError("");
    try {
      const payload = { ...runForm, symbol: activeSymbol, interval: activeInterval };
      await createRun(payload);
      await refreshRuns();
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : "创建运行实例失败");
    }
  }

  async function runAction(runId: string, action: "start" | "pause" | "stop") {
    await changeRunStatus(runId, action);
    await refreshRuns();
  }

  async function copyRunInstance(runId: string) {
    await copyRun(runId);
    await refreshRuns();
  }

  async function removeRunInstance(runId: string) {
    await deleteRun(runId);
    await refreshRuns();
  }

  async function triggerSignalTick() {
    setSignalError("");
    try {
      await tickSignalEngine();
      await refreshSignals();
      await refreshNotifications();
      await refreshLogs();
    } catch (err: unknown) {
      setSignalError(err instanceof Error ? err.message : "信号计算失败");
    }
  }

  async function markAllNotificationsRead() {
    if (notifications.length === 0) return;
    await markNotificationsRead(notifications.filter((item) => !item.read).map((item) => item.id));
    await refreshNotifications();
  }

  async function checkDatasourceAlerts() {
    await checkDatasourceNotifications();
    await refreshNotifications();
  }

  async function refreshMarketData(symbol = activeSymbol, interval = activeInterval) {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextKlines] = await Promise.all([
        getMarketOverview(symbol),
        getMarketKlines(symbol, interval, 220),
      ]);
      setOverview(nextOverview);
      setKlines(nextKlines);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "看盘数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void searchSymbols("").then((items) => {
      setSymbols(items);
      if (!items.some((item) => item.code === activeSymbol) && items.length > 0) {
        setActiveSymbol(items[0].code);
      }
    });
    void refreshSources();
    void refreshStrategies();
    void refreshRuns();
    void refreshSignals();
    void refreshNotifications();
    void refreshLogs();
  }, []);

  useEffect(() => {
    void refreshMarketData(activeSymbol, activeInterval);
    void loadHistory(activeSymbol, activeInterval);
    const timer = window.setInterval(() => {
      void refreshMarketData(activeSymbol, activeInterval);
    }, 12000);
    return () => window.clearInterval(timer);
  }, [activeSymbol, activeInterval]);

  function toggleIndicator(indicator: IndicatorKey) {
    setEnabledIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(indicator)) next.delete(indicator);
      else next.add(indicator);
      return next;
    });
  }

  const quote = overview?.quote;

  return (
    <div className="terminal-page">
      <aside className="left-panel">
        <h1>实时看盘（T1-02）</h1>
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索标的（QQQ/TQQQ/ETH）"
          aria-label="搜索标的"
        />
        <ul className="symbol-list">
          {filteredSymbols.map((item) => (
            <li key={item.code}>
              <button
                type="button"
                className={`symbol-btn ${activeSymbol === item.code ? "active" : ""}`}
                onClick={() => setActiveSymbol(item.code)}
              >
                <div>
                  <strong>{item.code}</strong>
                  <span>{item.name}</span>
                </div>
                <small>{marketText[item.market]}</small>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="main-panel">
        <section className="summary-panel">
          <div className="symbol-head">
            <h2>{activeSymbol}</h2>
            {overview ? <span className="session-tag">{overview.session_label}</span> : null}
            {quote ? <span className={`state-tag ${quote.state.toLowerCase()}`}>{dataStateText[quote.state]}</span> : null}
          </div>

          <div className="quote-grid">
            <div>
              <label>最新价</label>
              <strong>{formatNumber(quote?.last ?? 0, 4)}</strong>
            </div>
            <div>
              <label>涨跌额</label>
              <strong className={(quote?.change ?? 0) >= 0 ? "up" : "down"}>{formatNumber(quote?.change ?? 0, 4)}</strong>
            </div>
            <div>
              <label>涨跌幅</label>
              <strong className={(quote?.change_percent ?? 0) >= 0 ? "up" : "down"}>
                {formatNumber(quote?.change_percent ?? 0, 2)}%
              </strong>
            </div>
            <div>
              <label>最高</label>
              <strong>{formatNumber(quote?.high ?? 0, 4)}</strong>
            </div>
            <div>
              <label>最低</label>
              <strong>{formatNumber(quote?.low ?? 0, 4)}</strong>
            </div>
            <div>
              <label>成交量</label>
              <strong>{formatNumber(quote?.volume ?? 0, 2)}</strong>
            </div>
          </div>

          <p className="quote-detail">{quote?.detail ?? "等待行情..."}</p>
        </section>

        <section className="chart-panel">
          <div className="toolbar-row">
            <div className="interval-group">
              {intervals.map((interval) => (
                <button
                  type="button"
                  key={interval}
                  className={activeInterval === interval ? "active" : ""}
                  onClick={() => setActiveInterval(interval)}
                >
                  {interval}
                </button>
              ))}
            </div>

            <div className="indicator-group">
              {(["MA", "EMA", "RSI", "MACD", "BOLL"] as const).map((indicator) => (
                <button
                  type="button"
                  key={indicator}
                  className={enabledIndicators.has(indicator) ? "active" : ""}
                  onClick={() => toggleIndicator(indicator)}
                >
                  {indicator}
                </button>
              ))}
            </div>
          </div>

          {error ? <div className="error">{error}</div> : null}
          {loading ? <div className="hint">加载中...</div> : null}
          <CandleChart candles={klines} enabledIndicators={enabledIndicators} />

          <div className="sub-indicators">
            <div>RSI：{enabledIndicators.has("RSI") ? "已开启（14）" : "已关闭"}</div>
            <div>MACD：{enabledIndicators.has("MACD") ? "已开启（12,26,9）" : "已关闭"}</div>
            <div>BOLL：{enabledIndicators.has("BOLL") ? "已开启（20,2）" : "已关闭"}</div>
          </div>
        </section>
      </main>

      <aside className="right-panel">
        <div className="panel-title-row">
          <h3>数据源状态</h3>
          <button type="button" onClick={() => void refreshSources()}>
            刷新
          </button>
        </div>
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.name}>
              <div>
                <strong>{source.name}</strong>
                <span className={`state-tag ${source.state.toLowerCase()}`}>{dataStateText[source.state]}</span>
              </div>
              <p>{source.detail}</p>
            </li>
          ))}
        </ul>

        <div className="history-panel">
          <div className="panel-title-row">
            <h3>历史数据中心（T1-03）</h3>
            <button type="button" onClick={() => void loadHistory(activeSymbol, activeInterval, true)}>
              手动刷新
            </button>
          </div>
          <div className="history-meta">
            <span>标的：{activeSymbol}</span>
            <span>周期：{activeInterval}</span>
            <span>来源：{history?.source ?? "-"}</span>
            <span>更新时间：{history ? new Date(history.updated_at).toLocaleString("zh-CN") : "-"}</span>
            <span className={history?.has_missing ? "down" : "up"}>
              缺失检测：{history ? (history.has_missing ? `发现 ${history.missing_points} 个缺口` : "无缺失") : "-"}
            </span>
          </div>
          <div className="history-actions">
            <a href={buildHistoryDownloadUrl(activeSymbol, activeInterval, "csv")}>下载 CSV</a>
            <a href={buildHistoryDownloadUrl(activeSymbol, activeInterval, "parquet")}>下载 Parquet</a>
          </div>
          {historyLoading ? <div className="hint">历史数据刷新中...</div> : null}
          {historyError ? <div className="error">{historyError}</div> : null}
        </div>

        <div className="strategy-panel">
          <div className="panel-title-row">
            <h3>策略中心（T1-04）</h3>
            <button type="button" onClick={() => void submitStrategy()} disabled={strategySaving}>
              {strategySaving ? "保存中..." : "保存策略"}
            </button>
          </div>
          <div className="strategy-form">
            <input
              value={strategyForm.name}
              onChange={(event) => setStrategyForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="策略名称"
            />
            <select
              value={strategyForm.template}
              onChange={(event) =>
                setStrategyForm((prev) => ({ ...prev, template: event.target.value as StrategyTemplate }))
              }
            >
              <option value="MA_CROSS">MA 均线交叉</option>
              <option value="RSI_REVERSAL">RSI 超买超卖</option>
              <option value="MACD_TREND">MACD 趋势</option>
              <option value="BOLL_BREAKOUT">布林带突破/回归</option>
              <option value="RANGE_BREAKOUT">区间突破</option>
            </select>
            <div className="inline-fields">
              <label>
                止盈
                <input
                  type="number"
                  step="0.1"
                  value={strategyForm.take_profit}
                  onChange={(event) =>
                    setStrategyForm((prev) => ({ ...prev, take_profit: Number(event.target.value) }))
                  }
                />
              </label>
              <label>
                止损
                <input
                  type="number"
                  step="0.1"
                  value={strategyForm.stop_loss}
                  onChange={(event) => setStrategyForm((prev) => ({ ...prev, stop_loss: Number(event.target.value) }))}
                />
              </label>
            </div>
            <div className="inline-fields">
              <label>
                <input
                  type="checkbox"
                  checked={strategyForm.direction.allow_long}
                  onChange={(event) =>
                    setStrategyForm((prev) => ({
                      ...prev,
                      direction: { ...prev.direction, allow_long: event.target.checked },
                    }))
                  }
                />
                允许做多
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={strategyForm.direction.allow_short}
                  onChange={(event) =>
                    setStrategyForm((prev) => ({
                      ...prev,
                      direction: { ...prev.direction, allow_short: event.target.checked },
                    }))
                  }
                />
                允许做空
              </label>
            </div>
            <textarea
              value={strategyForm.json_dsl}
              onChange={(event) => setStrategyForm((prev) => ({ ...prev, json_dsl: event.target.value }))}
              rows={8}
            />
          </div>
          {strategyError ? <div className="error">{strategyError}</div> : null}

          <ul className="strategy-list">
            {strategies.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <span>v{item.current_version}</span>
                </div>
                <div className="actions">
                  <button type="button" onClick={() => void onCopyStrategy(item.id)}>
                    复制
                  </button>
                  <button type="button" onClick={() => void onDeleteStrategy(item.id)}>
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="backtest-panel">
          <div className="panel-title-row">
            <h3>回测系统（T1-05）</h3>
            <button type="button" onClick={() => void startBacktest()} disabled={backtestLoading}>
              {backtestLoading ? "回测中..." : "运行回测"}
            </button>
          </div>
          <div className="history-meta">
            <span>策略：{strategies[0]?.name ?? "-"}</span>
            <span>标的：{activeSymbol}</span>
            <span>周期：{activeInterval}</span>
            <span>模式：多空双向</span>
          </div>
          {backtestError ? <div className="error">{backtestError}</div> : null}
          {backtestResult ? (
            <>
              <div className="backtest-metrics">
                <span>总收益：{(backtestResult.metrics.total_return * 100).toFixed(2)}%</span>
                <span>年化：{(backtestResult.metrics.annual_return * 100).toFixed(2)}%</span>
                <span>最大回撤：{(backtestResult.metrics.max_drawdown * 100).toFixed(2)}%</span>
                <span>胜率：{(backtestResult.metrics.win_rate * 100).toFixed(2)}%</span>
                <span>交易次数：{backtestResult.metrics.trade_count}</span>
                <span>Profit Factor：{backtestResult.metrics.profit_factor.toFixed(3)}</span>
              </div>
              <div className="equity-preview">
                资金曲线点数：{backtestResult.equity_curve.length}，最后权益：
                {formatNumber(backtestResult.equity_curve[backtestResult.equity_curve.length - 1]?.equity ?? 0, 2)}
              </div>
              <div className="trade-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>方向</th>
                      <th>开仓时间</th>
                      <th>平仓时间</th>
                      <th>盈亏</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResult.trades.slice(0, 20).map((trade, idx) => (
                      <tr key={`${trade.entry_time}_${idx}`}>
                        <td>{trade.side}</td>
                        <td>{new Date(trade.entry_time).toLocaleString("zh-CN")}</td>
                        <td>{new Date(trade.exit_time).toLocaleString("zh-CN")}</td>
                        <td className={trade.pnl >= 0 ? "up" : "down"}>{formatNumber(trade.pnl, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>

        <div className="run-panel">
          <div className="panel-title-row">
            <h3>模拟运行中心（T1-06）</h3>
            <button type="button" onClick={() => void createRunInstance()}>
              新建实例
            </button>
          </div>
          <div className="history-meta">
            <span>实例名称</span>
            <input
              value={runForm.name}
              onChange={(event) => setRunForm((prev) => ({ ...prev, name: event.target.value }))}
            />
            <span>策略版本</span>
            <select
              value={runForm.strategy_id}
              onChange={(event) => setRunForm((prev) => ({ ...prev, strategy_id: event.target.value }))}
            >
              <option value="">请选择策略</option>
              {strategies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} v{item.current_version}
                </option>
              ))}
            </select>
            <span>标的/周期：{activeSymbol} / {activeInterval}</span>
          </div>
          {runError ? <div className="error">{runError}</div> : null}
          <ul className="strategy-list">
            {runs.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.payload.name}</strong>
                  <span>{item.status}</span>
                </div>
                <div className="actions">
                  <button type="button" onClick={() => void runAction(item.id, "start")}>
                    启动
                  </button>
                  <button type="button" onClick={() => void runAction(item.id, "pause")}>
                    暂停
                  </button>
                  <button type="button" onClick={() => void runAction(item.id, "stop")}>
                    停止
                  </button>
                  <button type="button" onClick={() => void copyRunInstance(item.id)}>
                    复制
                  </button>
                  <button type="button" onClick={() => void removeRunInstance(item.id)}>
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="signal-panel">
          <div className="panel-title-row">
            <h3>实时信号引擎（T1-07）</h3>
            <button type="button" onClick={() => void triggerSignalTick()}>
              手动计算一轮
            </button>
          </div>
          {signalError ? <div className="error">{signalError}</div> : null}
          <ul className="strategy-list">
            {signals.map((signal) => (
              <li key={signal.id}>
                <div>
                  <strong>{signal.signal_type}</strong>
                  <span>
                    {signal.symbol} {signal.interval}
                  </span>
                </div>
                <div>
                  <span>{new Date(signal.trigger_time).toLocaleString("zh-CN")}</span>
                  <span className="up">{formatNumber(signal.trigger_price, 4)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="notification-panel">
          <div className="panel-title-row">
            <h3>站内信通知（T1-08）</h3>
            <div className="actions">
              <button type="button" onClick={() => void checkDatasourceAlerts()}>
                检查数据源异常
              </button>
              <button type="button" onClick={() => void markAllNotificationsRead()}>
                全部标已读
              </button>
            </div>
          </div>
          <ul className="strategy-list">
            {notifications.map((note) => (
              <li key={note.id} className={note.read ? "" : "unread-item"}>
                <div>
                  <strong>{note.title}</strong>
                  <span>{note.type}</span>
                </div>
                <div>
                  <span>{new Date(note.created_at).toLocaleString("zh-CN")}</span>
                  <span>{note.read ? "已读" : "未读"}</span>
                </div>
                <p>{note.content}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="logs-panel">
          <div className="panel-title-row">
            <h3>日志与盈亏（T1-09）</h3>
            <a href={buildLogsExportUrl()} className="export-link">
              导出日志 CSV
            </a>
          </div>
          <div className="backtest-metrics">
            <span>已实现盈亏：{formatNumber(pnlSummary?.realized_pnl ?? 0, 4)}</span>
            <span>未实现盈亏：{formatNumber(pnlSummary?.unrealized_pnl ?? 0, 4)}</span>
            <span>累计盈亏：{formatNumber(pnlSummary?.total_pnl ?? 0, 4)}</span>
            <span>持仓日志：{positionLogs.length}</span>
            <span>成交日志：{tradeLogs.length}</span>
            <span>信号日志：{signals.length}</span>
          </div>
          <div className="trade-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>类型</th>
                  <th>标的</th>
                  <th>时间</th>
                  <th>价格/盈亏</th>
                </tr>
              </thead>
              <tbody>
                {positionLogs.slice(0, 10).map((log) => (
                  <tr key={log.id}>
                    <td>{log.action}</td>
                    <td>{log.symbol}</td>
                    <td>{new Date(log.timestamp).toLocaleString("zh-CN")}</td>
                    <td>{formatNumber(log.price, 4)}</td>
                  </tr>
                ))}
                {tradeLogs.slice(0, 10).map((log) => (
                  <tr key={log.id}>
                    <td>TRADE-{log.side}</td>
                    <td>{log.symbol}</td>
                    <td>{new Date(log.exit_time).toLocaleString("zh-CN")}</td>
                    <td className={log.realized_pnl >= 0 ? "up" : "down"}>{formatNumber(log.realized_pnl, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </aside>
    </div>
  );
}
