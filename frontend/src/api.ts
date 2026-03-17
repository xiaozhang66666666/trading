import type { DataSourceStatus, SymbolView } from "./types";

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

export function getWatchlist(): Promise<SymbolView[]> {
  return fetchJson<SymbolView[]>("/api/v1/watchlist");
}

export function addWatchlist(symbol: string): Promise<SymbolView[]> {
  return fetchJson<SymbolView[]>("/api/v1/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
}

export function removeWatchlist(symbol: string): Promise<SymbolView[]> {
  return fetchJson<SymbolView[]>(`/api/v1/watchlist/${symbol}`, {
    method: "DELETE",
  });
}

export function getDataSources(): Promise<DataSourceStatus[]> {
  return fetchJson<DataSourceStatus[]>("/api/v1/data-sources/status");
}
