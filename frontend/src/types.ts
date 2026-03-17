export type MarketType = "US_EQUITY" | "CRYPTO";
export type DataState = "REALTIME" | "DELAYED" | "DISCONNECTED" | "RESERVED";

export interface SymbolView {
  code: string;
  name: string;
  market: MarketType;
  datasource: string;
  data_state: DataState;
  data_detail: string;
  session: string;
  session_label: string;
}

export interface DataSourceStatus {
  name: string;
  state: DataState;
  detail: string;
  checked_at: string;
}

export interface MarketQuote {
  symbol: string;
  last: number;
  change: number;
  change_percent: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
  state: DataState;
  detail: string;
}

export interface MarketOverview {
  symbol: string;
  market: MarketType;
  session: string;
  session_label: string;
  quote: MarketQuote;
}

export interface Kline {
  open_time: string;
  close_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoryDataset {
  symbol: string;
  interval: string;
  source: string;
  updated_at: string;
  missing_points: number;
  has_missing: boolean;
  candles: Kline[];
}
