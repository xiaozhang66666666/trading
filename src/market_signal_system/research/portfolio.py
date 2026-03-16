"""Portfolio-level backtest utilities."""

from __future__ import annotations

import pandas as pd
import numpy as np
from itertools import combinations

from market_signal_system.backtest.metrics import summarize_metrics
from market_signal_system.strategies import get_strategy


def run_portfolio_backtest(
    data_manager,
    symbols: list[str],
    strategy_name: str,
    start: str,
    end: str,
    interval: str = "1d",
    strategy_params: dict | None = None,
    fee_rate: float = 0.0008,
    slippage_bps: float = 5.0,
    bars_per_year: int = 252,
    allocation_mode: str = "equal",
    vol_window: int = 20,
    target_vol: float = 0.15,
    max_leverage: float = 1.5,
    corr_watch_threshold: float = 0.75,
    corr_high_threshold: float = 0.85,
    crowding_watch_threshold: float = 0.15,
    crowding_high_threshold: float = 0.2,
    drift_watch_threshold: float = 0.08,
    drift_high_threshold: float = 0.15,
    rebalance_on_drift: bool = False,
    rebalance_trigger: str = "high",
    rebalance_scale: float = 1.0,
) -> tuple[dict[str, float], pd.Series, pd.DataFrame]:
    metrics, equity, exposures, _ = run_portfolio_backtest_detailed(
        data_manager=data_manager,
        symbols=symbols,
        strategy_name=strategy_name,
        start=start,
        end=end,
        interval=interval,
        strategy_params=strategy_params,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        bars_per_year=bars_per_year,
        allocation_mode=allocation_mode,
        vol_window=vol_window,
        target_vol=target_vol,
        max_leverage=max_leverage,
        corr_watch_threshold=corr_watch_threshold,
        corr_high_threshold=corr_high_threshold,
        crowding_watch_threshold=crowding_watch_threshold,
        crowding_high_threshold=crowding_high_threshold,
        drift_watch_threshold=drift_watch_threshold,
        drift_high_threshold=drift_high_threshold,
        rebalance_on_drift=rebalance_on_drift,
        rebalance_trigger=rebalance_trigger,
        rebalance_scale=rebalance_scale,
    )
    return metrics, equity, exposures


