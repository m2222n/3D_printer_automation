#!/usr/bin/env bash
# D435 브래킷 재촬영 + full pipeline 실행
#
# 세팅 체크 (실행 전):
#   [ ] D435 완전 고정 (흔들림 X)
#   [ ] bracket 부품 1개만, 앞면이 카메라 정면
#   [ ] 검은 배경 (천/옷)
#   [ ] 거리 30~40cm
#   [ ] 다른 물체 (손/노트북 가장자리) 프레임 밖
#
# 사용법:
#   ./bin_picking/tests/run_bracket_retry.sh            # 기본 (retry1)
#   ./bin_picking/tests/run_bracket_retry.sh retry2     # 다른 이름으로 저장
#
# 결과 프레임: ~/Desktop/d435_bracket_<tag>/

set -euo pipefail

TAG="${1:-retry1}"
FRAME_DIR="${HOME}/Desktop/d435_bracket_${TAG}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

PY="${PROJECT_ROOT}/.venv/binpick/bin/python"
if [[ ! -x "${PY}" ]]; then
  echo "[ERROR] venv python not found: ${PY}" >&2
  exit 1
fi

echo "=================================================="
echo "  D435 Bracket Retry — tag=${TAG}"
echo "  frame-dir: ${FRAME_DIR}"
echo "  depth: 0.20 ~ 0.60 m,  top-k: 5"
echo "=================================================="
echo ""

# sudo: Mac에서 D435 USB 접근에 필요
sudo "${PY}" bin_picking/tests/test_d435_full_pipeline.py \
    --live --save \
    --frame-dir "${FRAME_DIR}" \
    --top-k 5 \
    --depth-min 0.20 --depth-max 0.60 \
    --no-vis
