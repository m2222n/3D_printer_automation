#!/usr/bin/env bash
# develop 포트로 현재 체크아웃(juhee 등 미확정 API·FE)을 띄운다 — main(8085 / 5180)은 건드리지 않는다.
#   web-api 8086 (LINE_DSN 은 환경변수로만 넘긴다 → web-api/.env 는 그대로라 8085 를 재시작해도 v2 가 켜지지 않는다)
#   vite    5181 → 8086
# 사용: PGPASSWORD=… scripts/dev_develop.sh      (Ctrl-C 로 둘 다 종료)
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PGPASSWORD:?PGPASSWORD 를 설정하세요 (라인 MES 개발 DB 비번 · DSN 에 넣지 않는다)}"
export LINE_DSN="${LINE_DSN:-postgresql://mes@127.0.0.1/factory}"
export LINE_ID="${LINE_ID:-RESIN-1-ASIS}"
API_PORT="${DEV_API_PORT:-8086}"
FE_PORT="${DEV_FE_PORT:-5181}"

(cd web-api && exec ./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --reload --log-level warning) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null' EXIT
cd frontend && VITE_PORT="$FE_PORT" VITE_API_TARGET="http://127.0.0.1:$API_PORT" exec npx vite
