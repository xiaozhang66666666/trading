from __future__ import annotations

from market_signal_system.backtest import BacktestEngine
from market_signal_system.data import DataManager
from market_signal_system.strategies import get_strategy


def print_result(asset: str, strategy_name: str, metrics: dict[str, float]) -> None:
    print(f"[{asset}] {strategy_name}")
    print(
        "  收益={:.2%} 年化={:.2%} Sharpe={:.2f} 回撤={:.2%} Calmar={:.2f} 胜率={:.2%} 交易={:.0f}".format(
            metrics["total_return"],
            metrics["annual_return"],
            metrics["sharpe"],
            metrics["max_drawdown"],
            metrics["calmar"],
            metrics["win_rate"],
            metrics["trade_count"],
        )
    )


def main() -> None:
    dm = DataManager()
    engine = BacktestEngine(fee_rate=0.0008, slippage_bps=5.0)

    strategy_names = ["ma_cross", "donchian", "momentum"]
    for symbol in ["QQQ", "ETH"]:
        df = dm.get_history(symbol=symbol, start="2018-01-01", end="2025-12-31", interval="1d")
        for strategy_name in strategy_names:
            strategy = get_strategy(strategy_name)
            result = engine.run(df, strategy, symbol=symbol)
            print_result(symbol, strategy.name, result.metrics)


if __name__ == "__main__":
    main()
