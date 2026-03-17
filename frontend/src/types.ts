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

export type StrategyTemplate =
  | "MA_CROSS"
  | "RSI_REVERSAL"
  | "MACD_TREND"
  | "BOLL_BREAKOUT"
  | "RANGE_BREAKOUT";

export interface StrategyPayload {
  name: string;
  template: StrategyTemplate;
  interval: string;
  open_condition: string;
  close_condition: string;
  take_profit: number;
  stop_loss: number;
  position_size: number;
  direction: {
    allow_long: boolean;
    allow_short: boolean;
    include_extended_hours: boolean;
  };
  json_dsl: string;
}

export interface StrategyRecord {
  id: string;
  name: string;
  current_version: number;
  updated_at: string;
  latest_payload: StrategyPayload;
}

export interface BacktestRequest {
  strategy_id: string;
  symbol: string;
  interval: string;
  initial_capital: number;
  fee_rate: number;
  slippage_rate: number;
  allow_long: boolean;
  allow_short: boolean;
  include_extended_hours: boolean;
}

export interface BacktestTrade {
  side: string;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  qty: number;
  pnl: number;
  reason: string;
}

export interface EquityPoint {
  time: string;
  equity: number;
}

export interface BacktestResult {
  symbol: string;
  interval: string;
  metrics: {
    total_return: number;
    annual_return: number;
    max_drawdown: number;
    win_rate: number;
    trade_count: number;
    profit_loss_ratio: number;
    profit_factor: number;
  };
  trades: BacktestTrade[];
  equity_curve: EquityPoint[];
}

export type RunStatus = "PENDING" | "RUNNING" | "PAUSED" | "STOPPED" | "ERROR";

export interface RunInstancePayload {
  name: string;
  strategy_id: string;
  symbol: string;
  interval: string;
  fee_rate: number;
  slippage_rate: number;
  risk_limit: number;
  notify_in_app: boolean;
}

export interface RunInstance {
  id: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  payload: RunInstancePayload;
}

export interface SignalRecord {
  id: string;
  run_instance_id: string;
  strategy_id: string;
  symbol: string;
  interval: string;
  signal_type: "OPEN_LONG" | "CLOSE_LONG" | "OPEN_SHORT" | "CLOSE_SHORT";
  trigger_time: string;
  trigger_price: number;
  reason_snapshot: string;
}

export interface NotificationRecord {
  id: string;
  type: "SIGNAL" | "SYSTEM" | "DATASOURCE";
  title: string;
  content: string;
  created_at: string;
  read: boolean;
}
