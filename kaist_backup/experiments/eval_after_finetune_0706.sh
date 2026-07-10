#!/usr/bin/env bash
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd /workspace/cadence
FT=runs/C_real_finetune_ourcode_0706
LOG=runs/C_real_finetune_ourcode_0706.log
MN=/workspace/cadence/mentoring_new
C=$MN/data/real_labelme_dataset_C_fgclean_30_20_50
EVLOG=runs/eval_C_ourcode_0706.log
echo "===== fine-tune 완주 대기 $(date) =====" > $EVLOG
# Training done 또는 프로세스 종료까지 대기 (최대 90분)
for i in $(seq 1 180); do
  if grep -qa "Training done" $LOG 2>/dev/null; then echo "완주 감지" >> $EVLOG; break; fi
  if ! pgrep -f C_real_finetune_ourcode_0706 >/dev/null 2>&1; then echo "프로세스 종료 감지" >> $EVLOG; break; fi
  sleep 30
done
echo "===== test 50장 평가 시작 $(date) =====" >> $EVLOG
# 조교 eval 스크립트 (우리 best.pt로 test split 평가, F1)
cd $MN
REAL_ROOT=$C LABEL_DIR=./data/real_labels \
CKPT=/workspace/cadence/$FT/best.pt \
OUT_DIR=/workspace/cadence/eval_C_ourcode_test_s050_nms030_iou025 \
SCORE_THRESH=0.50 NMS_THRESH=0.30 IOU_THRESH=0.25 \
  bash ./scripts/eval_C_real_test.sh >> /workspace/cadence/$EVLOG 2>&1
echo "===== 평가 종료 $(date) =====" >> /workspace/cadence/$EVLOG
echo ">>> 결과:" >> /workspace/cadence/$EVLOG
cat /workspace/cadence/eval_C_ourcode_test_s050_nms030_iou025/eval_real_metrics.json >> /workspace/cadence/$EVLOG 2>&1