def run_portfolio_backtest_detailed(
    data_manager,
    symbols: list[str],
    strategy_name: str,
    start: str,
    end: str,
    interval: str = "1d",
    strategy_params: dict | None = None,
    fee_rate: float = 0.0008,
    slippage_bps: float = 5.0,
    bars_per_year: int = 252,
    allocation_mode: str = "equal",
    vol_window: int = 20,
    target_vol: float = 0.15,
    max_leverage: float = 1.5,
    corr_watch_threshold: float = 0.75,
    corr_high_threshold: float = 0.85,
    crowding_watch_threshold: float = 0.15,
    crowding_high_threshold: float = 0.2,
    drift_watch_threshold: float = 0.08,
    drift_high_threshold: float = 0.15,
    rebalance_on_drift: bool = False,
    rebalance_trigger: str = "high",
    rebalance_scale: float = 1.0,
) -> tuple[dict[str, float], pd.Series, pd.DataFrame, dict[str, pd.DataFrame]]:
    if not symbols:
        raise ValueError("symbols cannot be empty")
    if vol_window < 2:
        raise ValueError("vol_window must be >= 2")
    if target_vol <= 0:
        raise ValueError("target_vol must be > 0")
    if max_leverage <= 0:
        raise ValueError("max_leverage must be > 0")
    if not 0 <= corr_watch_threshold <= 1:
        raise ValueError("corr_watch_threshold must be in [0, 1]")
    if not 0 <= corr_high_threshold <= 1:
        raise ValueError("corr_high_threshold must be in [0, 1]")
    if not 0 <= crowding_watch_threshold <= 1:
        raise ValueError("crowding_watch_threshold must be in [0, 1]")
    if not 0 <= crowding_high_threshold <= 1:
        raise ValueError("crowding_high_threshold must be in [0, 1]")
    if not 0 <= drift_watch_threshold <= 1:
        raise ValueError("drift_watch_threshold must be in [0, 1]")
    if not 0 <= drift_high_threshold <= 1:
        raise ValueError("drift_high_threshold must be in [0, 1]")
    if corr_watch_threshold > corr_high_threshold:
        raise ValueError("corr_watch_threshold cannot exceed corr_high_threshold")
    if crowding_watch_threshold > crowding_high_threshold:
        raise ValueError("crowding_watch_threshold cannot exceed crowding_high_threshold")
    if drift_watch_threshold > drift_high_threshold:
        raise ValueError("drift_watch_threshold cannot exceed drift_high_threshold")
    trigger = rebalance_trigger.strip().lower()
    if trigger not in {"high", "watch"}:
        raise ValueError("rebalance_trigger must be 'high' or 'watch'")
    if rebalance_scale < 0:
        raise ValueError("rebalance_scale must be >= 0")

    strategy_params = strategy_params or {}
    one_side_cost = fee_rate + slippage_bps / 10000.0

    if hasattr(data_manager, "get_aligned_history"):
        aligned_data = data_manager.get_aligned_history(
            symbols=symbols,
            start=start,
            end=end,
            interval=interval,
        )
    else:
        raw_frames = {
            symbol: data_manager.get_history(symbol=symbol, start=start, end=end, interval=interval)
            for symbol in symbols
        }
        common_index: pd.DatetimeIndex | None = None
        for frame in raw_frames.values():
            common_index = frame.index if common_index is None else common_index.intersection(frame.index)
        if common_index is None or len(common_index) == 0:
            raise ValueError("symbols have no aligned timestamp range")
        aligned_data = {symbol: frame.loc[common_index].copy() for symbol, frame in raw_frames.items()}
    close_frames: dict[str, pd.Series] = {}
    pos_frames: dict[str, pd.Series] = {}
    trade_pnls: list[float] = []

    for symbol in symbols:
        data = aligned_data[symbol]
        strategy = get_strategy(strategy_name, **strategy_params)
        signal = strategy.generate_signals(data).fillna(0).clip(-1, 1).astype(int)
        position = signal.shift(1).fillna(0).astype(int)

        close = data["close"].astype(float)
        close_frames[symbol] = close
        pos_frames[symbol] = position
        trade_pnls.extend(_extract_trade_pnls(close=close, position=position, one_side_cost=one_side_cost))

    close_df = pd.concat(close_frames, axis=1, join="inner").sort_index()
    pos_df = pd.concat(pos_frames, axis=1, join="inner").sort_index().reindex(close_df.index).fillna(0).astype(int)
    returns_df = close_df.pct_change().fillna(0.0)

    weights = _build_weights(
        positions=pos_df,
        returns_df=returns_df,
        allocation_mode=allocation_mode,
        vol_window=vol_window,
        target_vol=target_vol,
        max_leverage=max_leverage,
    )
    drift = _build_weight_drift_table(
        weights=weights,
        returns_df=returns_df,
        drift_watch_threshold=drift_watch_threshold,
        drift_high_threshold=drift_high_threshold,
    )
    rebalance_actions = _build_drift_rebalance_actions(
        drift=drift,
        trigger=trigger,
        enabled=rebalance_on_drift,
        one_side_cost=one_side_cost,
        scale=rebalance_scale,
    )
    extra_turnover = rebalance_actions["rebalance_turnover"].reindex(weights.index).fillna(0.0)

    turnover_by_symbol = weights.diff().abs().fillna(weights.abs())
    turnover = turnover_by_symbol.sum(axis=1)
    gross = (weights * returns_df).sum(axis=1)
    costs = (turnover + extra_turnover) * one_side_cost
    net_returns = (gross - costs).rename("portfolio_returns")
    equity = (1.0 + net_returns).cumprod().rename("portfolio_equity")
    benchmark_weights = pd.DataFrame(
        1.0 / len(symbols),
        index=returns_df.index,
        columns=returns_df.columns,
    ).shift(1).fillna(0.0)
    benchmark_turnover = benchmark_weights.diff().abs().fillna(benchmark_weights.abs()).sum(axis=1)
    benchmark_gross = (benchmark_weights * returns_df).sum(axis=1)
    benchmark_returns = (benchmark_gross - benchmark_turnover * one_side_cost).rename("benchmark_returns")
    benchmark_equity = (1.0 + benchmark_returns).cumprod().rename("benchmark_equity")

    metrics = summarize_metrics(
        returns=net_returns,
        equity_curve=equity,
        trade_pnls=trade_pnls,
        benchmark_returns=benchmark_returns,
        benchmark_equity_curve=benchmark_equity,
        bars_per_year=bars_per_year,
    )
    metrics["drift_rebalance_enabled"] = bool(rebalance_on_drift)
    metrics["drift_rebalance_turnover_total"] = float(extra_turnover.sum())
    metrics["drift_rebalance_cost_total"] = float((extra_turnover * one_side_cost).sum())
    metrics["drift_rebalance_event_count"] = int((rebalance_actions["triggered"] == 1).sum())

    exposures = pd.concat(
        [
            pos_df.rename(columns=lambda x: f"{x}_position"),
            weights.rename(columns=lambda x: f"{x}_weight"),
        ],
        axis=1,
    )

    gross_contrib = weights * returns_df
    cost_contrib = turnover_by_symbol * one_side_cost
    net_contrib = (gross_contrib - cost_contrib).rename(columns=lambda x: f"{x}_net_contrib")
    attribution = pd.DataFrame(
        {
            "total_contribution": net_contrib.sum(axis=0).values,
            "annualized_vol_contribution": (net_contrib.std(ddof=0) * (bars_per_year**0.5)).values,
            "total_turnover": turnover_by_symbol.sum(axis=0).values,
            "avg_abs_weight": weights.abs().mean(axis=0).values,
        },
        index=weights.columns,
    )
    attribution.index.name = "symbol"
    detail = {
        "net_contrib": net_contrib,
        "attribution": attribution.reset_index(),
        "alerts": _build_correlation_alerts(
            weights=weights,
            returns_df=returns_df,
            vol_window=vol_window,
            corr_watch_threshold=corr_watch_threshold,
            corr_high_threshold=corr_high_threshold,
            crowding_watch_threshold=crowding_watch_threshold,
            crowding_high_threshold=crowding_high_threshold,
        ),
        "weights": weights.rename(columns=lambda x: f"{x}_weight"),
        "drift": drift,
        "rebalance": rebalance_actions,
    }
    return metrics, equity, exposures, detail


