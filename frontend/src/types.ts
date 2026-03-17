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
