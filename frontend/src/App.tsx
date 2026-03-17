import { useEffect, useMemo, useState } from "react";

import {
  buildHistoryDownloadUrl,
  copyStrategy,
  createStrategy,
  deleteStrategy,
  getDataSources,
  getHistoryKlines,
  listStrategies,
  getMarketKlines,
  getMarketOverview,
  refreshHistoryKlines,
  searchSymbols,
} from "./api";
import type {
  DataSourceStatus,
  DataState,
  HistoryDataset,
  Kline,
  MarketOverview,
  StrategyPayload,
  StrategyRecord,
  StrategyTemplate,
  SymbolView,
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
    setStrategies(await listStrategies());
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
      </aside>
    </div>
  );
}