def run_equal_weight_portfolio(
    data_manager,
    symbols: list[str],
    strategy_name: str,
    start: str,
    end: str,
    interval: str = "1d",
    strategy_params: dict | None = None,
    fee_rate: float = 0.0008,
    slippage_bps: float = 5.0,
    bars_per_year: int = 252,
) -> tuple[dict[str, float], pd.Series, pd.DataFrame]:
    return run_portfolio_backtest(
        data_manager=data_manager,
        symbols=symbols,
        strategy_name=strategy_name,
        start=start,
        end=end,
        interval=interval,
        strategy_params=strategy_params,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        bars_per_year=bars_per_year,
        allocation_mode="equal",
    )


def _build_weights(
    positions: pd.DataFrame,
    returns_df: pd.DataFrame,
    allocation_mode: str,
    vol_window: int,
    target_vol: float,
    max_leverage: float,
) -> pd.DataFrame:
    mode = allocation_mode.lower().strip()
    if mode not in {"equal", "risk_parity", "vol_target", "cov_risk_parity", "cov_vol_target"}:
        raise ValueError(
            "allocation_mode must be one of: equal, risk_parity, vol_target, cov_risk_parity, cov_vol_target"
        )

    active_mask = positions.ne(0).astype(float)
    sign_df = positions.astype(float)

    # 仅在有信号的标的间分配权重；无信号时保持空仓（全 0 权重）。
    equal_core = active_mask.div(active_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    equal_weights = equal_core * sign_df
    if mode == "equal":
        return equal_weights

    rolling_vol = returns_df.rolling(window=vol_window, min_periods=max(2, vol_window // 2)).std().clip(lower=1e-8)
    inv_vol = (1.0 / rolling_vol).where(active_mask > 0, 0.0)
    rp_core = inv_vol.div(inv_vol.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    rp_weights = rp_core * sign_df
    if mode == "risk_parity":
        return rp_weights

    if mode == "cov_risk_parity":
        return _build_covariance_weights(
            positions=positions,
            returns_df=returns_df,
            vol_window=vol_window,
        )

    base_portfolio_ret = (rp_weights * returns_df).sum(axis=1)
    realized_port_vol = (
        base_portfolio_ret.rolling(window=vol_window, min_periods=max(2, vol_window // 2)).std() * (252**0.5)
    )
    leverage = (
        target_vol / realized_port_vol.shift(1).replace(0, np.nan)
    ).clip(lower=0.0, upper=max_leverage).fillna(0.0)
    if mode == "vol_target":
        return rp_weights.mul(leverage, axis=0)

    cov_weights = _build_covariance_weights(
        positions=positions,
        returns_df=returns_df,
        vol_window=vol_window,
    )
    cov_portfolio_ret = (cov_weights * returns_df).sum(axis=1)
    cov_realized_port_vol = (
        cov_portfolio_ret.rolling(window=vol_window, min_periods=max(2, vol_window // 2)).std() * (252**0.5)
    )
    cov_leverage = (
        target_vol / cov_realized_port_vol.shift(1).replace(0, np.nan)
    ).clip(lower=0.0, upper=max_leverage).fillna(0.0)
    return cov_weights.mul(cov_leverage, axis=0)


def _build_covariance_weights(positions: pd.DataFrame, returns_df: pd.DataFrame, vol_window: int) -> pd.DataFrame:
    weights = pd.DataFrame(0.0, index=positions.index, columns=positions.columns)
    min_obs = max(2, vol_window // 2)

    for idx, ts in enumerate(positions.index):
        active = [c for c in positions.columns if positions.loc[ts, c] != 0]
        if not active:
            continue

        # 使用 t-1 及之前窗口估计协方差，避免未来函数。
        start = max(0, idx - vol_window)
        hist = returns_df.iloc[start:idx][active]
        if len(hist) < min_obs:
            base = np.repeat(1.0 / len(active), len(active))
        else:
            cov = hist.cov().fillna(0.0).to_numpy(dtype=float)
            if cov.size == 0:
                base = np.repeat(1.0 / len(active), len(active))
            else:
                inv_cov = np.linalg.pinv(cov)
                raw = inv_cov @ np.ones(len(active))
                raw = np.clip(raw, 0.0, None)
                if raw.sum() <= 0:
                    base = np.repeat(1.0 / len(active), len(active))
                else:
                    base = raw / raw.sum()

        for i, symbol in enumerate(active):
            weights.loc[ts, symbol] = base[i] * np.sign(positions.loc[ts, symbol])
    return weights


def _extract_trade_pnls(close: pd.Series, position: pd.Series, one_side_cost: float) -> list[float]:
    pnls: list[float] = []
    current = 0
    entry = 0.0

    for ts in close.index:
        side = int(position.loc[ts])
        px = float(close.loc[ts])
        if current == 0 and side != 0:
            current = side
            entry = px
            continue

        if current != 0 and side != current:
            pnl = ((px - entry) / entry) * current - (2 * one_side_cost)
            pnls.append(float(pnl))
            if side == 0:
                current = 0
                entry = 0.0
            else:
                current = side
                entry = px

    if current != 0:
        px = float(close.iloc[-1])
        pnl = ((px - entry) / entry) * current - (2 * one_side_cost)
        pnls.append(float(pnl))
    return pnls


def _build_weight_drift_table(
    weights: pd.DataFrame,
    returns_df: pd.DataFrame,
    drift_watch_threshold: float,
    drift_high_threshold: float,
) -> pd.DataFrame:
    prev_target = weights.shift(1).fillna(0.0)
    drift_notional = prev_target * (1.0 + returns_df.fillna(0.0))
    prev_gross = prev_target.abs().sum(axis=1)
    drift_gross = drift_notional.abs().sum(axis=1).replace(0, np.nan)
    scale = (prev_gross / drift_gross).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    drifted_weight = drift_notional.mul(scale, axis=0)

    records: dict[str, pd.Series] = {}
    for symbol in weights.columns:
        target_col = f"{symbol}_target_weight"
        drifted_col = f"{symbol}_drifted_weight"
        gap_col = f"{symbol}_weight_gap"
        records[target_col] = weights[symbol]
        records[drifted_col] = drifted_weight[symbol]
        records[gap_col] = weights[symbol] - drifted_weight[symbol]

    drift_df = pd.DataFrame(records, index=weights.index)
    gap_cols = [c for c in drift_df.columns if c.endswith("_weight_gap")]
    drift_df["abs_weight_gap_sum"] = drift_df[gap_cols].abs().sum(axis=1) if gap_cols else 0.0
    drift_df["drift_alert_level"] = np.where(
        drift_df["abs_weight_gap_sum"] >= drift_high_threshold,
        "high",
        np.where(drift_df["abs_weight_gap_sum"] >= drift_watch_threshold, "watch", "none"),
    )
    return drift_df


def _build_drift_rebalance_actions(
    drift: pd.DataFrame,
    trigger: str,
    enabled: bool,
    one_side_cost: float,
    scale: float,
) -> pd.DataFrame:
    levels = drift["drift_alert_level"].fillna("none").astype(str)
    if enabled:
        if trigger == "watch":
            flags = levels.isin(["watch", "high"])
        else:
            flags = levels.eq("high")
    else:
        flags = pd.Series(False, index=drift.index)
    turnover = drift["abs_weight_gap_sum"].astype(float).where(flags, 0.0) * float(scale)
    cost = turnover * one_side_cost
    return pd.DataFrame(
        {
            "timestamp": drift.index.astype(str),
            "drift_alert_level": levels.values,
            "triggered": flags.astype(int).values,
            "rebalance_turnover": turnover.values,
            "rebalance_cost": cost.values,
        },
        index=drift.index,
    )


def _build_correlation_alerts(
    weights: pd.DataFrame,
    returns_df: pd.DataFrame,
    vol_window: int,
    corr_watch_threshold: float,
    corr_high_threshold: float,
    crowding_watch_threshold: float,
    crowding_high_threshold: float,
) -> pd.DataFrame:
    min_obs = max(2, vol_window // 2)
    records: list[dict[str, float | str]] = []
    cols = list(weights.columns)
    pairs = list(combinations(cols, 2))
    if not pairs:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "pair",
                "corr",
                "weight_a",
                "weight_b",
                "same_direction",
                "crowding_score",
                "alert_level",
            ]
        )

    for idx, ts in enumerate(weights.index):
        start = max(0, idx - vol_window)
        hist = returns_df.iloc[start:idx]
        if len(hist) < min_obs:
            continue
        corr_mat = hist.corr().fillna(0.0)
        for a, b in pairs:
            corr = float(corr_mat.loc[a, b]) if (a in corr_mat.index and b in corr_mat.columns) else 0.0
            wa = float(weights.loc[ts, a])
            wb = float(weights.loc[ts, b])
            same_direction = int(np.sign(wa) == np.sign(wb) and wa != 0 and wb != 0)
            crowding = min(abs(wa), abs(wb))
            if abs(corr) < corr_watch_threshold and crowding < crowding_watch_threshold:
                continue
            level = (
                "high"
                if (
                    abs(corr) >= corr_high_threshold
                    and crowding >= crowding_high_threshold
                    and same_direction == 1
                )
                else "watch"
            )
            records.append(
                {
                    "timestamp": ts.isoformat(),
                    "pair": f"{a}/{b}",
                    "corr": corr,
                    "weight_a": wa,
                    "weight_b": wb,
                    "same_direction": same_direction,
                    "crowding_score": crowding,
                    "alert_level": level,
                }
            )
    return pd.DataFrame(records)
