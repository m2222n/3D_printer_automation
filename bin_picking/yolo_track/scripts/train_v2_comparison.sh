#!/usr/bin/env bash
# YOLO 트랙 v2 비교 학습 스크립트 — 5개 모델 (v8n/v8m/v11s/v11m/v11l) 순차 학습
# ================================================================
# 5/20 한솔 권고 ("v8 → v11 + n → m/l") + 사용자 결정 ("전부 다 해보고 가장 좋은 거")
#
# 사용법 (AICA에서):
#   cd /workspace/binpicking_yolo
#   bash scripts/train_v2_comparison.sh
#
# 사전 조건:
# - dataset/v2/ 풀린 상태 (data.yaml + train/ + valid/ + test/)
# - ultralytics 8.4.51+ (5/18 설치 그대로, YOLOv11 지원)
# - CUDA A100 (5/18 부활 컨테이너)
#
# 동작:
# - 5개 모델 순차 학습 (백그라운드 가능)
# - 각 결과는 runs/v2-comparison/v2-{model}/ 에 저장
# - 학습 완료 후 results.csv 종합해서 비교 표 출력

set -euo pipefail

# ============================================================
# 경로 설정
# ============================================================
DATASET_DIR="${DATASET_DIR:-/workspace/binpicking_yolo/dataset/v2}"
RUNS_DIR="${RUNS_DIR:-/workspace/binpicking_yolo/runs}"
PROJECT_NAME="${PROJECT_NAME:-v2-comparison}"

# 학습 하이퍼파라미터 (v1 150 epochs에서 강화)
EPOCHS="${EPOCHS:-200}"
IMGSZ="${IMGSZ:-640}"
BATCH="${BATCH:-16}"           # AICA shm 64MB 제약 (workers=0이라 batch 보수적)
DEVICE="${DEVICE:-0}"
PATIENCE="${PATIENCE:-50}"     # early stopping (overfitting 방지)

# 5/20 v2 비교 대상 5개 모델
MODELS=(
    "yolov8n"   # 3.2M  - v1 baseline (5/18 mAP50 0.988)
    "yolov8m"   # 25.9M - v8 medium 참고
    "yolo11s"   # 9.5M  - v11 small (한솔 권고 기본)
    "yolo11m"   # 20.1M - v11 medium (한솔 권고 권장)
    "yolo11l"   # 25.3M - v11 large (한솔 권고 최대)
)

# ============================================================
# 환경 검증
# ============================================================
echo "================================================================"
echo "  YOLO v2 비교 학습 — 5개 모델 (5/20)"
echo "================================================================"
echo ""

if [[ ! -f "$DATASET_DIR/data.yaml" ]]; then
    echo "❌ data.yaml 없음: $DATASET_DIR/data.yaml"
    echo "   DATASET_DIR 환경변수 확인하거나 v2 zip 풀기"
    exit 1
fi

nvidia-smi --query-gpu=name,memory.free --format=csv,noheader | head -1
/opt/conda/bin/python -c "import torch; print(f'torch {torch.__version__} / CUDA {torch.cuda.is_available()}')"
/opt/conda/bin/python -c "import ultralytics; print(f'ultralytics {ultralytics.__version__}')"

echo ""
echo "=== v2 데이터셋 ==="
cat "$DATASET_DIR/data.yaml"
echo ""

# ============================================================
# 학습 루프 — 5개 모델 순차
# ============================================================
LOG_DIR="$RUNS_DIR/$PROJECT_NAME"
mkdir -p "$LOG_DIR"

TS_START=$(date +%s)
echo "=== 5개 모델 학습 시작: $(date) ==="
echo ""

for MODEL_NAME in "${MODELS[@]}"; do
    RUN_NAME="v2-${MODEL_NAME}"
    LOG_FILE="$LOG_DIR/${RUN_NAME}.log"

    echo "────────────────────────────────────────────────────────────────"
    echo "  학습 [${MODEL_NAME}] 시작: $(date +%H:%M:%S)"
    echo "  로그: $LOG_FILE"
    echo "────────────────────────────────────────────────────────────────"

    TS_MODEL_START=$(date +%s)

    # workers=0 + cache=ram = AICA /dev/shm 64MB 제약 회피 (5/18 학습 시 정립)
    /opt/conda/bin/yolo detect train \
        model="${MODEL_NAME}.pt" \
        data="$DATASET_DIR/data.yaml" \
        epochs="$EPOCHS" \
        imgsz="$IMGSZ" \
        batch="$BATCH" \
        workers=0 \
        cache=ram \
        device="$DEVICE" \
        project="$LOG_DIR" \
        name="$RUN_NAME" \
        exist_ok=True \
        cos_lr=True \
        patience="$PATIENCE" \
        save=True \
        save_period=20 \
        plots=True \
        verbose=False \
        2>&1 | tee "$LOG_FILE" | grep -E "Epoch|mAP|Saving|Validating|complete|best.pt" | tail -30 || true

    TS_MODEL_END=$(date +%s)
    DURATION=$((TS_MODEL_END - TS_MODEL_START))
    echo ""
    echo "  ✅ [${MODEL_NAME}] 완료: ${DURATION}초 ($(date +%H:%M:%S))"
    echo ""
done

TS_END=$(date +%s)
TOTAL=$((TS_END - TS_START))
echo "================================================================"
echo "  전체 학습 완료: ${TOTAL}초 ($(date))"
echo "================================================================"
echo ""

# ============================================================
# 비교 표 자동 생성
# ============================================================
echo "=== 5개 모델 비교 (best.pt 기준) ==="
/opt/conda/bin/python "$(dirname "$0")/compare_v2_results.py" --runs-dir "$LOG_DIR" || \
    echo "⚠️ 비교 스크립트 실행 실패 — 수동으로 results.csv 확인"

echo ""
echo "=== 결과 위치 ==="
for MODEL_NAME in "${MODELS[@]}"; do
    RUN_PATH="$LOG_DIR/v2-${MODEL_NAME}"
    if [[ -d "$RUN_PATH" ]]; then
        echo "  $RUN_PATH/weights/best.pt"
    fi
done

echo ""
echo "=== 6000 회수 명령 (AICA에서 실행) ==="
echo "  scp -P 22 -r $LOG_DIR jtm@<DEV_SERVER_IP>:/home/jtm/3D_printer_automation/bin_picking/yolo_track/runs/"
