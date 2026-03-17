import type { DataSourceStatus, HistoryDataset, Kline, MarketOverview, SymbolView } from "./types";

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
