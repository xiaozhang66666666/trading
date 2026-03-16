#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/market-signal-system"
SESSION="codex-market"
LOG="$ROOT/MONITOR_LOG.md"
TS="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"

append_log() {
  local msg="$1"
  printf -- "\n## [%s]\n%s\n" "$TS" "$msg" >> "$LOG"
}

start_codex() {
  tmux new-session -d -s "$SESSION" -c "$ROOT" "bash -lc 'codex --dangerously-bypass-approvals-and-sandbox --model gpt-5.3-codex --no-alt-screen'"
  sleep 3
  tmux load-buffer "$ROOT/CODEX_PROMPT.md"
  tmux paste-buffer -t "$SESSION"
  tmux send-keys -t "$SESSION" Enter
  sleep 1
}

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  start_codex
  append_log "- 会话不存在，已新建并启动 Codex。"
fi

OUT="$(tmux capture-pane -t "$SESSION" -p -S -240 || true)"
LOW="$(printf '%s' "$OUT" | tr 'A-Z' 'a-z')"
ACTION=""

if printf '%s' "$LOW" | grep -Eq "(choose how you'd like codex to proceed|try new model|use existing model|press enter to confirm)"; then
  tmux send-keys -t "$SESSION" "2" Enter
  ACTION+="- 检测到模型升级选择提示，已自动选择继续使用现有模型（2）。\n"
fi

if printf '%s' "$LOW" | grep -Eq "\b(proceed|continue|approve|yes/no|y/n|press y|confirm)\b"; then
  tmux send-keys -t "$SESSION" "y" Enter
  ACTION+="- 检测到确认提示，已自动发送 y。\n"
fi

if printf '%s' "$LOW" | grep -Eq "(what should i|which option|need your decision|请选择|你希望)"; then
  tmux send-keys -t "$SESSION" "按稳妥方案推进：优先可运行MVP，先补主链路，再增强；不要等待用户确认。" Enter
  ACTION+="- 检测到决策请求，已下发默认技术决策。\n"
fi

if printf '%s' "$LOW" | grep -Eq "(error|traceback|failed|exception)"; then
  tmux send-keys -t "$SESSION" "先做最小修复以恢复主链路，然后继续任务；修复后更新STATUS并提交。" Enter
  ACTION+="- 检测到错误信号，已指令最小修复并继续。\n"
fi

if [[ -z "$ACTION" ]]; then
  ACTION+="- 未发现阻塞提示，会话继续运行。\n"
fi

cd "$ROOT"
GIT_STATUS="$(git status --short 2>/dev/null || true)"
MISSING=""
for f in README.md STATUS.md DECISIONS.md; do
  [[ -f "$ROOT/$f" ]] || MISSING+="$f "
done

if [[ -n "$MISSING" ]]; then
  tmux send-keys -t "$SESSION" "请立即补齐缺失文件：$MISSING，并继续主线开发。" Enter
  ACTION+="- 检测到缺失文件，已要求补齐：$MISSING\n"
fi

append_log "- git status:\n\n\`\`\`\n${GIT_STATUS:-<clean-or-unavailable>}\n\`\`\`\n\n- 动作:\n${ACTION}"

exit 0
