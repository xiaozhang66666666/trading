#!/usr/bin/env bash
set -euo pipefail
ROOT="/root/.openclaw/workspace/multi-asset-sim-platform"
cd "$ROOT"
echo "时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "当前任务: T1-01 标的管理与数据源接入"
echo "代码变更:"
git status --short || true
echo "最近提交:"
git log --oneline -n 5 2>/dev/null || true
echo "最近修改文件:"
find "$ROOT" -type f -not -path '*/.git/*' -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' | sort -r | head -n 12 || true
if [ -f package.json ]; then
  echo "检测到 package.json，尝试构建/检查"
  npm run build 2>&1 || true
fi
