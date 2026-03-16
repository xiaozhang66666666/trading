import json

import pandas as pd

from market_signal_system.signal_pilot.ledger import create_alert_row, save_alert_ledger
from market_signal_system.signal_pilot.pilot import report_alerts


def test_report_alerts_outputs_7_30_60_window_files(tmp_path):
    rows = [
        create_alert_row(
            symbol="QQQ",
            strategy="score_regime",
            interval="1d",
            side="long",
            alert_price=100.0,
            alert_reason="a",
            created_at="2026-03-10T00:00:00+00:00",
            alert_id="a1",
        ),
        create_alert_row(
            symbol="QQQ",
            strategy="score_regime",
            interval="1d",
            side="long",
            alert_price=100.0,
            alert_reason="b",
            created_at="2026-02-20T00:00:00+00:00",
            alert_id="a2",
        ),
        create_alert_row(
            symbol="ETH",
            strategy="macd_regime",
            interval="1d",
            side="short",
            alert_price=200.0,
            alert_reason="c",
            created_at="2026-01-20T00:00:00+00:00",
            alert_id="a3",
        ),
    ]
    df = pd.DataFrame(rows)
    df.loc[df["alert_id"] == "a1", "realized_pnl_pct"] = 0.05
    df.loc[df["alert_id"] == "a1", "holding_days"] = 3
    df.loc[df["alert_id"] == "a1", "max_favorable_excursion"] = 0.08
    df.loc[df["alert_id"] == "a1", "max_adverse_excursion"] = -0.01
    df.loc[df["alert_id"] == "a2", "current_pnl_pct"] = -0.02
    df.loc[df["alert_id"] == "a2", "holding_days"] = 20
    df.loc[df["alert_id"] == "a2", "max_favorable_excursion"] = 0.03
    df.loc[df["alert_id"] == "a2", "max_adverse_excursion"] = -0.06
    df.loc[df["alert_id"] == "a3", "realized_pnl_pct"] = 0.1
    df.loc[df["alert_id"] == "a3", "holding_days"] = 40
    df.loc[df["alert_id"] == "a3", "max_favorable_excursion"] = 0.2
    df.loc[df["alert_id"] == "a3", "max_adverse_excursion"] = -0.03

    ledger_path = tmp_path / "alerts.csv"
    save_alert_ledger(df, ledger_path)

    summary = report_alerts(
        ledger_path=ledger_path,
        as_of="2026-03-16T00:00:00+00:00",
        windows=[7, 30, 60],
        output_prefix="pilot_report",
        output_dir=tmp_path,
    )
    assert summary["row_count"] >= 3
    csv_path = tmp_path / "pilot_report_20260316T000000Z.csv"
    json_path = tmp_path / "pilot_report_20260316T000000Z.json"
    md_path = tmp_path / "pilot_report_20260316T000000Z.md"
    assert csv_path.exists()
    assert json_path.exists()
    assert md_path.exists()

    out = pd.read_csv(csv_path)
    assert set(out["window_days"]) == {7, 30, 60}
    row_7 = out[(out["window_days"] == 7) & (out["symbol"] == "QQQ") & (out["strategy"] == "score_regime")].iloc[0]
    assert int(row_7["signal_count"]) == 1
    assert float(row_7["avg_return_pct"]) == 0.05
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["as_of"] == "2026-03-16T00:00:00+00:00"
    assert payload["windows"] == [7, 30, 60]
    assert "| 窗口(天) | 标的 | 策略 |" in md_path.read_text(encoding="utf-8")

