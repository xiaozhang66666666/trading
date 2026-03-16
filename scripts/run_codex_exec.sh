#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/market-signal-system"
RUN_DIR="$ROOT/.codex/runs"
PROMPT_FILE="$ROOT/CODEX_PROMPT.md"
mkdir -p "$RUN_DIR"

TS="$(date -u '+%Y%m%dT%H%M%SZ')"
LOG="$RUN_DIR/exec-$TS.log"
LAST="$RUN_DIR/latest.log"
MSG_OUT="$RUN_DIR/last-message.txt"
SESSION_FILE="$RUN_DIR/session-id.txt"

cd "$ROOT"

codex exec \
  --dangerously-bypass-approvals-and-sandbox \
  --model gpt-5.3-codex \
  --output-last-message "$MSG_OUT" \
  "$(cat "$PROMPT_FILE")" \
  > "$LOG" 2>&1 || true

cp -f "$LOG" "$LAST" 2>/dev/null || true
awk '/session id:/{print $3}' "$LOG" | tail -n 1 > "$SESSION_FILE" 2>/dev/null || true
