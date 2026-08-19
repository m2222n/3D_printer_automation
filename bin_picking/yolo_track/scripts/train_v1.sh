#!/usr/bin/env bash
# YOLO 트랙 v1 학습 스크립트 — AICA A100 또는 호환 GPU 환경에서 실행
# ================================================================
# 사용법 (AICA에서):
#   cd /workspace/binpicking_yolo
#   bash scripts/train_v1.sh
#
# 사전 조건:
# - dataset zip 풀린 상태 (data.yaml + train/ + valid/ + test/)
# - ultralytics 설치 (pip install ultralytics)
# - CUDA 사용 가능 (nvidia-smi 확인)

set -euo pipefail

# ============================================================
# 경로 설정 (AICA 기본 가정, 환경 변수로 오버라이드 가능)
# ============================================================
DATASET_DIR="${DATASET_DIR:-/workspace/binpicking_yolo/dataset/v1}"
RUNS_DIR="${RUNS_DIR:-/workspace/binpicking_yolo/runs}"
MODEL="${MODEL:-yolov8n.pt}"  # nano = 가장 작음 / s/m/l/x 로 확장
EPOCHS="${EPOCHS:-100}"
IMGSZ="${IMGSZ:-640}"
BATCH="${BATCH:-32}"          # A100 80GB면 64~128도 가능, 안전 32
DEVICE="${DEVICE:-0}"         # GPU 0번. CPU는 cpu, Mac은 mps
PROJECT_NAME="${PROJECT_NAME:-parts-5class-v1}"
RUN_NAME="${RUN_NAME:-v1-yolov8n-$(date +%Y%m%d-%H%M)}"

# ============================================================
# 환경 검증
# ============================================================
echo "=== 환경 검증 ==="
nvidia-smi | head -5 || echo "⚠️ nvidia-smi 없음 — GPU 학습 불가"
python -c "import ultralytics; print(f'ultralytics: {ultralytics.__version__}')" || {
    echo "❌ ultralytics 미설치. pip install ultralytics 실행"
    exit 1
}
python -c "import torch; print(f'torch: {torch.__version__}, cuda: {torch.cuda.is_available()}, device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}')"

# data.yaml 존재 확인
if [[ ! -f "$DATASET_DIR/data.yaml" ]]; then
    echo "❌ data.yaml 없음: $DATASET_DIR/data.yaml"
    echo "   DATASET_DIR 환경변수 확인하거나 zip 풀기"
    exit 1
fi

echo ""
echo "=== 학습 설정 ==="
echo "Dataset:  $DATASET_DIR/data.yaml"
echo "Model:    $MODEL"
echo "Epochs:   $EPOCHS"
echo "Image:    ${IMGSZ}x${IMGSZ}"
echo "Batch:    $BATCH"
echo "Device:   $DEVICE"
echo "Output:   $RUNS_DIR/$PROJECT_NAME/$RUN_NAME"
echo ""

# data.yaml 미리보기
echo "=== data.yaml ==="
cat "$DATASET_DIR/data.yaml"
echo ""

# ============================================================
# 학습 시작
# ============================================================
echo "=== 학습 시작 ==="
yolo detect train \
    data="$DATASET_DIR/data.yaml" \
    model="$MODEL" \
    epochs="$EPOCHS" \
    imgsz="$IMGSZ" \
    batch="$BATCH" \
    device="$DEVICE" \
    project="$RUNS_DIR/$PROJECT_NAME" \
    name="$RUN_NAME" \
    save=True \
    save_period=10 \
    plots=True \
    verbose=True

# ============================================================
# 결과 안내
# ============================================================
echo ""
echo "=== 학습 완료 ==="
RUN_PATH="$RUNS_DIR/$PROJECT_NAME/$RUN_NAME"
echo "결과 디렉토리: $RUN_PATH"
echo ""
echo "주요 결과 파일:"
echo "  - weights/best.pt    : 최고 성능 모델"
echo "  - weights/last.pt    : 마지막 epoch 모델"
echo "  - results.png        : 학습 곡선 (loss, mAP)"
echo "  - confusion_matrix.png : 혼동 행렬"
echo "  - val_batch*_pred.jpg : 검증 예측 시각화"
echo ""
echo "메트릭 확인:"
echo "  cat $RUN_PATH/results.csv | tail -5"
echo ""
echo "6000 회수 (AICA에서 실행):"
echo "  scp -P 22 -r $RUN_PATH jtm@<DEV_SERVER_IP>:/home/jtm/3D_printer_automation/bin_picking/yolo_track/runs/"
