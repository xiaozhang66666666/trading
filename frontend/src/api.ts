import type { DataSourceStatus, Kline, MarketOverview, SymbolView } from "./types";

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
