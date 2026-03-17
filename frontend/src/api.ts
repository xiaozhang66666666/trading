import type {
  BacktestRequest,
  BacktestResult,
  DataSourceStatus,
  HistoryDataset,
  Kline,
  MarketOverview,
  StrategyPayload,
  StrategyRecord,
  RunInstance,
  RunInstancePayload,
  NotificationRecord,
  PnlSummary,
  PositionLog,
  SignalRecord,
  SystemHealth,
  SystemSettings,
  TradeLog,
  SymbolView,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function searchSymbols(q: string): Promise<SymbolView[]> {
  const query = new URLSearchParams({ q });
  return fetchJson<SymbolView[]>(`/api/v1/symbols/search?${query.toString()}`);
}

export function getDataSources(): Promise<DataSourceStatus[]> {
  return fetchJson<DataSourceStatus[]>("/api/v1/data-sources/status");
}

export function getMarketOverview(symbol: string): Promise<MarketOverview> {
  const query = new URLSearchParams({ symbol });
  return fetchJson<MarketOverview>(`/api/v1/market/overview?${query.toString()}`);
}

export function getMarketKlines(symbol: string, interval: string, limit = 200): Promise<Kline[]> {
  const query = new URLSearchParams({ symbol, interval, limit: String(limit) });
  return fetchJson<Kline[]>(`/api/v1/market/klines?${query.toString()}`);
}

export function getHistoryKlines(symbol: string, interval: string, refresh = false): Promise<HistoryDataset> {
  const query = new URLSearchParams({ symbol, interval, limit: "500", refresh: String(refresh) });
  return fetchJson<HistoryDataset>(`/api/v1/history/klines?${query.toString()}`);
}

export function refreshHistoryKlines(symbol: string, interval: string): Promise<HistoryDataset> {
  const query = new URLSearchParams({ symbol, interval, limit: "500" });
  return fetchJson<HistoryDataset>(`/api/v1/history/refresh?${query.toString()}`, { method: "POST" });
}

export function buildHistoryDownloadUrl(symbol: string, interval: string, format: "csv" | "parquet"): string {
  const query = new URLSearchParams({ symbol, interval, limit: "500" });
  return `${API_BASE}/api/v1/history/download.${format}?${query.toString()}`;
}

export function listStrategies(): Promise<StrategyRecord[]> {
  return fetchJson<StrategyRecord[]>("/api/v1/strategies");
}

export function createStrategy(payload: StrategyPayload): Promise<StrategyRecord> {
  return fetchJson<StrategyRecord>("/api/v1/strategies", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function copyStrategy(strategyId: string): Promise<StrategyRecord> {
  return fetchJson<StrategyRecord>(`/api/v1/strategies/${strategyId}/copy`, {
    method: "POST",
  });
}

export function deleteStrategy(strategyId: string): Promise<{ status: string }> {
  return fetchJson<{ status: string }>(`/api/v1/strategies/${strategyId}`, {
    method: "DELETE",
  });
}

export function runBacktest(payload: BacktestRequest): Promise<BacktestResult> {
  return fetchJson<BacktestResult>("/api/v1/backtests/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listRuns(): Promise<RunInstance[]> {
  return fetchJson<RunInstance[]>("/api/v1/runs");
}

export function createRun(payload: RunInstancePayload): Promise<RunInstance> {
  return fetchJson<RunInstance>("/api/v1/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function copyRun(runId: string): Promise<RunInstance> {
  return fetchJson<RunInstance>(`/api/v1/runs/${runId}/copy`, {
    method: "POST",
  });
}

export function changeRunStatus(runId: string, action: "start" | "pause" | "stop"): Promise<RunInstance> {
  return fetchJson<RunInstance>(`/api/v1/runs/${runId}/${action}`, { method: "POST" });
}

export function deleteRun(runId: string): Promise<{ status: string }> {
  return fetchJson<{ status: string }>(`/api/v1/runs/${runId}`, { method: "DELETE" });
}

export function tickSignalEngine(): Promise<SignalRecord[]> {
  return fetchJson<SignalRecord[]>("/api/v1/signal-engine/tick", { method: "POST" });
}

export function listSignals(): Promise<SignalRecord[]> {
  return fetchJson<SignalRecord[]>("/api/v1/signal-engine/signals");
}

export function listNotifications(): Promise<NotificationRecord[]> {
  return fetchJson<NotificationRecord[]>("/api/v1/notifications");
}

export function markNotificationsRead(ids: string[]): Promise<{ status: string }> {
  return fetchJson<{ status: string }>("/api/v1/notifications/mark-read", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export function checkDatasourceNotifications(): Promise<{ created: number }> {
  return fetchJson<{ created: number }>("/api/v1/notifications/check-datasource", {
    method: "POST",
  });
}

export function listPositionLogs(): Promise<PositionLog[]> {
  return fetchJson<PositionLog[]>("/api/v1/logs/positions");
}

export function listTradeLogs(): Promise<TradeLog[]> {
  return fetchJson<TradeLog[]>("/api/v1/logs/trades");
}

export function getPnlSummary(): Promise<PnlSummary> {
  return fetchJson<PnlSummary>("/api/v1/logs/pnl");
}

export function buildLogsExportUrl(): string {
  return `${API_BASE}/api/v1/logs/export.csv`;
}

export function getSystemSettings(): Promise<SystemSettings> {
  return fetchJson<SystemSettings>("/api/v1/system/settings");
}

export function updateSystemSettings(payload: SystemSettings): Promise<SystemSettings> {
  return fetchJson<SystemSettings>("/api/v1/system/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getSystemHealth(): Promise<SystemHealth> {
  return fetchJson<SystemHealth>("/api/v1/system/health");
}
