#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/market-signal-system"
RUN_DIR="$ROOT/.codex/runs"
LOG="$ROOT/MONITOR_LOG.md"
TS="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
SESSION_FILE="$RUN_DIR/session-id.txt"
LATEST_LOG="$RUN_DIR/latest.log"
MSG_OUT="$RUN_DIR/last-message.txt"
PID_FILE="$RUN_DIR/runner.pid"

mkdir -p "$RUN_DIR"

append_log() {
  local msg="$1"
  printf -- "\n## [%s]\n%s\n" "$TS" "$msg" >> "$LOG"
}

start_new() {
  nohup "$ROOT/scripts/run_codex_exec.sh" >/dev/null 2>&1 &
  echo $! > "$PID_FILE"
  append_log "- 未发现运行中的 Codex exec，已启动新一轮执行。"
}

resume_with_prompt() {
  local prompt="$1"
  local sid=""
  [[ -f "$SESSION_FILE" ]] && sid="$(cat "$SESSION_FILE" 2>/dev/null || true)"
  if [[ -n "$sid" ]]; then
    local out="$RUN_DIR/resume-$(date -u '+%Y%m%dT%H%M%SZ').log"
    nohup bash -lc "cd '$ROOT' && codex exec resume '$sid' --dangerously-bypass-approvals-and-sandbox --model gpt-5.3-codex '$prompt' > '$out' 2>&1" >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    append_log "- 已基于 session $sid 继续一轮 Codex：$prompt"
  else
    start_new
  fi
}

running=0
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    running=1
  fi
fi

if [[ "$running" -eq 0 ]]; then
  start_new
fi

status="<no latest log>"
[[ -f "$LATEST_LOG" ]] && status="$(tail -n 80 "$LATEST_LOG")"
last_msg="<no last message>"
[[ -f "$MSG_OUT" ]] && last_msg="$(tail -n 40 "$MSG_OUT")"

missing=""
for f in README.md STATUS.md DECISIONS.md; do
  [[ -f "$ROOT/$f" ]] || missing+="$f "
done
if [[ -n "$missing" ]]; then
  resume_with_prompt "请立即补齐缺失文件：$missing。然后继续主线开发：先数据层，再回测引擎，再策略，再模拟交易，并更新 STATUS.md 与 DECISIONS.md。"
fi

if printf '%s' "$status\n$last_msg" | grep -Eqi '(error|traceback|failed|exception)'; then
  resume_with_prompt "检测到错误。请先做最小修复以恢复主链路，然后继续任务；修复后更新 STATUS.md 并 git commit。"
fi

append_log "- 运行中: $running\n\n- 最新输出摘要:\n\n\`\`\`\n$(printf '%s' "$status" | tail -n 40)\n\`\`\`\n\n- 最后消息:\n\n\`\`\`\n$(printf '%s' "$last_msg" | tail -n 20)\n\`\`\`"
