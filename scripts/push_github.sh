#!/usr/bin/env bash
set -euo pipefail

# 中文约束：推送前必须是干净工作树。
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[错误] 当前仓库不是 clean 状态，请先提交或清理后再推送。" >&2
  exit 1
fi

REMOTE_URL="https://github.com/xiaozhang66666666/trading.git"
BRANCH="master"

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# 优先使用环境变量令牌；未提供时回退普通 HTTPS（会要求交互凭据）。
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  AUTH_URL="https://x-access-token:${GITHUB_TOKEN}@github.com/xiaozhang66666666/trading.git"
  git push -u "$AUTH_URL" "$BRANCH"
else
  git push -u origin "$BRANCH"
fi
