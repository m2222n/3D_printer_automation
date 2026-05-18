#!/usr/bin/env bash
# AICA A100 환경 초기 셋업 + 검증
# ===================================
# 근형님이 컨테이너 재생성 후 처음 실행.
# PyTorch + CUDA 확인 → ultralytics 설치 → dataset 자리 생성
#
# 사용법 (AICA에서):
#   bash aica_setup.sh
#
# 종료 코드:
#   0: 환경 OK, 학습 가능
#   1: 환경 문제 — 메시지 확인

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✅ PASS${NC} — $1"; }
fail() { echo -e "  ${RED}❌ FAIL${NC} — $1"; }
info() { echo -e "  ${YELLOW}ℹ️  INFO${NC} — $1"; }
section() { echo -e "\n${BOLD}━━━ $1 ━━━${NC}"; }

FAIL_COUNT=0

# ============================================================
# 1. GPU 확인
# ============================================================
section "1. GPU 확인"
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    if [[ -n "$GPU_NAME" ]]; then
        pass "GPU: $GPU_NAME ($GPU_MEM)"
    else
        fail "nvidia-smi 있으나 GPU 정보 안 나옴"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
else
    fail "nvidia-smi 미설치 또는 GPU 없음"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# ============================================================
# 2. Python + PyTorch
# ============================================================
section "2. Python + PyTorch + CUDA"
PY_VER=$(python --version 2>&1)
pass "Python: $PY_VER"

if python -c "import torch" 2>/dev/null; then
    TORCH_VER=$(python -c "import torch; print(torch.__version__)" 2>/dev/null)
    CUDA_OK=$(python -c "import torch; print(torch.cuda.is_available())" 2>/dev/null)
    if [[ "$CUDA_OK" == "True" ]]; then
        DEVICE=$(python -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null)
        pass "PyTorch: $TORCH_VER (CUDA: $DEVICE)"
    else
        fail "PyTorch $TORCH_VER 있으나 CUDA 사용 불가"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
else
    fail "PyTorch 미설치"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

# ============================================================
# 3. Ultralytics 설치 (없으면 자동 설치)
# ============================================================
section "3. Ultralytics"
if python -c "import ultralytics" 2>/dev/null; then
    ULT_VER=$(python -c "import ultralytics; print(ultralytics.__version__)" 2>/dev/null)
    pass "ultralytics: $ULT_VER"
else
    info "ultralytics 미설치 — pip install 진행"
    pip install ultralytics 2>&1 | tail -3
    if python -c "import ultralytics" 2>/dev/null; then
        ULT_VER=$(python -c "import ultralytics; print(ultralytics.__version__)" 2>/dev/null)
        pass "ultralytics 설치 완료: $ULT_VER"
    else
        fail "ultralytics 설치 실패"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
fi

# ============================================================
# 4. 작업 디렉토리 준비
# ============================================================
section "4. 작업 디렉토리"
WORK_DIR="${WORK_DIR:-/workspace/binpicking_yolo}"
mkdir -p "$WORK_DIR/dataset" "$WORK_DIR/runs" "$WORK_DIR/scripts"
pass "작업 디렉토리: $WORK_DIR"
ls -la "$WORK_DIR/" | head -10

# ============================================================
# 5. 디스크 여유
# ============================================================
section "5. 디스크 여유"
df -h "$WORK_DIR" | head -2

# ============================================================
# 요약
# ============================================================
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}✅ AICA 환경 OK — 학습 가능${NC}"
    echo ""
    echo "다음 단계 (6000에서 실행):"
    echo "  cd ~/binpicking_dataset"
    echo "  scp -r v1/ <AICA_USER>@<AICA_HOST>:-p <AICA_PORT> $WORK_DIR/dataset/"
    echo "  scp -P <AICA_PORT> /home/jtm/3D_printer_automation/bin_picking/yolo_track/scripts/train_v1.sh <AICA_USER>@<AICA_HOST>:$WORK_DIR/"
    echo ""
    echo "그 후 AICA에서:"
    echo "  cd $WORK_DIR"
    echo "  DATASET_DIR=$WORK_DIR/dataset/v1 bash train_v1.sh"
    exit 0
else
    echo -e "${RED}❌ FAIL $FAIL_COUNT — 환경 문제 해결 후 재시도${NC}"
    exit 1
fi
