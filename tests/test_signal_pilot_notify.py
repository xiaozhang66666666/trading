import json
import sqlite3

import pandas as pd
import urllib.error

from market_signal_system.signal_pilot.ledger import create_alert_row, load_alert_ledger, save_alert_ledger
from market_signal_system.signal_pilot.notify import dispatch_alerts


def test_dispatch_alerts_local_sink_updates_ledger_and_writes_sink(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    queue_path = tmp_path / "notifications.jsonl"
    sink_path = tmp_path / "dispatched.jsonl"

    row_a = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="test",
        alert_id="a1",
    )
    row_b = create_alert_row(
        symbol="ETH",
        strategy="score_regime",
        interval="1d",
        side="short",
        alert_price=200.0,
        alert_reason="test",
        alert_id="b1",
    )
    row_b["notification_sent"] = True
    row_b["notification_channel"] = "local_file"
    save_alert_ledger(pd.DataFrame([row_a, row_b]), ledger_path, account_id="acct_notify", db_path=tmp_path / "pilot.db")

    queue_path.write_text(
        "\n".join(
            [
                json.dumps({"alert_id": "a1", "symbol": "QQQ", "strategy": "score_regime"}, ensure_ascii=False),
                json.dumps({"alert_id": "b1", "symbol": "ETH", "strategy": "score_regime"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = dispatch_alerts(
        queue_file=queue_path,
        ledger_path=ledger_path,
        sink_file=sink_path,
        max_events=10,
        dry_run=False,
        account_id="acct_notify",
        db_path=tmp_path / "pilot.db",
    )

    assert summary["processed"] == 2
    assert summary["sent"] == 1
    assert summary["skipped_already_sent"] == 1
    assert summary["failed"] == 0
    assert summary["account_id"] == "acct_notify"
    assert summary["sink_file"] == str(sink_path)
    assert sink_path.exists()

    sent_lines = [json.loads(x) for x in sink_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(sent_lines) == 1
    assert sent_lines[0]["alert_id"] == "a1"

    ledger = load_alert_ledger(ledger_path, account_id="acct_notify", db_path=tmp_path / "pilot.db")
    row_a_new = ledger.loc[ledger["alert_id"] == "a1"].iloc[0]
    assert bool(row_a_new["notification_sent"]) is True
    assert str(row_a_new["notification_channel"]) == "local_file"
    with sqlite3.connect(tmp_path / "pilot.db") as conn:
        dispatch_count = conn.execute(
            "SELECT COUNT(1) FROM notification_dispatch_records WHERE account_id=?",
            ("acct_notify",),
        ).fetchone()[0]
    assert int(dispatch_count) >= 1


def test_dispatch_alerts_dry_run_does_not_write_sink(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    queue_path = tmp_path / "notifications.jsonl"
    sink_path = tmp_path / "dispatched.jsonl"

    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="test",
        alert_id="a1",
    )
    save_alert_ledger(pd.DataFrame([row]), ledger_path)
    queue_path.write_text(json.dumps({"alert_id": "a1"}, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = dispatch_alerts(
        queue_file=queue_path,
        ledger_path=ledger_path,
        sink_file=sink_path,
        max_events=10,
        dry_run=True,
    )

    assert summary["sent"] == 1
    assert summary["channel"] == "dry_run"
    assert summary["sink_file"] is None
    assert not sink_path.exists()


def test_dispatch_alerts_webhook_retry_then_success(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.csv"
    queue_path = tmp_path / "notifications.jsonl"

    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="test",
        alert_id="a1",
    )
    save_alert_ledger(pd.DataFrame([row]), ledger_path)
    queue_path.write_text(json.dumps({"alert_id": "a1"}, ensure_ascii=False) + "\n", encoding="utf-8")

    calls = {"count": 0}

    def _fake_urlopen(req, timeout):  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("timed out")

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):  # noqa: ARG002
                return False

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    summary = dispatch_alerts(
        queue_file=queue_path,
        ledger_path=ledger_path,
        webhook_url="https://example.com/hook",
        max_events=10,
        retry_count=1,
        retry_delay_ms=0,
        dry_run=False,
    )

    assert summary["sent"] == 1
    assert summary["failed"] == 0
    assert summary["retried"] == 1
    assert summary["retry_succeeded"] == 1
    assert calls["count"] == 2

    ledger = load_alert_ledger(ledger_path)
    row_new = ledger.loc[ledger["alert_id"] == "a1"].iloc[0]
    assert bool(row_new["notification_sent"]) is True
    assert str(row_new["notification_channel"]) == "webhook"
    assert str(row_new["notification_last_sent_at"])


def test_dispatch_alerts_idempotency_window_skips_recent_attempt(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    queue_path = tmp_path / "notifications.jsonl"
    sink_path = tmp_path / "dispatched.jsonl"

    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="test",
        alert_id="a1",
    )
    row["notification_last_attempt_at"] = "2026-03-16T00:00:00+00:00"
    save_alert_ledger(pd.DataFrame([row]), ledger_path)
    queue_path.write_text(json.dumps({"alert_id": "a1"}, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = dispatch_alerts(
        queue_file=queue_path,
        ledger_path=ledger_path,
        sink_file=sink_path,
        max_events=10,
        dry_run=False,
        idempotency_window_minutes=24 * 60,
    )

    assert summary["processed"] == 1
    assert summary["sent"] == 0
    assert summary["failed"] == 0
    assert summary["skipped_idempotent"] == 1
    assert not sink_path.exists()


def test_dispatch_alerts_missing_queue_returns_stable_summary_schema(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    save_alert_ledger(pd.DataFrame(), ledger_path)

    summary = dispatch_alerts(
        queue_file=tmp_path / "not_exists.jsonl",
        ledger_path=ledger_path,
        webhook_url="https://example.com/hook",
        retry_count=2,
        dry_run=False,
    )

    assert summary["processed"] == 0
    assert summary["sent"] == 0
    assert summary["failed"] == 0
    assert summary["skipped_already_sent"] == 0
    assert summary["skipped_idempotent"] == 0
    assert summary["retried"] == 0
    assert summary["retry_succeeded"] == 0
    assert summary["retry_count"] == 2
    assert summary["channel"] == "webhook"
    assert summary["sink_file"] is None
    assert summary["error_type_counts"] == {}


def test_dispatch_alerts_collects_error_type_counts(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.csv"
    queue_path = tmp_path / "notifications.jsonl"
    row = create_alert_row(
        symbol="QQQ",
        strategy="score_regime",
        interval="1d",
        side="long",
        alert_price=100.0,
        alert_reason="test",
        alert_id="a1",
    )
    save_alert_ledger(pd.DataFrame([row]), ledger_path)
    queue_path.write_text(json.dumps({"alert_id": "a1"}, ensure_ascii=False) + "\n", encoding="utf-8")

    def _fake_urlopen(req, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(
            url="https://example.com/hook",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    summary = dispatch_alerts(
        queue_file=queue_path,
        ledger_path=ledger_path,
        webhook_url="https://example.com/hook",
        retry_count=0,
        dry_run=False,
    )
    assert summary["failed"] == 1
    assert summary["sent"] == 0
    assert summary["error_type_counts"].get("rate_limit") == 1
