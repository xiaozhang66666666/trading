import { useEffect, useMemo, useState } from "react";

import {
  buildHistoryDownloadUrl,
  buildLogsExportUrl,
  changeRunStatus,
  checkDatasourceNotifications,
  copyRun,
  copyStrategy,
  createRun,
  createStrategy,
  deleteRun,
  deleteStrategy,
  getDataSources,
  getHistoryKlines,
  getMarketKlines,
  getMarketOverview,
  getPnlSummary,
  getSystemHealth,
  getSystemSettings,
  listNotifications,
  listPositionLogs,
  listRuns,
  listSignals,
  listStrategies,
  listTradeLogs,
  markNotificationsRead,
  refreshHistoryKlines,
  runBacktest,
  searchSymbols,
  tickSignalEngine,
  updateSystemSettings,
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
  SystemHealth,
  SystemSettings,
  TradeLog,
} from "./types";

const intervals = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
type IndicatorKey = "MA" | "EMA" | "RSI" | "MACD" | "BOLL";
type NavKey = "overview" | "market" | "strategy" | "backtest" | "run" | "notification" | "system";

const navItems: Array<{ key: NavKey; label: string; desc: string }> = [
  { key: "overview", label: "总览", desc: "产品总览与状态" },
  { key: "market", label: "市场看板", desc: "实时行情与历史" },
  { key: "strategy", label: "策略中心", desc: "模板与 JSON 策略" },
  { key: "backtest", label: "回测", desc: "策略回测与指标" },
  { key: "run", label: "模拟运行", desc: "运行实例与信号" },
  { key: "notification", label: "通知中心", desc: "站内通知管理" },
  { key: "system", label: "系统设置", desc: "参数与健康状态" },
];

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

const notificationTypeText = {
  SIGNAL: "信号",
  SYSTEM: "系统",
  DATASOURCE: "数据源",
};

const signalTypeText = {
  OPEN_LONG: "开多",
  CLOSE_LONG: "平多",
  OPEN_SHORT: "开空",
  CLOSE_SHORT: "平空",
};

const strategyTemplateText: Record<StrategyTemplate, string> = {
  MA_CROSS: "MA 均线交叉",
  RSI_REVERSAL: "RSI 超买超卖",
  MACD_TREND: "MACD 趋势",
  BOLL_BREAKOUT: "布林带突破/回归",
  RANGE_BREAKOUT: "区间突破",
};

const strategyTemplateHint: Record<StrategyTemplate, string> = {
  MA_CROSS: "适合趋势切换明确的阶段，参数易理解，适合作为基线策略。",
  RSI_REVERSAL: "适合震荡市场，注意避免单边行情中连续逆势入场。",
  MACD_TREND: "强调趋势跟随，适合中周期观察，建议配合止损。",
  BOLL_BREAKOUT: "适合波动扩张或均值回归验证，需关注假突破。",
  RANGE_BREAKOUT: "适合箱体突破交易，建议配合成交量或波动过滤。",
};

const runStatusText = {
  PENDING: "待运行",
  RUNNING: "运行中",
  PAUSED: "暂停",
  STOPPED: "已停止",
  ERROR: "异常",
};

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

