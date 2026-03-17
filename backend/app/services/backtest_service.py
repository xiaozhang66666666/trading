from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from app.core.models import (
    BacktestCompareItem,
    BacktestCompareRequest,
    BacktestCompareResult,
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    BacktestScanItem,
    BacktestScanRequest,
    BacktestScanResult,
    BacktestTrade,
    EquityPoint,
    Kline,
    PortfolioBacktestRequest,
    PortfolioBacktestResult,
    PortfolioItemResult,
    ScanRange,
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

    @staticmethod
    def _range_values(scan: ScanRange) -> list[float]:
        if scan.step <= 0:
            raise ValueError("参数扫描步长必须大于0")
        if scan.end < scan.start:
            raise ValueError("参数扫描结束值不能小于起始值")
        values: list[float] = []
        current = scan.start
        while current <= scan.end + 1e-12:
            values.append(round(current, 10))
            current += scan.step
        return values

    @staticmethod
    def _metric_value(metrics: BacktestMetrics, key: str) -> float:
        if key == "max_drawdown":
            return -metrics.max_drawdown
        return {
            "total_return": metrics.total_return,
            "annual_return": metrics.annual_return,
            "win_rate": metrics.win_rate,
            "trade_count": float(metrics.trade_count),
            "profit_factor": metrics.profit_factor,
            "profit_loss_ratio": metrics.profit_loss_ratio,
            "max_drawdown": -metrics.max_drawdown,
        }.get(key, metrics.total_return)

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

    async def scan(self, request: BacktestScanRequest, symbol: Symbol, strategy: StrategyRecord) -> BacktestScanResult:
        fee_values = self._range_values(request.fee_rate)
        slip_values = self._range_values(request.slippage_rate)

        items: list[BacktestScanItem] = []
        for fee in fee_values:
            for slip in slip_values:
                result = await self.run(
                    BacktestRequest(
                        strategy_id=request.strategy_id,
                        symbol=request.symbol,
                        interval=request.interval,
                        initial_capital=request.initial_capital,
                        fee_rate=fee,
                        slippage_rate=slip,
                        allow_long=request.allow_long,
                        allow_short=request.allow_short,
                        include_extended_hours=request.include_extended_hours,
                    ),
                    symbol=symbol,
                    strategy=strategy,
                )
                items.append(
                    BacktestScanItem(
                        fee_rate=fee,
                        slippage_rate=slip,
                        metrics=result.metrics,
                    )
                )

        sorted_items = sorted(
            items,
            key=lambda item: self._metric_value(item.metrics, request.sort_by),
            reverse=True,
        )
        top_n = max(1, request.top_n)
        return BacktestScanResult(
            symbol=request.symbol,
            interval=request.interval,
            scanned_count=len(items),
            sort_by=request.sort_by,
            items=sorted_items[:top_n],
        )

    async def compare(
        self,
        request: BacktestCompareRequest,
        symbol: Symbol,
        strategies: list[StrategyRecord],
    ) -> BacktestCompareResult:
        items: list[BacktestCompareItem] = []
        for strategy in strategies:
            result = await self.run(
                BacktestRequest(
                    strategy_id=strategy.id,
                    symbol=request.symbol,
                    interval=request.interval,
                    initial_capital=request.initial_capital,
                    fee_rate=request.fee_rate,
                    slippage_rate=request.slippage_rate,
                    allow_long=request.allow_long,
                    allow_short=request.allow_short,
                    include_extended_hours=request.include_extended_hours,
                ),
                symbol=symbol,
                strategy=strategy,
            )
            items.append(BacktestCompareItem(strategy_id=strategy.id, strategy_name=strategy.name, metrics=result.metrics))

        items.sort(key=lambda item: self._metric_value(item.metrics, request.sort_by), reverse=True)
        return BacktestCompareResult(symbol=request.symbol, interval=request.interval, sort_by=request.sort_by, items=items)

    @staticmethod
    def _max_drawdown(equities: list[float]) -> float:
        if not equities:
            return 0.0
        peak = equities[0]
        max_dd = 0.0
        for value in equities:
            peak = max(peak, value)
            dd = (peak - value) / peak if peak else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    async def run_portfolio(
        self,
        request: PortfolioBacktestRequest,
        symbols: list[Symbol],
        strategy: StrategyRecord,
    ) -> PortfolioBacktestResult:
        results: list[BacktestResult] = []
        item_results: list[PortfolioItemResult] = []
        for symbol in symbols:
            single = await self.run(
                BacktestRequest(
                    strategy_id=request.strategy_id,
                    symbol=symbol.code,
                    interval=request.interval,
                    initial_capital=request.initial_capital,
                    fee_rate=request.fee_rate,
                    slippage_rate=request.slippage_rate,
                    allow_long=request.allow_long,
                    allow_short=request.allow_short,
                    include_extended_hours=request.include_extended_hours,
                ),
                symbol=symbol,
                strategy=strategy,
            )
            results.append(single)
            item_results.append(
                PortfolioItemResult(
                    symbol=symbol.code,
                    metrics=single.metrics,
                    trades=single.metrics.trade_count,
                )
            )

        if not results:
            empty_metrics = BacktestMetrics(
                total_return=0,
                annual_return=0,
                max_drawdown=0,
                win_rate=0,
                trade_count=0,
                profit_loss_ratio=0,
                profit_factor=0,
            )
            return PortfolioBacktestResult(
                strategy_id=request.strategy_id,
                symbols=[],
                interval=request.interval,
                portfolio_metrics=empty_metrics,
                portfolio_equity_curve=[],
                items=[],
            )

        min_length = min((len(item.equity_curve) for item in results), default=0)
        curve: list[EquityPoint] = []
        if min_length > 0:
            for idx in range(min_length):
                returns = [(result.equity_curve[idx].equity / request.initial_capital) - 1 for result in results]
                avg_return = sum(returns) / len(returns)
                equity = request.initial_capital * (1 + avg_return)
                curve.append(EquityPoint(time=results[0].equity_curve[idx].time, equity=equity))

        portfolio_total_return = 0.0
        if curve and request.initial_capital:
            portfolio_total_return = (curve[-1].equity - request.initial_capital) / request.initial_capital
        weighted_trade_count = sum(item.metrics.trade_count for item in results)
        weighted_win = sum(item.metrics.win_rate * item.metrics.trade_count for item in results)
        win_rate = (weighted_win / weighted_trade_count) if weighted_trade_count else 0.0
        avg_profit_factor = sum(item.metrics.profit_factor for item in results) / len(results)
        avg_pl_ratio = sum(item.metrics.profit_loss_ratio for item in results) / len(results)
        max_drawdown = self._max_drawdown([point.equity for point in curve])

        portfolio_metrics = BacktestMetrics(
            total_return=portfolio_total_return,
            annual_return=portfolio_total_return * sqrt(365) if portfolio_total_return > -1 else -1,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            trade_count=weighted_trade_count,
            profit_loss_ratio=avg_pl_ratio,
            profit_factor=avg_profit_factor,
        )

        return PortfolioBacktestResult(
            strategy_id=request.strategy_id,
            symbols=[symbol.code for symbol in symbols],
            interval=request.interval,
            portfolio_metrics=portfolio_metrics,
            portfolio_equity_curve=curve,
            items=item_results,
        )
