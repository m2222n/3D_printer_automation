#!/usr/bin/env bash
# 라인 MES 화면 자체검사 — 타입 + 투영 + 렌더/조작(jsdom).
#   cd frontend && ./scripts/check.sh
# jsdom 은 저장소에 없다. 와이어프레임 검사(check_merged.js)와 같은 규약으로 NODE_PATH 로 준다.
set -euo pipefail
cd "$(dirname "$0")/.."
export NODE_PATH="${NODE_PATH:-/tmp/node_modules}"
node -e "require('jsdom')" 2>/dev/null || { echo "✗ jsdom 이 필요합니다 (NODE_PATH 확인)"; exit 1; }

npx tsc -b && echo "✓ 타입"

run() {  # run <이름> <진입 파일>
  npx esbuild "$2" --bundle --platform=node --format=esm --jsx=automatic \
    --external:jsdom --outfile="/tmp/$1.mjs" --log-level=warning
  echo "── $1"
  node "/tmp/$1.mjs"
}
run checkLineApi        scripts/checkLineApi.ts
run checkLineMonitor    scripts/checkLineMonitor.tsx
run checkProcessControl scripts/checkProcessControl.tsx
