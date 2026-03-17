from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from app.core.models import (
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
    Kline,
    StrategyRecord,
    StrategyTemplate,
    Symbol,
)
from app.services.market_data_service import MarketDataService


@dataclass
class _Position:
    side: str
    entry_time: str
    entry_price: float
    qty: float


class BacktestService:
    def __init__(self, market_data: MarketDataService) -> None:
        self._market_data = market_data

    @staticmethod
    def _sma(values: list[float], period: int, index: int) -> float | None:
        if index + 1 < period:
            return None
        sample = values[index + 1 - period : index + 1]
        return sum(sample) / period

    @staticmethod
    def _rsi(values: list[float], period: int, index: int) -> float | None:
        if index < period:
            return None
        gains = 0.0
        losses = 0.0
        for i in range(index - period + 1, index + 1):
            delta = values[i] - values[i - 1]
            if delta > 0:
                gains += delta
            elif delta < 0:
                losses += abs(delta)
        if losses == 0:
            return 100.0
        rs = gains / losses
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _ema(values: list[float], period: int) -> list[float]:
        k = 2 / (period + 1)
        result: list[float] = []
        prev = values[0]
        for value in values:
            prev = value * k + prev * (1 - k)
            result.append(prev)
        return result

    def _signal(self, template: StrategyTemplate, candles: list[Kline], index: int) -> tuple[bool, bool, bool, bool]:
        closes = [item.close for item in candles[: index + 1]]
        if len(closes) < 30:
            return (False, False, False, False)

        # 返回开多/平多/开空/平空。
        if template == StrategyTemplate.MA_CROSS:
            fast_now = self._sma(closes, 5, len(closes) - 1)
            slow_now = self._sma(closes, 20, len(closes) - 1)
            fast_prev = self._sma(closes, 5, len(closes) - 2)
            slow_prev = self._sma(closes, 20, len(closes) - 2)
            if None in (fast_now, slow_now, fast_prev, slow_prev):
                return (False, False, False, False)
            open_long = fast_prev <= slow_prev and fast_now > slow_now
            close_long = fast_prev >= slow_prev and fast_now < slow_now
            open_short = close_long
            close_short = open_long
            return (open_long, close_long, open_short, close_short)

        if template == StrategyTemplate.RSI_REVERSAL:
            rsi = self._rsi(closes, 14, len(closes) - 1)
            if rsi is None:
                return (False, False, False, False)
            return (rsi < 30, rsi > 55, rsi > 70, rsi < 45)

        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd = [a - b for a, b in zip(ema12, ema26, strict=False)]
        signal = self._ema(macd, 9)
        if len(signal) < 2:
            return (False, False, False, False)
        open_long = macd[-2] <= signal[-2] and macd[-1] > signal[-1]
        close_long = macd[-2] >= signal[-2] and macd[-1] < signal[-1]
        open_short = close_long
        close_short = open_long
        return (open_long, close_long, open_short, close_short)

    async def run(self, request: BacktestRequest, symbol: Symbol, strategy: StrategyRecord) -> BacktestResult:
        candles = await self._market_data.get_klines(symbol=symbol, interval=request.interval, limit=500)
        if len(candles) < 35:
            return BacktestResult(
                symbol=request.symbol,
                interval=request.interval,
                metrics=BacktestMetrics(
                    total_return=0,
                    annual_return=0,
                    max_drawdown=0,
                    win_rate=0,
                    trade_count=0,
                    profit_loss_ratio=0,
                    profit_factor=0,
                ),
                trades=[],
                equity_curve=[],
            )

        capital = request.initial_capital
        equity_curve: list[EquityPoint] = []
        trades: list[BacktestTrade] = []
        position: _Position | None = None
        winning = 0
        total_profit = 0.0
        total_loss = 0.0
        max_equity = capital
        max_drawdown = 0.0

        for idx in range(1, len(candles)):
            candle = candles[idx]
            open_long, close_long, open_short, close_short = self._signal(strategy.latest_payload.template, candles, idx)
            price = candle.close

            if position is None:
                if request.allow_long and strategy.latest_payload.direction.allow_long and open_long:
                    qty = capital / price
                    position = _Position(side="LONG", entry_time=candle.close_time, entry_price=price, qty=qty)
                elif request.allow_short and strategy.latest_payload.direction.allow_short and open_short:
                    qty = capital / price
                    position = _Position(side="SHORT", entry_time=candle.close_time, entry_price=price, qty=qty)
            else:
                should_close = (position.side == "LONG" and close_long) or (position.side == "SHORT" and close_short)
                if should_close:
                    gross = (price - position.entry_price) * position.qty
                    if position.side == "SHORT":
                        gross = -gross
                    costs = capital * (request.fee_rate + request.slippage_rate)
                    pnl = gross - costs
                    capital += pnl
                    if pnl >= 0:
                        winning += 1
                        total_profit += pnl
                    else:
                        total_loss += abs(pnl)
                    trades.append(
                        BacktestTrade(
                            side=position.side,
                            entry_time=position.entry_time,
                            entry_price=position.entry_price,
                            exit_time=candle.close_time,
                            exit_price=price,
                            qty=position.qty,
                            pnl=pnl,
                            reason=f"{position.side} 信号平仓",
                        )
                    )
                    position = None

            equity = capital
            if position:
                floating = (price - position.entry_price) * position.qty
                equity = capital + (floating if position.side == "LONG" else -floating)
            max_equity = max(max_equity, equity)
            drawdown = (max_equity - equity) / max_equity if max_equity else 0
            max_drawdown = max(max_drawdown, drawdown)
            equity_curve.append(EquityPoint(time=candle.close_time, equity=equity))

        trade_count = len(trades)
        total_return = (capital - request.initial_capital) / request.initial_capital if request.initial_capital else 0
        annual_return = total_return * sqrt(365) if total_return > -1 else -1
        win_rate = winning / trade_count if trade_count else 0
        avg_win = (total_profit / winning) if winning else 0
        losing_count = trade_count - winning
        avg_loss = (total_loss / losing_count) if losing_count else 0
        profit_loss_ratio = (avg_win / avg_loss) if avg_loss else 0
        profit_factor = (total_profit / total_loss) if total_loss else 0

        return BacktestResult(
            symbol=request.symbol,
            interval=request.interval,
            metrics=BacktestMetrics(
                total_return=total_return,
                annual_return=annual_return,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                trade_count=trade_count,
                profit_loss_ratio=profit_loss_ratio,
                profit_factor=profit_factor,
            ),
            trades=trades,
            equity_curve=equity_curve,
        )
