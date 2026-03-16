import pandas as pd

from market_signal_system.strategies.atr_regime import AtrRegimeStrategy
from market_signal_system.strategies.donchian import DonchianBreakoutStrategy
from market_signal_system.strategies.dual_momentum import DualMomentumStrategy
from market_signal_system.strategies.macd_regime import MacdRegimeStrategy
from market_signal_system.strategies.momentum import MomentumVolatilityStrategy
from market_signal_system.strategies.momentum_regime import RegimeMomentumStrategy
from market_signal_system.strategies.score_regime import ScoreRegimeStrategy
from market_signal_system.strategies.trend import MovingAverageCrossStrategy


def build_df(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    data = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )
    return data


def test_ma_cross_signal_shape():
    df = build_df()
    strategy = MovingAverageCrossStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_donchian_signal_shape():
    df = build_df()
    strategy = DonchianBreakoutStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_momentum_signal_shape():
    df = build_df()
    strategy = MomentumVolatilityStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_momentum_accepts_legacy_alias_params():
    df = build_df()
    strategy = MomentumVolatilityStrategy(lookback=63, vol_window=20, volatility_limit=0.8)
    sig = strategy.generate_signals(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})


def test_regime_momentum_signal_shape():
    df = build_df()
    strategy = RegimeMomentumStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_macd_regime_signal_shape():
    df = build_df()
    strategy = MacdRegimeStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_score_regime_signal_shape():
    df = build_df()
    strategy = ScoreRegimeStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_score_regime_accepts_legacy_weights_param():
    df = build_df()
    strategy = ScoreRegimeStrategy(weights=[0.5, 0.3, 0.2])
    sig = strategy.generate_signals(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})


def test_atr_regime_signal_shape():
    df = build_df()
    strategy = AtrRegimeStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns


def test_dual_momentum_signal_shape():
    df = build_df()
    strategy = DualMomentumStrategy()
    sig = strategy.generate_signals(df)
    explain = strategy.explain(df)
    assert len(sig) == len(df)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert (explain["signal"] == sig).all()
    assert "reason" in explain.columns
