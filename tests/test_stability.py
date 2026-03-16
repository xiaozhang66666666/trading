import pandas as pd

from market_signal_system.research.stability import analyze_walk_forward_stability


def test_analyze_walk_forward_stability_outputs_summary_and_freq():
    detail = pd.DataFrame(
        [
            {"window": 1, "selected_params": {"fast_window": 30, "slow_window": 120}, "test_sharpe": 0.8},
            {"window": 2, "selected_params": {"fast_window": 30, "slow_window": 180}, "test_sharpe": 0.5},
            {"window": 3, "selected_params": {"fast_window": 30, "slow_window": 120}, "test_sharpe": -0.2},
        ]
    )
    summary, freq = analyze_walk_forward_stability(detail)
    assert summary["window_count"] == 3.0
    assert summary["unique_param_sets"] == 2.0
    assert "positive_sharpe_ratio" in summary
    fast_30 = freq[(freq["param"] == "fast_window") & (freq["value"] == 30)]
    assert not fast_30.empty
    assert float(fast_30.iloc[0]["share"]) == 1.0
