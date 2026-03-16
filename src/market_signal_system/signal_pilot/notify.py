"""Notification dispatch helpers for Signal Pilot queue."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from market_signal_system.signal_pilot.ledger import load_alert_ledger, save_alert_ledger
from market_signal_system.storage import SQLiteStore, normalize_account_id
from market_signal_system.utils.paths import OUTPUT_DIR


def _normalize_output_path(path: str | Path | None, default_name: str) -> Path:
    if path is None:
        return OUTPUT_DIR / default_name
    p = Path(path)
    if p.is_absolute():
        return p
    return OUTPUT_DIR / p


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def _is_retryable_webhook_error(error_msg: str | None, http_status: int | None) -> bool:
    if http_status is not None and (http_status >= 500 or http_status in {408, 425, 429}):
        return True
    if not error_msg:
        return False
    text = error_msg.lower()
    retryable_markers = [
        "timed out",
        "timeout",
        "temporarily",
        "temporary",
        "connection reset",
        "connection refused",
        "remote end closed connection",
        "too many requests",
        "rate limit",
        "unavailable",
    ]
    return any(marker in text for marker in retryable_markers)


def _classify_dispatch_error(error_msg: str | None, http_status: int | None) -> str:
    if http_status == 429:
        return "rate_limit"
    if http_status is not None and http_status >= 500:
        return "server_5xx"
    if http_status is not None and http_status >= 400:
        return "http_4xx"
    text = (error_msg or "").lower()
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "connection" in text or "refused" in text or "reset" in text:
        return "connection"
    if "temporary" in text or "unavailable" in text:
        return "temporary"
    return "unknown"


def _post_webhook(
    url: str,
    payload: dict[str, Any],
    timeout_sec: float,
    idempotency_key: str | None,
) -> tuple[bool, str | None, int | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(0.1, float(timeout_sec))) as resp:
            code = int(getattr(resp, "status", 200) or 200)
        return 200 <= code < 300, None, code
    except urllib.error.HTTPError as exc:
        return False, str(exc), int(getattr(exc, "code", 0) or 0)
    except urllib.error.URLError as exc:
        return False, str(exc), None


def dispatch_alerts(
    *,
    queue_file: str | Path | None = None,
    ledger_path: str | Path | None = None,
    webhook_url: str | None = None,
    sink_file: str | Path | None = None,
    max_events: int = 200,
    timeout_sec: float = 10.0,
    retry_count: int = 0,
    retry_delay_ms: int = 500,
    idempotency_window_minutes: float = 0.0,
    dry_run: bool = False,
    account_id: str = "default",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    account = normalize_account_id(account_id)
    store = SQLiteStore(db_path=db_path)
    queue_path = _normalize_output_path(queue_file, "signal_pilot_notifications.jsonl")
    sink_path = _normalize_output_path(sink_file, "signal_pilot_notifications_dispatched.jsonl")
    ledger = load_alert_ledger(ledger_path, account_id=account, db_path=db_path)
    if not ledger.empty and "notification_channel" in ledger.columns:
        ledger["notification_channel"] = ledger["notification_channel"].astype("object")

    if max_events <= 0:
        raise ValueError("max_events 必须 > 0")
    if timeout_sec <= 0:
        raise ValueError("timeout_sec 必须 > 0")
    if retry_count < 0:
        raise ValueError("retry_count 必须 >= 0")
    if retry_delay_ms < 0:
        raise ValueError("retry_delay_ms 必须 >= 0")
    if idempotency_window_minutes < 0:
        raise ValueError("idempotency_window_minutes 必须 >= 0")

    if not queue_path.exists():
        out_path = save_alert_ledger(ledger, ledger_path, account_id=account, db_path=db_path)
        return {
            "queue_file": str(queue_path),
            "sink_file": None if dry_run or webhook_url else str(sink_path),
            "ledger_path": str(out_path),
            "account_id": account,
            "db_file": str(store.db_path),
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped_already_sent": 0,
            "skipped_idempotent": 0,
            "errors": [],
            "channel": "dry_run" if dry_run else ("webhook" if webhook_url else "local_file"),
            "retry_count": int(retry_count),
            "retried": 0,
            "retry_succeeded": 0,
            "error_type_counts": {},
        }

    raw_events: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            raw_events.append(payload)

    sent_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    processed = 0
    sent = 0
    failed = 0
    skipped_already_sent = 0
    skipped_idempotent = 0
    retried = 0
    retry_succeeded = 0
    error_type_counts: dict[str, int] = {}
    now_ts = pd.Timestamp(datetime.now(timezone.utc))
    dispatch_records: list[dict[str, Any]] = []

    ledger_idx = {}
    if not ledger.empty and "alert_id" in ledger.columns:
        for idx, value in ledger["alert_id"].astype(str).items():
            ledger_idx[value] = idx

    for event in raw_events[: max(1, int(max_events))]:
        processed += 1
        alert_id = str(event.get("alert_id", "")).strip()
        ledger_row_idx = ledger_idx.get(alert_id)
        already_sent = False
        if ledger_row_idx is not None and not ledger.empty:
            already_sent = bool(ledger.at[ledger_row_idx, "notification_sent"])
        if already_sent:
            skipped_already_sent += 1
            dispatch_records.append(
                {
                    "alert_id": alert_id or None,
                    "event_time": now_ts.isoformat(),
                    "channel": "skip",
                    "status": "skipped_already_sent",
                    "payload": event,
                    "retry_count": int(retry_count),
                }
            )
            continue
        if ledger_row_idx is not None and not ledger.empty:
            last_attempt_raw = ledger.at[ledger_row_idx, "notification_last_attempt_at"]
            if pd.notna(last_attempt_raw) and str(last_attempt_raw).strip():
                last_attempt_ts = pd.Timestamp(str(last_attempt_raw))
                if last_attempt_ts.tzinfo is None:
                    last_attempt_ts = last_attempt_ts.tz_localize("UTC")
                else:
                    last_attempt_ts = last_attempt_ts.tz_convert("UTC")
                if idempotency_window_minutes > 0:
                    elapsed_minutes = (now_ts - last_attempt_ts).total_seconds() / 60.0
                    if elapsed_minutes < float(idempotency_window_minutes):
                        skipped_idempotent += 1
                        dispatch_records.append(
                            {
                                "alert_id": alert_id or None,
                                "event_time": now_ts.isoformat(),
                                "channel": "skip",
                                "status": "skipped_idempotent",
                                "payload": event,
                                "retry_count": int(retry_count),
                            }
                        )
                        continue

        channel = "dry_run" if dry_run else ("webhook" if webhook_url else "local_file")
        ok = True
        error_msg = None
        used_retry = False
        if not dry_run:
            if webhook_url:
                max_attempts = max(1, int(retry_count) + 1)
                http_status: int | None = None
                for attempt in range(1, max_attempts + 1):
                    ok, error_msg, http_status = _post_webhook(
                        str(webhook_url),
                        event,
                        timeout_sec,
                        alert_id or None,
                    )
                    if ok:
                        if attempt > 1:
                            retry_succeeded += 1
                        break
                    retryable = _is_retryable_webhook_error(error_msg, http_status)
                    if attempt >= max_attempts or not retryable:
                        break
                    retried += 1
                    used_retry = True
                    if retry_delay_ms > 0:
                        time.sleep(float(retry_delay_ms) / 1000.0)
            else:
                sent_rows.append(event)

        if ledger_row_idx is not None and not ledger.empty:
            ledger.at[ledger_row_idx, "notification_last_attempt_at"] = now_ts.isoformat()

        if ok:
            sent += 1
            dispatch_records.append(
                {
                    "alert_id": alert_id or None,
                    "event_time": now_ts.isoformat(),
                    "channel": channel,
                    "status": "sent",
                    "payload": event,
                    "used_retry": used_retry,
                    "retry_count": int(retry_count),
                }
            )
            if ledger_row_idx is not None and not ledger.empty:
                ledger.at[ledger_row_idx, "notification_sent"] = True
                ledger.at[ledger_row_idx, "notification_channel"] = channel
                ledger.at[ledger_row_idx, "notification_last_sent_at"] = now_ts.isoformat()
                ledger.at[ledger_row_idx, "notification_fail_count"] = 0
        else:
            failed += 1
            error_type = _classify_dispatch_error(error_msg, http_status if webhook_url else None)
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
            dispatch_records.append(
                {
                    "alert_id": alert_id or None,
                    "event_time": now_ts.isoformat(),
                    "channel": channel,
                    "status": "failed",
                    "error_type": error_type,
                    "error_message": error_msg or "unknown_error",
                    "payload": event,
                    "used_retry": used_retry,
                    "retry_count": int(retry_count),
                }
            )
            errors.append(
                {
                    "alert_id": alert_id,
                    "error": error_msg or "unknown_error",
                    "used_retry": used_retry,
                    "error_type": error_type,
                }
            )
            if ledger_row_idx is not None and not ledger.empty:
                previous = pd.to_numeric(pd.Series([ledger.at[ledger_row_idx, "notification_fail_count"]]), errors="coerce").iloc[0]
                previous_val = int(previous) if pd.notna(previous) else 0
                ledger.at[ledger_row_idx, "notification_fail_count"] = max(0, previous_val) + 1

    if sent_rows and not dry_run:
        _append_jsonl(sink_path, sent_rows)

    store.append_dispatch_records(account, dispatch_records)
    out_path = save_alert_ledger(ledger, ledger_path, account_id=account, db_path=db_path)
    return {
        "queue_file": str(queue_path),
        "sink_file": None if dry_run or webhook_url else str(sink_path),
        "ledger_path": str(out_path),
        "account_id": account,
        "db_file": str(store.db_path),
        "processed": processed,
        "sent": sent,
        "failed": failed,
        "skipped_already_sent": skipped_already_sent,
        "skipped_idempotent": skipped_idempotent,
        "errors": errors,
        "channel": "dry_run" if dry_run else ("webhook" if webhook_url else "local_file"),
        "retry_count": int(retry_count),
        "retried": retried,
        "retry_succeeded": retry_succeeded,
        "error_type_counts": error_type_counts,
    }


__all__ = ["dispatch_alerts"]
