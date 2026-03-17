#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "当前主目标: 持续完成 T1（T1-02 → T1-10）"
echo "当前分支: $(git branch --show-current 2>/dev/null || true)"
echo "代码变更:"
git status --short || true
echo "最近提交:"
git log --oneline -n 8 2>/dev/null || true
echo "最近修改文件:"
find "$ROOT" -type f \
  -not -path '*/.git/*' \
  -not -path '*/node_modules/*' \
  -not -path '*/dist/*' \
  -not -name '*.pyc' \
  -not -path '*/__pycache__/*' \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' | sort -r | head -n 20 || true
if [ -f frontend/package.json ]; then
  echo "前端构建检查:"
  (cd frontend && npm run build) || true
fi
if [ -f backend/requirements.txt ]; then
  echo "后端测试检查:"
  (cd backend && PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py') || true
fi
if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ]; then
  echo "Compose 配置检查:"
  docker compose config >/dev/null && echo "docker compose config: OK" || true
fi
