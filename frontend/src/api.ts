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

const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string; message?: string };
      detail = payload.detail ?? payload.message ?? "";
    } catch {
      try {
        detail = await response.text();
      } catch {
        detail = "";
      }
    }
    throw new Error(detail ? `请求失败: ${response.status} - ${detail}` : `请求失败: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function searchSymbols(q: string): Promise<SymbolView[]> {
  const query = new URLSearchParams({ q });
  return fetchJson<SymbolView[]>(`/v1/symbols/search?${query.toString()}`);
}

export function getDataSources(): Promise<DataSourceStatus[]> {
  return fetchJson<DataSourceStatus[]>("/v1/data-sources/status");
}

export function getMarketOverview(symbol: string): Promise<MarketOverview> {
  const query = new URLSearchParams({ symbol });
  return fetchJson<MarketOverview>(`/v1/market/overview?${query.toString()}`);
}

export function getMarketKlines(symbol: string, interval: string, limit = 200): Promise<Kline[]> {
  const query = new URLSearchParams({ symbol, interval, limit: String(limit) });
  return fetchJson<Kline[]>(`/v1/market/klines?${query.toString()}`);
}

export function getHistoryKlines(symbol: string, interval: string, refresh = false): Promise<HistoryDataset> {
  const query = new URLSearchParams({ symbol, interval, limit: "500", refresh: String(refresh) });
  return fetchJson<HistoryDataset>(`/v1/history/klines?${query.toString()}`);
}

export function refreshHistoryKlines(symbol: string, interval: string): Promise<HistoryDataset> {
  const query = new URLSearchParams({ symbol, interval, limit: "500" });
  return fetchJson<HistoryDataset>(`/v1/history/refresh?${query.toString()}`, { method: "POST" });
}

export function buildHistoryDownloadUrl(symbol: string, interval: string, format: "csv" | "parquet"): string {
  const query = new URLSearchParams({ symbol, interval, limit: "500" });
  return `${API_BASE}/v1/history/download.${format}?${query.toString()}`;
}

export function listStrategies(): Promise<StrategyRecord[]> {
  return fetchJson<StrategyRecord[]>("/v1/strategies");
}

export function createStrategy(payload: StrategyPayload): Promise<StrategyRecord> {
  return fetchJson<StrategyRecord>("/v1/strategies", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function copyStrategy(strategyId: string): Promise<StrategyRecord> {
  return fetchJson<StrategyRecord>(`/v1/strategies/${strategyId}/copy`, {
    method: "POST",
  });
}

export function deleteStrategy(strategyId: string): Promise<{ status: string }> {
  return fetchJson<{ status: string }>(`/v1/strategies/${strategyId}`, {
    method: "DELETE",
  });
}

export function runBacktest(payload: BacktestRequest): Promise<BacktestResult> {
  return fetchJson<BacktestResult>("/v1/backtests/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listRuns(): Promise<RunInstance[]> {
  return fetchJson<RunInstance[]>("/v1/runs");
}

export function createRun(payload: RunInstancePayload): Promise<RunInstance> {
  return fetchJson<RunInstance>("/v1/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function copyRun(runId: string): Promise<RunInstance> {
  return fetchJson<RunInstance>(`/v1/runs/${runId}/copy`, {
    method: "POST",
  });
}

export function changeRunStatus(runId: string, action: "start" | "pause" | "stop"): Promise<RunInstance> {
  return fetchJson<RunInstance>(`/v1/runs/${runId}/${action}`, { method: "POST" });
}

export function deleteRun(runId: string): Promise<{ status: string }> {
  return fetchJson<{ status: string }>(`/v1/runs/${runId}`, { method: "DELETE" });
}

export function tickSignalEngine(): Promise<SignalRecord[]> {
  return fetchJson<SignalRecord[]>("/v1/signal-engine/tick", { method: "POST" });
}

export function listSignals(): Promise<SignalRecord[]> {
  return fetchJson<SignalRecord[]>("/v1/signal-engine/signals");
}

export function listNotifications(): Promise<NotificationRecord[]> {
  return fetchJson<NotificationRecord[]>("/v1/notifications");
}

export function markNotificationsRead(ids: string[]): Promise<{ status: string }> {
  return fetchJson<{ status: string }>("/v1/notifications/mark-read", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export function checkDatasourceNotifications(): Promise<{ created: number }> {
  return fetchJson<{ created: number }>("/v1/notifications/check-datasource", {
    method: "POST",
  });
}

export function listPositionLogs(): Promise<PositionLog[]> {
  return fetchJson<PositionLog[]>("/v1/logs/positions");
}

export function listTradeLogs(): Promise<TradeLog[]> {
  return fetchJson<TradeLog[]>("/v1/logs/trades");
}

export function getPnlSummary(): Promise<PnlSummary> {
  return fetchJson<PnlSummary>("/v1/logs/pnl");
}

export function buildLogsExportUrl(): string {
  return `${API_BASE}/v1/logs/export.csv`;
}

export function getSystemSettings(): Promise<SystemSettings> {
  return fetchJson<SystemSettings>("/v1/system/settings");
}

export function updateSystemSettings(payload: SystemSettings): Promise<SystemSettings> {
  return fetchJson<SystemSettings>("/v1/system/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getSystemHealth(): Promise<SystemHealth> {
  return fetchJson<SystemHealth>("/v1/system/health");
}
