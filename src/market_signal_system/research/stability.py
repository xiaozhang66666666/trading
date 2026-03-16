"""Walk-forward parameter stability analysis."""

from __future__ import annotations

import ast
import json

import pandas as pd


def analyze_walk_forward_stability(detail: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    if detail.empty:
        raise ValueError("walk-forward detail is empty")
    if "selected_params" not in detail.columns:
        raise ValueError("walk-forward detail missing selected_params column")
    if "test_sharpe" not in detail.columns:
        raise ValueError("walk-forward detail missing test_sharpe column")

    parsed = detail["selected_params"].map(_parse_params)
    params_df = pd.DataFrame(parsed.tolist())
    if params_df.empty:
        raise ValueError("selected_params cannot be parsed")

    rows: list[dict[str, object]] = []
    for col in params_df.columns:
        freq = params_df[col].value_counts(dropna=False)
        total = int(freq.sum())
        for value, count in freq.items():
            rows.append(
                {
                    "param": col,
                    "value": value,
                    "count": int(count),
                    "share": float(count / total) if total > 0 else 0.0,
                }
            )
    freq_df = pd.DataFrame(rows).sort_values(["param", "count"], ascending=[True, False]).reset_index(drop=True)

    set_counts = parsed.map(lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False)).value_counts()
    sharpe = detail["test_sharpe"].astype(float)
    summary = {
        "window_count": float(len(detail)),
        "unique_param_sets": float(set_counts.shape[0]),
        "top_param_set_share": float(set_counts.iloc[0] / len(detail)),
        "avg_test_sharpe": float(sharpe.mean()),
        "std_test_sharpe": float(sharpe.std(ddof=0)),
        "positive_sharpe_ratio": float((sharpe > 0).mean()),
    }
    return summary, freq_df


def _parse_params(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = ast.literal_eval(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"cannot parse selected_params: {value!r}")
