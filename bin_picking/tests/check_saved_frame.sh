#!/usr/bin/env bash
# 저장된 D435 프레임 로드 → Full Pipeline (카메라/sudo 불필요)
#
# 사용법:
#   ./bin_picking/tests/check_saved_frame.sh                       # retry1, 기본 범위
#   ./bin_picking/tests/check_saved_frame.sh retry2                # 다른 태그
#   ./bin_picking/tests/check_saved_frame.sh retry1 0.15 1.0       # depth 범위 지정

set -euo pipefail

TAG="${1:-retry1}"
DEPTH_MIN="${2:-0.15}"
DEPTH_MAX="${3:-0.60}"
ONLY="${4:-}"
FRAME_DIR="${HOME}/Desktop/d435_bracket_${TAG}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

PY="${PROJECT_ROOT}/.venv/binpick/bin/python"

echo "=================================================="
echo "  Load saved frame — tag=${TAG}"
echo "  frame-dir: ${FRAME_DIR}"
echo "  depth: ${DEPTH_MIN} ~ ${DEPTH_MAX} m,  top-k: 5"
echo "=================================================="

if [[ ! -d "${FRAME_DIR}" ]]; then
  echo "[ERROR] frame-dir not found: ${FRAME_DIR}" >&2
  exit 1
fi

EXTRA=()
if [[ -n "${ONLY}" ]]; then
  EXTRA+=(--only "${ONLY}")
fi

"${PY}" bin_picking/tests/test_d435_full_pipeline.py \
    --load \
    --frame-dir "${FRAME_DIR}" \
    --top-k 7 \
    --depth-min "${DEPTH_MIN}" --depth-max "${DEPTH_MAX}" \
    --no-vis \
    "${EXTRA[@]}"