function formatDateTime(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function containsHint(value: string | undefined, hints: string[]): boolean {
  const normalized = (value ?? "").toLowerCase();
  return hints.some((hint) => normalized.includes(hint));
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

  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = closes.map((_, index) => {
    if (ema12[index] == null || ema26[index] == null) return null;
    return (ema12[index] as number) - (ema26[index] as number);
  });
  const signalLine = ema(macdLine.map((item) => item ?? 0), 9);

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
    return <div className="empty-state">K 线加载失败或暂无可用数据</div>;
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
            <stop offset="0%" stopColor="#121f34" />
            <stop offset="100%" stopColor="#0b1221" />
          </linearGradient>
        </defs>

        {candles.map((candle, index) => {
          const x = (index / candles.length) * width;
          const openY = yFromPrice(candle.open);
          const closeY = yFromPrice(candle.close);
          const highY = yFromPrice(candle.high);
          const lowY = yFromPrice(candle.low);
          const color = candle.close >= candle.open ? "#3ccd8e" : "#ef626a";
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

        {enabledIndicators.has("MA") ? <path d={linePath(indicator.ma)} stroke="#6fb3ff" strokeWidth="1.5" fill="none" /> : null}
        {enabledIndicators.has("EMA") ? <path d={linePath(indicator.ema)} stroke="#ffc961" strokeWidth="1.5" fill="none" /> : null}
        {enabledIndicators.has("BOLL") ? (
          <>
            <path d={linePath(indicator.boll.map((item) => item.upper))} stroke="#9e84f9" strokeWidth="1" fill="none" />
            <path d={linePath(indicator.boll.map((item) => item.middle))} stroke="#70a4ff" strokeWidth="1" fill="none" />
            <path d={linePath(indicator.boll.map((item) => item.lower))} stroke="#9e84f9" strokeWidth="1" fill="none" />
          </>
        ) : null}
      </svg>
    </div>
  );
}

function DataStateTag({ state }: { state: DataState }) {
  return <span className={`state-tag ${state.toLowerCase()}`}>{dataStateText[state]}</span>;
}

export default function App() {
  const [currentNav, setCurrentNav] = useState<NavKey>("overview");
  const [symbols, setSymbols] = useState<SymbolView[]>([]);
  const [sources, setSources] = useState<DataSourceStatus[]>([]);
  const [activeSymbol, setActiveSymbol] = useState("QQQ");
  const [activeInterval, setActiveInterval] = useState<(typeof intervals)[number]>("15m");
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [klines, setKlines] = useState<Kline[]>([]);
  const [keyword, setKeyword] = useState("");
  const [marketFilter, setMarketFilter] = useState<"ALL" | "US_EQUITY" | "CRYPTO">("ALL");
  const [marketStateFilter, setMarketStateFilter] = useState<"ALL" | DataState>("ALL");
  const [enabledIndicators, setEnabledIndicators] = useState<Set<IndicatorKey>>(() => new Set<IndicatorKey>(["MA", "EMA"]));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [history, setHistory] = useState<HistoryDataset | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);

  const [strategies, setStrategies] = useState<StrategyRecord[]>([]);
  const [strategyError, setStrategyError] = useState("");
  const [strategySaving, setStrategySaving] = useState(false);
  const [strategyKeyword, setStrategyKeyword] = useState("");
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
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

  const [backtestError, setBacktestError] = useState("");
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  const [runs, setRuns] = useState<RunInstance[]>([]);
  const [runError, setRunError] = useState("");
  const [runSearch, setRunSearch] = useState("");
  const [runStatusFilter, setRunStatusFilter] = useState<"ALL" | RunInstance["status"]>("ALL");
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
  const [signalTypeFilter, setSignalTypeFilter] = useState<"ALL" | SignalRecord["signal_type"]>("ALL");

  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [notificationError, setNotificationError] = useState("");
  const [notificationKeyword, setNotificationKeyword] = useState("");
  const [notificationTypeFilter, setNotificationTypeFilter] = useState<"ALL" | NotificationRecord["type"]>("ALL");
  const [notificationReadFilter, setNotificationReadFilter] = useState<"ALL" | "READ" | "UNREAD">("ALL");

  const [positionLogs, setPositionLogs] = useState<PositionLog[]>([]);
  const [tradeLogs, setTradeLogs] = useState<TradeLog[]>([]);
  const [pnlSummary, setPnlSummary] = useState<PnlSummary | null>(null);

  const [systemSettings, setSystemSettings] = useState<SystemSettings | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [systemError, setSystemError] = useState("");

  const filteredSymbols = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    return symbols.filter((item) => {
      if (key && !`${item.code}${item.name}`.toLowerCase().includes(key)) return false;
      if (marketFilter !== "ALL" && item.market !== marketFilter) return false;
      if (marketStateFilter !== "ALL" && item.data_state !== marketStateFilter) return false;
      return true;
    });
  }, [keyword, marketFilter, marketStateFilter, symbols]);

  const strategyFiltered = useMemo(() => {
    const key = strategyKeyword.trim().toLowerCase();
    if (!key) return strategies;
    return strategies.filter((item) => {
      const target = [item.name, strategyTemplateText[item.latest_payload.template], item.latest_payload.interval].join(" ").toLowerCase();
      return target.includes(key);
    });
  }, [strategies, strategyKeyword]);

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.id === selectedStrategyId) ?? strategies[0] ?? null,
    [selectedStrategyId, strategies],
  );

  const runStats = useMemo(
    () => ({
      running: runs.filter((item) => item.status === "RUNNING").length,
      paused: runs.filter((item) => item.status === "PAUSED").length,
      error: runs.filter((item) => item.status === "ERROR").length,
      pending: runs.filter((item) => item.status === "PENDING").length,
    }),
    [runs],
  );

  const filteredRuns = useMemo(() => {
    const key = runSearch.trim().toLowerCase();
    return runs.filter((item) => {
      if (runStatusFilter !== "ALL" && item.status !== runStatusFilter) return false;
      if (!key) return true;
      const target = [item.payload.name, item.payload.symbol, item.payload.interval, runStatusText[item.status]].join(" ").toLowerCase();
      return target.includes(key);
    });
  }, [runSearch, runStatusFilter, runs]);

  const filteredSignals = useMemo(() => {
    return signals.filter((item) => (signalTypeFilter === "ALL" ? true : item.signal_type === signalTypeFilter));
  }, [signalTypeFilter, signals]);

  const filteredNotifications = useMemo(() => {
    const key = notificationKeyword.trim().toLowerCase();
    return notifications.filter((item) => {
      if (notificationTypeFilter !== "ALL" && item.type !== notificationTypeFilter) return false;
      if (notificationReadFilter === "READ" && !item.read) return false;
      if (notificationReadFilter === "UNREAD" && item.read) return false;
      if (!key) return true;
      return [item.title, item.content, notificationTypeText[item.type]].join(" ").toLowerCase().includes(key);
    });
  }, [notificationKeyword, notificationReadFilter, notificationTypeFilter, notifications]);

  const disconnectedSources = useMemo(() => sources.filter((item) => item.state === "DISCONNECTED"), [sources]);
  const warningSources = useMemo(() => sources.filter((item) => item.state === "DELAYED" || item.state === "RESERVED"), [sources]);
  const datasourceNotConfigured = useMemo(
    () => sources.filter((item) => containsHint(item.detail, ["未配置", "placeholder", "占位", "fallback", "回退"])),
    [sources],
  );

  const unreadCount = notifications.filter((item) => !item.read).length;
  const quote = overview?.quote;
  const activeNavItem = navItems.find((item) => item.key === currentNav) ?? navItems[0];

  const overviewAttentionItems = useMemo(() => {
    const items: string[] = [];
    if (disconnectedSources.length > 0) items.push(`${disconnectedSources.length} 个数据源断连，需检查凭证或网络。`);
    if (datasourceNotConfigured.length > 0) items.push(`${datasourceNotConfigured.length} 个数据源仍处于未配置或占位状态。`);
    if (history?.has_missing) items.push(`历史数据检测到 ${history.missing_points} 个缺口，建议手动刷新后再下载或回测。`);
    if (!selectedStrategy) items.push("当前没有可用策略，回测与模拟运行入口将受限。");
    if (runStats.error > 0) items.push(`${runStats.error} 个运行实例处于异常状态，建议优先排查。`);
    if (unreadCount > 0) items.push(`${unreadCount} 条未读通知等待处理。`);
    return items;
  }, [datasourceNotConfigured.length, disconnectedSources.length, history?.has_missing, history?.missing_points, selectedStrategy, runStats.error, unreadCount]);

  async function refreshSources() {
    setSources(await getDataSources());
  }

  async function refreshStrategies() {
    const items = await listStrategies();
    setStrategies(items);
    if (items.length > 0) {
      setSelectedStrategyId((prev) => prev || items[0].id);
      setRunForm((prev) => ({ ...prev, strategy_id: prev.strategy_id || items[0].id }));
    } else {
      setSelectedStrategyId("");
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

  async function refreshSystem() {
    const [settings, health] = await Promise.all([getSystemSettings(), getSystemHealth()]);
    setSystemSettings(settings);
    setSystemHealth(health);
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

  async function refreshMarketData(symbol = activeSymbol, interval = activeInterval) {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextKlines] = await Promise.all([getMarketOverview(symbol), getMarketKlines(symbol, interval, 220)]);
      setOverview(nextOverview);
      setKlines(nextKlines);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "看盘数据加载失败");
    } finally {
      setLoading(false);
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
    if (!selectedStrategy) {
      setBacktestError("请先创建策略");
      return;
    }
    if (history?.has_missing) {
      setBacktestError("历史数据存在缺口，请先刷新历史数据后再运行回测");
      return;
    }
    setBacktestError("");
    setBacktestLoading(true);
    try {
      const result = await runBacktest({
        strategy_id: selectedStrategy.id,
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
    if (!runForm.strategy_id) {
      setRunError("请先选择要绑定的策略版本");
      return;
    }
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
    setRunError("");
    try {
      await changeRunStatus(runId, action);
      await refreshRuns();
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : `实例${action}失败`);
    }
  }

  async function copyRunInstance(runId: string) {
    setRunError("");
    try {
      await copyRun(runId);
      await refreshRuns();
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : "复制运行实例失败");
    }
  }

  async function removeRunInstance(runId: string) {
    setRunError("");
    try {
      await deleteRun(runId);
      await refreshRuns();
    } catch (err: unknown) {
      setRunError(err instanceof Error ? err.message : "删除运行实例失败");
    }
  }

  function loadStrategyIntoForm(strategy: StrategyRecord) {
    setSelectedStrategyId(strategy.id);
    setRunForm((prev) => ({ ...prev, strategy_id: strategy.id, name: `${activeSymbol} ${activeInterval} + ${strategy.name}` }));
    setStrategyForm(strategy.latest_payload);
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
    if (unreadCount === 0) return;
    await markNotificationsRead(notifications.filter((item) => !item.read).map((item) => item.id));
    await refreshNotifications();
  }

  async function checkDatasourceAlerts() {
    setNotificationError("");
    try {
      await checkDatasourceNotifications();
      await refreshNotifications();
    } catch (err: unknown) {
      setNotificationError(err instanceof Error ? err.message : "数据源异常检查失败");
    }
  }

  async function saveSystemSettings() {
    if (!systemSettings) return;
    setSystemError("");
    try {
      await updateSystemSettings(systemSettings);
      await refreshSystem();
    } catch (err: unknown) {
      setSystemError(err instanceof Error ? err.message : "系统设置保存失败");
    }
  }

  function toggleIndicator(indicator: IndicatorKey) {
    setEnabledIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(indicator)) next.delete(indicator);
      else next.add(indicator);
      return next;
    });
  }

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const items = await searchSymbols("");
        setSymbols(items);
        if (!items.some((item) => item.code === activeSymbol) && items.length > 0) {
          setActiveSymbol(items[0].code);
        }
      } catch {
        setError("标的列表加载失败");
      }
      await Promise.all([
        refreshSources(),
        refreshStrategies(),
        refreshRuns(),
        refreshSignals(),
        refreshNotifications(),
        refreshLogs(),
        refreshSystem(),
      ]).catch(() => {
        setError((prev) => prev || "初始化加载部分失败，请刷新重试");
      });
    };

    void bootstrap();
  }, []);

  useEffect(() => {
    void refreshMarketData(activeSymbol, activeInterval);
    void loadHistory(activeSymbol, activeInterval);
    const timer = window.setInterval(() => {
      void refreshMarketData(activeSymbol, activeInterval);
    }, 12000);
    return () => window.clearInterval(timer);
  }, [activeSymbol, activeInterval]);

  function renderOverviewPage() {
    return (
      <div className="content-grid two-col">
        <section className="panel panel-highlight">
          <div className="panel-head">
            <h2>产品总览</h2>
            <span className="subtle">部署域名：trading.1522237.xyz</span>
          </div>
          <div className="metric-grid">
            <article>
              <label>当前标的</label>
              <strong>{activeSymbol}</strong>
            </article>
            <article>
              <label>行情状态</label>
              <strong>{quote ? dataStateText[quote.state] : "-"}</strong>
            </article>
            <article>
              <label>运行中实例</label>
              <strong>{systemHealth?.running_instances ?? 0}</strong>
            </article>
            <article>
              <label>未读通知</label>
              <strong>{unreadCount}</strong>
            </article>
            <article>
              <label>累计盈亏</label>
              <strong className={(pnlSummary?.total_pnl ?? 0) >= 0 ? "up" : "down"}>{formatNumber(pnlSummary?.total_pnl ?? 0, 4)}</strong>
            </article>
            <article>
              <label>策略数量</label>
              <strong>{strategies.length}</strong>
            </article>
          </div>
          <div className="hint-strip">
            <span>当前焦点：{activeSymbol} / {activeInterval}</span>
            <span>历史来源：{history?.source ?? "未就绪"}</span>
            <span>最新报价时间：{formatDateTime(quote?.timestamp)}</span>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>待处理事项</h3>
            <span className="subtle">优先处理会影响回测、模拟运行和通知的阻塞项</span>
          </div>
          {overviewAttentionItems.length > 0 ? (
            <ul className="list-block compact">
              {overviewAttentionItems.map((item) => (
                <li key={item} className="attention-item">
                  <strong>需关注</strong>
                  <p>{item}</p>
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state">当前关键模块状态稳定，可直接进入看盘、回测或模拟运行。</div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>快捷入口</h3>
          </div>
          <div className="quick-nav-grid">
            {navItems.slice(1).map((item) => (
              <button type="button" key={item.key} className="quick-card" onClick={() => setCurrentNav(item.key)}>
                <strong>{item.label}</strong>
                <span>{item.desc}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>数据源状态</h3>
            <button type="button" onClick={() => void refreshSources()}>刷新</button>
          </div>
          <ul className="list-block">
            {sources.map((source) => (
              <li key={source.name}>
                <div className="list-head">
                  <strong>{source.name}</strong>
                  <DataStateTag state={source.state} />
                </div>
                <p>{source.detail}</p>
                <p>最近检查：{formatDateTime(source.checked_at)}</p>
                {containsHint(source.detail, ["未配置", "placeholder", "占位"]) ? (
                  <div className="hint">当前数据源尚未完整配置，页面可能展示占位数据或回退结果。</div>
                ) : null}
              </li>
            ))}
            {sources.length === 0 ? <li className="plain-text">尚未拿到数据源状态，请先检查后端连接。</li> : null}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>最新通知</h3>
            <button type="button" onClick={() => setCurrentNav("notification")}>进入通知中心</button>
          </div>
          <ul className="list-block compact">
            {notifications.slice(0, 6).map((note) => (
              <li key={note.id} className={note.read ? "" : "unread-item"}>
                <div className="list-head">
                  <strong>{note.title}</strong>
                  <span>{notificationTypeText[note.type]} · {note.read ? "已读" : "未读"}</span>
                </div>
                <p>{formatDateTime(note.created_at)}</p>
                <p>{note.content}</p>
              </li>
            ))}
            {notifications.length === 0 ? <li className="plain-text">暂无通知</li> : null}
          </ul>
        </section>
      </div>
    );
  }

  function renderMarketPage() {
    return (
      <div className="content-grid market-layout">
        <section className="panel">
          <div className="panel-head">
            <h3>标的列表</h3>
          </div>
          <div className="form-grid compact-grid">
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索标的（QQQ/TQQQ/ETH）"
              aria-label="搜索标的"
            />
            <div className="inline-fields stretch-fields">
              <label>
                市场
                <select value={marketFilter} onChange={(event) => setMarketFilter(event.target.value as typeof marketFilter)}>
                  <option value="ALL">全部</option>
                  <option value="US_EQUITY">美股</option>
                  <option value="CRYPTO">Crypto</option>
                </select>
              </label>
              <label>
                状态
                <select value={marketStateFilter} onChange={(event) => setMarketStateFilter(event.target.value as typeof marketStateFilter)}>
                  <option value="ALL">全部</option>
                  <option value="REALTIME">实时</option>
                  <option value="DELAYED">延迟</option>
                  <option value="DISCONNECTED">断连</option>
                  <option value="RESERVED">预留</option>
                </select>
              </label>
            </div>
          </div>
          <p className="plain-text">共 {filteredSymbols.length} 个结果，支持按市场与链路状态快速定位。</p>
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
                    <span>{item.session_label || item.data_detail}</span>
                  </div>
                  <small>{marketText[item.market]}</small>
                </button>
              </li>
            ))}
            {filteredSymbols.length === 0 ? <li className="empty-state">未找到符合筛选条件的标的，请放宽筛选或检查标的列表接口。</li> : null}
          </ul>
        </section>

        <section className="panel panel-wide">
          <div className="panel-head">
            <h2>{activeSymbol}</h2>
            <div className="panel-head-right">
              {overview ? <span className="session-tag">{overview.session_label}</span> : null}
              {quote ? <DataStateTag state={quote.state} /> : null}
            </div>
          </div>
          <div className="meta-grid status-meta">
            <span>市场：{overview ? marketText[overview.market] : "-"}</span>
            <span>会话：{overview?.session_label ?? "-"}</span>
            <span>报价时间：{formatDateTime(quote?.timestamp)}</span>
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
              <strong className={(quote?.change_percent ?? 0) >= 0 ? "up" : "down"}>{formatNumber(quote?.change_percent ?? 0, 2)}%</strong>
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

          {quote?.detail ? (
            <div className={quote.state === "DISCONNECTED" ? "error" : "hint"}>
              {quote.detail}
              {quote.state === "DISCONNECTED" ? " 当前无法确认最新实时链路，数值可能为缓存或占位结果。" : ""}
            </div>
          ) : null}
          {error ? <div className="error">{error}</div> : null}
          {loading ? <div className="hint">行情加载中...</div> : null}
          <CandleChart candles={klines} enabledIndicators={enabledIndicators} />
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>历史数据中心</h3>
            <button type="button" onClick={() => void loadHistory(activeSymbol, activeInterval, true)}>手动刷新</button>
          </div>
          <div className="meta-grid">
            <span>标的：{activeSymbol}</span>
            <span>周期：{activeInterval}</span>
            <span>来源：{history?.source ?? "-"}</span>
            <span>更新时间：{history ? formatDateTime(history.updated_at) : "-"}</span>
            <span className={history?.has_missing ? "down" : "up"}>
              缺失检测：{history ? (history.has_missing ? `发现 ${history.missing_points} 个缺口` : "无缺失") : "-"}
            </span>
          </div>
          <div className="row-actions">
            <a href={buildHistoryDownloadUrl(activeSymbol, activeInterval, "csv")}>下载 CSV</a>
            <a href={buildHistoryDownloadUrl(activeSymbol, activeInterval, "parquet")}>下载 Parquet</a>
          </div>
          {historyLoading ? <div className="hint">历史数据刷新中...</div> : null}
          {historyError ? <div className="error">{historyError}</div> : null}
          {!historyLoading && !historyError && history && history.candles.length === 0 ? (
            <div className="empty-state">当前标的尚未拿到历史 K 线，可能是数据源未配置、无权限或该时间粒度暂无数据。</div>
          ) : null}
          {!historyError && history?.has_missing ? (
            <div className="hint">检测到缺口后仍可浏览，但下载、回测和模拟运行前建议先手动刷新。</div>
          ) : null}
        </section>
      </div>
    );
  }

  function renderStrategyPage() {
    return (
      <div className="content-grid two-col">
        <section className="panel panel-wide">
          <div className="panel-head">
            <h2>策略中心</h2>
            <button type="button" onClick={() => void submitStrategy()} disabled={strategySaving}>
              {strategySaving ? "保存中..." : "保存策略"}
            </button>
          </div>
          <div className="metric-grid small compact-metrics">
            <article><label>模板</label><strong>{strategyTemplateText[strategyForm.template]}</strong></article>
            <article><label>周期</label><strong>{strategyForm.interval}</strong></article>
            <article><label>仓位</label><strong>{formatNumber(strategyForm.position_size * 100, 0)}%</strong></article>
          </div>
          <div className="hint">{strategyTemplateHint[strategyForm.template]}</div>
          <div className="form-grid">
            <input
              value={strategyForm.name}
              onChange={(event) => setStrategyForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="策略名称"
            />
            <select
              value={strategyForm.template}
              onChange={(event) => setStrategyForm((prev) => ({ ...prev, template: event.target.value as StrategyTemplate }))}
            >
              <option value="MA_CROSS">MA 均线交叉</option>
              <option value="RSI_REVERSAL">RSI 超买超卖</option>
              <option value="MACD_TREND">MACD 趋势</option>
              <option value="BOLL_BREAKOUT">布林带突破/回归</option>
              <option value="RANGE_BREAKOUT">区间突破</option>
            </select>
            <label>
              运行周期
              <select
                value={strategyForm.interval}
                onChange={(event) => setStrategyForm((prev) => ({ ...prev, interval: event.target.value }))}
              >
                {intervals.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            <div className="inline-fields">
              <label>
                止盈
                <input
                  type="number"
                  step="0.1"
                  value={strategyForm.take_profit}
                  onChange={(event) => setStrategyForm((prev) => ({ ...prev, take_profit: Number(event.target.value) }))}
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
              <label>
                仓位比例
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  max={1}
                  value={strategyForm.position_size}
                  onChange={(event) => setStrategyForm((prev) => ({ ...prev, position_size: Number(event.target.value) }))}
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
            <label className="check-line">
              <input
                type="checkbox"
                checked={strategyForm.direction.include_extended_hours}
                onChange={(event) =>
                  setStrategyForm((prev) => ({
                    ...prev,
                    direction: { ...prev.direction, include_extended_hours: event.target.checked },
                  }))
                }
              />
              允许盘前 / 盘后参与（仅在数据源支持时生效）
            </label>
            <textarea
              value={strategyForm.json_dsl}
              onChange={(event) => setStrategyForm((prev) => ({ ...prev, json_dsl: event.target.value }))}
              rows={16}
            />
          </div>
          {!strategyForm.json_dsl.trim() ? <div className="error">JSON DSL 为空，保存后将难以追溯规则逻辑。</div> : null}
          {!strategyForm.direction.allow_long && !strategyForm.direction.allow_short ? (
            <div className="error">当前策略未允许任何方向，回测和运行将无法产生交易。</div>
          ) : null}
          {strategyError ? <div className="error">{strategyError}</div> : null}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>策略列表</h3>
          </div>
          <input
            value={strategyKeyword}
            onChange={(event) => setStrategyKeyword(event.target.value)}
            placeholder="按名称 / 模板 / 周期搜索策略"
          />
          <ul className="list-block">
            {strategyFiltered.map((item) => (
              <li key={item.id} className={selectedStrategy?.id === item.id ? "selected-item" : ""}>
                <div className="list-head">
                  <strong>{item.name}</strong>
                  <span>v{item.current_version}</span>
                </div>
                <p>{strategyTemplateText[item.latest_payload.template]} · {item.latest_payload.interval}</p>
                <p>更新时间：{formatDateTime(item.updated_at)}</p>
                <div className="row-actions">
                  <button type="button" onClick={() => loadStrategyIntoForm(item)}>载入表单</button>
                  <button type="button" onClick={() => void onCopyStrategy(item.id)}>复制</button>
                  <button type="button" onClick={() => void onDeleteStrategy(item.id)}>删除</button>
                </div>
              </li>
            ))}
            {strategies.length === 0 ? <li className="plain-text">暂无策略，请先新建</li> : null}
            {strategies.length > 0 && strategyFiltered.length === 0 ? <li className="plain-text">没有匹配当前搜索条件的策略</li> : null}
          </ul>
        </section>
      </div>
    );
  }

  function renderBacktestPage() {
    return (
      <div className="content-grid single-col">
        <section className="panel">
          <div className="panel-head">
            <h2>回测系统</h2>
            <button type="button" onClick={() => void startBacktest()} disabled={backtestLoading}>
              {backtestLoading ? "回测中..." : "运行回测"}
            </button>
          </div>
          <div className="inline-fields stretch-fields">
            <label>
              策略版本
              <select value={selectedStrategy?.id ?? ""} onChange={(event) => setSelectedStrategyId(event.target.value)}>
                {strategies.length === 0 ? <option value="">暂无策略</option> : null}
                {strategies.map((item) => (
                  <option key={item.id} value={item.id}>{item.name} v{item.current_version}</option>
                ))}
              </select>
            </label>
            <label>
              当前标的
              <input value={activeSymbol} readOnly />
            </label>
            <label>
              当前周期
              <input value={activeInterval} readOnly />
            </label>
          </div>
          <div className="meta-grid">
            <span>策略：{selectedStrategy?.name ?? "-"}</span>
            <span>标的：{activeSymbol}</span>
            <span>周期：{activeInterval}</span>
            <span>模式：多空双向</span>
          </div>
          <div className="checklist-grid">
            <span className={selectedStrategy ? "up" : "down"}>策略：{selectedStrategy ? "已选择" : "未配置"}</span>
            <span className={history && !history.has_missing ? "up" : "down"}>历史数据：{history ? (history.has_missing ? "存在缺口" : "已就绪") : "未加载"}</span>
            <span className={quote?.state === "REALTIME" || quote?.state === "DELAYED" ? "up" : "down"}>行情链路：{quote ? dataStateText[quote.state] : "未连接"}</span>
          </div>
          {backtestError ? <div className="error">{backtestError}</div> : null}
          {backtestResult ? (
            <>
              <div className="metric-grid small">
                <article><label>总收益</label><strong>{(backtestResult.metrics.total_return * 100).toFixed(2)}%</strong></article>
                <article><label>年化</label><strong>{(backtestResult.metrics.annual_return * 100).toFixed(2)}%</strong></article>
                <article><label>最大回撤</label><strong>{(backtestResult.metrics.max_drawdown * 100).toFixed(2)}%</strong></article>
                <article><label>胜率</label><strong>{(backtestResult.metrics.win_rate * 100).toFixed(2)}%</strong></article>
                <article><label>交易次数</label><strong>{backtestResult.metrics.trade_count}</strong></article>
                <article><label>Profit Factor</label><strong>{backtestResult.metrics.profit_factor.toFixed(3)}</strong></article>
              </div>
              <p className="plain-text">
                资金曲线点数：{backtestResult.equity_curve.length}，最后权益：
                {formatNumber(backtestResult.equity_curve[backtestResult.equity_curve.length - 1]?.equity ?? 0, 2)}
              </p>
              {backtestResult.trades.length === 0 ? (
                <div className="hint">本次回测没有成交，通常是因为规则过严、周期不匹配，或当前历史数据不足以触发条件。</div>
              ) : null}
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>方向</th>
                      <th>开仓时间</th>
                      <th>平仓时间</th>
                      <th>盈亏</th>
                      <th>原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResult.trades.slice(0, 30).map((trade, idx) => (
                      <tr key={`${trade.entry_time}_${idx}`}>
                        <td>{trade.side}</td>
                        <td>{formatDateTime(trade.entry_time)}</td>
                        <td>{formatDateTime(trade.exit_time)}</td>
                        <td className={trade.pnl >= 0 ? "up" : "down"}>{formatNumber(trade.pnl, 2)}</td>
                        <td>{trade.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="empty-state">尚未执行回测。请先确认策略已选择、历史数据无明显缺口，再开始运行。</div>
          )}
        </section>
      </div>
    );
  }

  function renderRunPage() {
    return (
      <div className="content-grid two-col">
        <section className="panel">
          <div className="panel-head">
            <h2>模拟运行中心</h2>
            <button type="button" onClick={() => void createRunInstance()}>新建实例</button>
          </div>
          <div className="metric-grid small compact-metrics">
            <article><label>运行中</label><strong>{runStats.running}</strong></article>
            <article><label>暂停</label><strong>{runStats.paused}</strong></article>
            <article><label>异常</label><strong className={runStats.error > 0 ? "down" : "up"}>{runStats.error}</strong></article>
          </div>
          <div className="form-grid">
            <label>
              实例名称
              <input value={runForm.name} onChange={(event) => setRunForm((prev) => ({ ...prev, name: event.target.value }))} />
            </label>
            <label>
              策略版本
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
            </label>
            <div className="meta-grid">
              <span>标的：{activeSymbol}</span>
              <span>周期：{activeInterval}</span>
            </div>
            <div className="inline-fields stretch-fields">
              <label>
                手续费
                <input type="number" step="0.0001" value={runForm.fee_rate} onChange={(event) => setRunForm((prev) => ({ ...prev, fee_rate: Number(event.target.value) }))} />
              </label>
              <label>
                滑点
                <input type="number" step="0.0001" value={runForm.slippage_rate} onChange={(event) => setRunForm((prev) => ({ ...prev, slippage_rate: Number(event.target.value) }))} />
              </label>
              <label>
                风险上限
                <input type="number" step="0.01" min={0} max={1} value={runForm.risk_limit} onChange={(event) => setRunForm((prev) => ({ ...prev, risk_limit: Number(event.target.value) }))} />
              </label>
            </div>
            <label className="check-line">
              <input type="checkbox" checked={runForm.notify_in_app} onChange={(event) => setRunForm((prev) => ({ ...prev, notify_in_app: event.target.checked }))} />
              开启站内通知
            </label>
          </div>
          {runError ? <div className="error">{runError}</div> : null}

          <div className="inline-fields stretch-fields">
            <label>
              搜索实例
              <input value={runSearch} onChange={(event) => setRunSearch(event.target.value)} placeholder="名称 / 标的 / 状态" />
            </label>
            <label>
              状态筛选
              <select value={runStatusFilter} onChange={(event) => setRunStatusFilter(event.target.value as typeof runStatusFilter)}>
                <option value="ALL">全部</option>
                <option value="PENDING">待运行</option>
                <option value="RUNNING">运行中</option>
                <option value="PAUSED">暂停</option>
                <option value="STOPPED">已停止</option>
                <option value="ERROR">异常</option>
              </select>
            </label>
          </div>

          <ul className="list-block">
            {filteredRuns.map((item) => (
              <li key={item.id} className={item.status === "ERROR" ? "attention-item" : ""}>
                <div className="list-head">
                  <strong>{item.payload.name}</strong>
                  <span className={`status-pill ${item.status.toLowerCase()}`}>{runStatusText[item.status]}</span>
                </div>
                <p>{item.payload.symbol} / {item.payload.interval}</p>
                <p>风险上限 {formatNumber(item.payload.risk_limit * 100, 0)}% · 手续费 {item.payload.fee_rate} · 滑点 {item.payload.slippage_rate}</p>
                <p>更新时间：{formatDateTime(item.updated_at)}</p>
                <div className="row-actions">
                  <button type="button" onClick={() => void runAction(item.id, "start")}>启动</button>
                  <button type="button" onClick={() => void runAction(item.id, "pause")}>暂停</button>
                  <button type="button" onClick={() => void runAction(item.id, "stop")}>停止</button>
                  <button type="button" onClick={() => void copyRunInstance(item.id)}>复制</button>
                  <button type="button" onClick={() => void removeRunInstance(item.id)}>删除</button>
                </div>
              </li>
            ))}
            {runs.length === 0 ? <li className="plain-text">暂无运行实例</li> : null}
            {runs.length > 0 && filteredRuns.length === 0 ? <li className="plain-text">没有匹配当前筛选条件的运行实例</li> : null}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>信号与日志</h3>
            <button type="button" onClick={() => void triggerSignalTick()}>手动计算一轮</button>
          </div>
          {signalError ? <div className="error">{signalError}</div> : null}
          <div className="metric-grid small">
            <article><label>已实现盈亏</label><strong>{formatNumber(pnlSummary?.realized_pnl ?? 0, 4)}</strong></article>
            <article><label>未实现盈亏</label><strong>{formatNumber(pnlSummary?.unrealized_pnl ?? 0, 4)}</strong></article>
            <article><label>累计盈亏</label><strong className={(pnlSummary?.total_pnl ?? 0) >= 0 ? "up" : "down"}>{formatNumber(pnlSummary?.total_pnl ?? 0, 4)}</strong></article>
            <article><label>信号数量</label><strong>{signals.length}</strong></article>
          </div>
          <div className="inline-fields stretch-fields">
            <label>
              信号类型
              <select value={signalTypeFilter} onChange={(event) => setSignalTypeFilter(event.target.value as typeof signalTypeFilter)}>
                <option value="ALL">全部</option>
                <option value="OPEN_LONG">开多</option>
                <option value="CLOSE_LONG">平多</option>
                <option value="OPEN_SHORT">开空</option>
                <option value="CLOSE_SHORT">平空</option>
              </select>
            </label>
            <span className="plain-text">持仓日志 {positionLogs.length} 条 · 成交日志 {tradeLogs.length} 条</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>类型</th>
                  <th>标的/周期</th>
                  <th>触发时间</th>
                  <th>价格</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                {filteredSignals.slice(0, 20).map((signal) => (
                  <tr key={signal.id}>
                    <td>{signalTypeText[signal.signal_type]}</td>
                    <td>{signal.symbol} / {signal.interval}</td>
                    <td>{formatDateTime(signal.trigger_time)}</td>
                    <td>{formatNumber(signal.trigger_price, 4)}</td>
                    <td>{signal.reason_snapshot}</td>
                  </tr>
                ))}
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="plain-text">暂无信号</td>
                  </tr>
                ) : null}
                {signals.length > 0 && filteredSignals.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="plain-text">没有匹配当前筛选条件的信号</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="row-actions">
            <a href={buildLogsExportUrl()}>导出日志 CSV</a>
          </div>
        </section>
      </div>
    );
  }

  function renderNotificationPage() {
    return (
      <div className="content-grid single-col">
        <section className="panel">
          <div className="panel-head">
            <h2>通知中心</h2>
            <div className="row-actions">
              <button type="button" onClick={() => void checkDatasourceAlerts()}>检查数据源异常</button>
              <button type="button" onClick={() => void markAllNotificationsRead()}>全部标记已读</button>
            </div>
          </div>
          <div className="metric-grid small compact-metrics">
            <article><label>总通知</label><strong>{notifications.length}</strong></article>
            <article><label>未读</label><strong>{unreadCount}</strong></article>
            <article><label>数据源类</label><strong>{notifications.filter((item) => item.type === "DATASOURCE").length}</strong></article>
          </div>
          <div className="inline-fields stretch-fields">
            <label>
              搜索
              <input value={notificationKeyword} onChange={(event) => setNotificationKeyword(event.target.value)} placeholder="标题 / 内容 / 类型" />
            </label>
            <label>
              类型
              <select value={notificationTypeFilter} onChange={(event) => setNotificationTypeFilter(event.target.value as typeof notificationTypeFilter)}>
                <option value="ALL">全部</option>
                <option value="SIGNAL">信号</option>
                <option value="SYSTEM">系统</option>
                <option value="DATASOURCE">数据源</option>
              </select>
            </label>
            <label>
              已读状态
              <select value={notificationReadFilter} onChange={(event) => setNotificationReadFilter(event.target.value as typeof notificationReadFilter)}>
                <option value="ALL">全部</option>
                <option value="UNREAD">未读</option>
                <option value="READ">已读</option>
              </select>
            </label>
          </div>
          {notificationError ? <div className="error">{notificationError}</div> : null}
          <ul className="list-block">
            {filteredNotifications.map((note) => (
              <li key={note.id} className={note.read ? "" : "unread-item"}>
                <div className="list-head">
                  <strong>{note.title}</strong>
                  <span>{notificationTypeText[note.type]} · {note.read ? "已读" : "未读"}</span>
                </div>
                <p>{formatDateTime(note.created_at)}</p>
                <p>{note.content}</p>
              </li>
            ))}
            {notifications.length === 0 ? <li className="plain-text">当前暂无通知</li> : null}
            {notifications.length > 0 && filteredNotifications.length === 0 ? <li className="plain-text">当前筛选条件下没有通知</li> : null}
          </ul>
          {notifications.length === 0 && disconnectedSources.length === 0 ? (
            <div className="hint">目前没有站内消息。如果你正在排查链路问题，可先执行“检查数据源异常”。</div>
          ) : null}
        </section>
      </div>
    );
  }

  function renderSystemPage() {
    return (
      <div className="content-grid two-col">
        <section className="panel panel-wide">
          <div className="panel-head">
            <h2>系统设置</h2>
            <button type="button" onClick={() => void saveSystemSettings()}>保存设置</button>
          </div>
          {systemSettings?.feishu_enabled && !systemSettings.feishu_webhook_url ? (
            <div className="error">已启用飞书通知但未配置 Webhook URL，通知不会实际发送。</div>
          ) : null}
          {!systemSettings?.feishu_enabled ? (
            <div className="hint">飞书通知当前未启用；站内通知仍会保留，适合先验证策略和信号链路。</div>
          ) : null}
          {systemSettings ? (
            <div className="form-grid settings-grid">
              <label>
                美股主数据源
                <input
                  value={systemSettings.preferred_us_provider}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, preferred_us_provider: event.target.value } : prev))
                  }
                />
              </label>
              <label>
                美股备份源
                <input
                  value={systemSettings.fallback_us_provider}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, fallback_us_provider: event.target.value } : prev))
                  }
                />
              </label>
              <label>
                默认手续费
                <input
                  type="number"
                  step="0.0001"
                  value={systemSettings.default_fee_rate}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, default_fee_rate: Number(event.target.value) } : prev))
                  }
                />
              </label>
              <label>
                默认滑点
                <input
                  type="number"
                  step="0.0001"
                  value={systemSettings.default_slippage_rate}
                  onChange={(event) =>
                    setSystemSettings((prev) =>
                      prev ? { ...prev, default_slippage_rate: Number(event.target.value) } : prev,
                    )
                  }
                />
              </label>
              <label>
                时区
                <input
                  value={systemSettings.timezone}
                  onChange={(event) => setSystemSettings((prev) => (prev ? { ...prev, timezone: event.target.value } : prev))}
                />
              </label>
              <label>
                飞书 Webhook
                <input
                  value={systemSettings.feishu_webhook_url}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, feishu_webhook_url: event.target.value } : prev))
                  }
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                />
              </label>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={systemSettings.feishu_enabled}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, feishu_enabled: event.target.checked } : prev))
                  }
                />
                启用飞书通知
              </label>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={systemSettings.feishu_notify_signal}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, feishu_notify_signal: event.target.checked } : prev))
                  }
                />
                开平仓信号推送
              </label>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={systemSettings.feishu_notify_system}
                  onChange={(event) =>
                    setSystemSettings((prev) => (prev ? { ...prev, feishu_notify_system: event.target.checked } : prev))
                  }
                />
                系统异常推送
              </label>
              <label>
                节流秒数
                <input
                  type="number"
                  min={0}
                  step="1"
                  value={systemSettings.feishu_throttle_seconds}
                  onChange={(event) =>
                    setSystemSettings((prev) =>
                      prev ? { ...prev, feishu_throttle_seconds: Number(event.target.value) } : prev,
                    )
                  }
                />
              </label>
            </div>
          ) : (
            <div className="hint">系统设置加载中...</div>
          )}
          {systemError ? <div className="error">{systemError}</div> : null}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h3>系统健康</h3>
          </div>
          {systemHealth ? (
            <>
              <div className="metric-grid small">
                <article><label>API</label><strong>{systemHealth.api_status}</strong></article>
                <article><label>运行中</label><strong>{systemHealth.running_instances}</strong></article>
                <article><label>暂停</label><strong>{systemHealth.paused_instances}</strong></article>
                <article><label>已停止</label><strong>{systemHealth.stopped_instances}</strong></article>
                <article><label>异常数</label><strong>{systemHealth.errors.length}</strong></article>
              </div>
              <ul className="list-block compact">
                {systemHealth.data_sources.map((item) => (
                  <li key={item.name}>
                    <div className="list-head">
                      <strong>{item.name}</strong>
                      <span className={`status-pill ${String(item.state).toLowerCase()}`}>{item.state}</span>
                    </div>
                    <p>{item.detail}</p>
                    <p>最近检查：{formatDateTime(item.checked_at)}</p>
                  </li>
                ))}
                {systemHealth.data_sources.length === 0 ? <li className="plain-text">系统健康接口尚未返回数据源明细。</li> : null}
              </ul>
              {systemHealth.errors.length > 0 ? (
                <div className="error">最近错误：{systemHealth.errors.join("；")}</div>
              ) : (
                <div className="hint">当前没有系统级错误上报。</div>
              )}
            </>
          ) : (
            <div className="hint">系统健康状态加载中...</div>
          )}
        </section>
      </div>
    );
  }

  function renderCurrentPage() {
    switch (currentNav) {
      case "overview":
        return renderOverviewPage();
      case "market":
        return renderMarketPage();
      case "strategy":
        return renderStrategyPage();
      case "backtest":
        return renderBacktestPage();
      case "run":
        return renderRunPage();
      case "notification":
        return renderNotificationPage();
      case "system":
        return renderSystemPage();
      default:
        return renderOverviewPage();
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <h1>交易模拟平台</h1>
          <p>Multi-Asset Sim Platform</p>
        </div>
        <nav className="nav-list" aria-label="主导航">
          {navItems.map((item) => (
            <button
              type="button"
              key={item.key}
              className={`nav-item ${currentNav === item.key ? "active" : ""}`}
              onClick={() => setCurrentNav(item.key)}
            >
              <strong>{item.label}</strong>
              <span>{item.desc}</span>
              {item.key === "notification" && unreadCount > 0 ? <em>{unreadCount}</em> : null}
            </button>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{activeNavItem.label}</h2>
            <p>{activeNavItem.desc}</p>
          </div>
          <div className="topbar-right">
            <label>
              当前标的
              <select value={activeSymbol} onChange={(event) => setActiveSymbol(event.target.value)}>
                {symbols.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.code}
                  </option>
                ))}
              </select>
            </label>
            <label>
              周期
              <select value={activeInterval} onChange={(event) => setActiveInterval(event.target.value as (typeof intervals)[number])}>
                {intervals.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            {quote ? (
              <div className="price-chip">
                <span>{formatNumber(quote.last, 4)}</span>
                <small className={quote.change >= 0 ? "up" : "down"}>{formatNumber(quote.change_percent, 2)}%</small>
              </div>
            ) : null}
          </div>
        </header>

        <main className="content-area">{renderCurrentPage()}</main>
      </section>
    </div>
  );
}
