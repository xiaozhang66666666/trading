"""Simple bar-by-bar backtesting engine."""

from __future__ import annotations

import pandas as pd

from market_signal_system.backtest.metrics import summarize_metrics
from market_signal_system.backtest.models import BacktestConfig, BacktestResult
from market_signal_system.strategies.base import Strategy


class BacktestEngine:
    """Backtest with t-1 signal execution and explicit costs."""

    def __init__(
        self,
        fee_rate: float = 0.0008,
        slippage_bps: float = 5.0,
        bars_per_year: int = 252,
        max_drawdown: float | None = None,
        cooldown_bars: int = 20,
    ) -> None:
        self.config = BacktestConfig(
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            bars_per_year=bars_per_year,
            max_drawdown=max_drawdown,
            cooldown_bars=cooldown_bars,
        )

    def run(self, data: pd.DataFrame, strategy: Strategy, symbol: str) -> BacktestResult:
        if len(data) < 10:
            raise ValueError("Not enough bars for backtest.")

        close = data["close"].astype(float)
        open_ = data["open"].astype(float)
        explain = strategy.explain(data).reindex(data.index)
        explain_signals = explain.get("signal", strategy.generate_signals(data)).fillna(0).clip(-1, 1).astype(int)
        signals = explain_signals
        explain = explain.copy()
        explain["signal"] = signals
        if "reason" not in explain.columns:
            explain["reason"] = signals.map({1: "long_signal", -1: "short_signal", 0: "flat_signal"})

        # 避免未来函数：t-1 信号在 t 开盘执行，因此持仓先 shift(1)。
        target_positions = signals.shift(1).fillna(0).astype(int)
        target_positions = self._apply_drawdown_guard(
            positions=target_positions,
            asset_returns=close.pct_change().fillna(0.0),
            one_side_cost=self.config.fee_rate + self.config.slippage_bps / 10000.0,
            max_drawdown=self.config.max_drawdown,
            cooldown_bars=self.config.cooldown_bars,
        )
        turnovers = target_positions.diff().abs().fillna(target_positions.abs()).astype(float)

        asset_returns = close.pct_change().fillna(0.0)
        gross_returns = target_positions * asset_returns

        one_side_cost = self.config.fee_rate + self.config.slippage_bps / 10000.0
        costs = turnovers * one_side_cost
        net_returns = (gross_returns - costs).rename("returns")
        equity = (1.0 + net_returns).cumprod().rename("equity")
        benchmark_positions = pd.Series(1, index=data.index, dtype=int).shift(1).fillna(0).astype(int)
        benchmark_turnovers = benchmark_positions.diff().abs().fillna(benchmark_positions.abs()).astype(float)
        benchmark_returns = (benchmark_positions * asset_returns - benchmark_turnovers * one_side_cost).rename(
            "benchmark_returns"
        )
        benchmark_equity = (1.0 + benchmark_returns).cumprod().rename("benchmark_equity")

        trades_df = self._build_trades(data.index, open_, target_positions, one_side_cost)
        trade_pnls = trades_df["pnl"].tolist() if not trades_df.empty else []
        metrics = summarize_metrics(
            net_returns,
            equity,
            trade_pnls,
            benchmark_returns=benchmark_returns,
            benchmark_equity_curve=benchmark_equity,
            bars_per_year=self.config.bars_per_year,
        )

        return BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            equity_curve=equity,
            returns=net_returns,
            positions=target_positions.rename("position"),
            signals=signals.rename("signal"),
            signal_explain=explain,
            trades=trades_df,
            metrics=metrics,
        )

    @staticmethod
    def _build_trades(
        index: pd.Index,
        open_price: pd.Series,
        positions: pd.Series,
        one_side_cost: float,
    ) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        current_side = 0
        entry_time: pd.Timestamp | None = None
        entry_price = 0.0

        for ts in index:
            side = int(positions.loc[ts])
            px = float(open_price.loc[ts])
            if current_side == 0 and side != 0:
                current_side = side
                entry_time = ts
                entry_price = px
                continue

            if current_side != 0 and side != current_side:
                pnl = ((px - entry_price) / entry_price) * current_side - (2 * one_side_cost)
                rows.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "side": current_side,
                        "entry_price": entry_price,
                        "exit_price": px,
                        "pnl": float(pnl),
                    }
                )
                if side == 0:
                    current_side = 0
                    entry_time = None
                    entry_price = 0.0
                else:
                    current_side = side
                    entry_time = ts
                    entry_price = px

        if current_side != 0 and entry_time is not None:
            ts = index[-1]
            px = float(open_price.iloc[-1])
            pnl = ((px - entry_price) / entry_price) * current_side - (2 * one_side_cost)
            rows.append(
                {
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "side": current_side,
                    "entry_price": entry_price,
                    "exit_price": px,
                    "pnl": float(pnl),
                }
            )

        return pd.DataFrame(rows)

    @staticmethod
    def _apply_drawdown_guard(
        positions: pd.Series,
        asset_returns: pd.Series,
        one_side_cost: float,
        max_drawdown: float | None,
        cooldown_bars: int,
    ) -> pd.Series:
        if max_drawdown is None:
            return positions
        if not 0 < max_drawdown < 1:
            raise ValueError("max_drawdown must be between 0 and 1.")
        if cooldown_bars < 1:
            raise ValueError("cooldown_bars must be >= 1.")

        turnovers = positions.diff().abs().fillna(positions.abs()).astype(float)
        raw_returns = positions * asset_returns - turnovers * one_side_cost
        raw_equity = (1.0 + raw_returns).cumprod()
        drawdown = (raw_equity / raw_equity.cummax() - 1.0).shift(1).fillna(0.0)

        protected: list[int] = []
        lock = 0
        for ts, side in positions.items():
            if lock > 0:
                protected.append(0)
                lock -= 1
                continue

            if float(drawdown.loc[ts]) <= -max_drawdown:
                protected.append(0)
                lock = cooldown_bars
                continue

            protected.append(int(side))

        return pd.Series(protected, index=positions.index, name=positions.name, dtype=int)
