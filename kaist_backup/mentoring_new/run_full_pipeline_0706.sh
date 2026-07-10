#!/usr/bin/env bash
# 조교 mentoring_new 전체 파이프라인 무인 체인 (7/6, A100)
# 앞단(CAD encoder/memory bank/split)은 이미 완료 → warmup부터.
# 목표: C real fine-tune 후 held-out test 50장 F1 0.7.
set -eu
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd /workspace/cadence/mentoring_new
LOG=./run_full_pipeline_0706.log
echo "========== 파이프라인 시작 $(date) ==========" | tee -a $LOG

step () { echo "" | tee -a $LOG; echo ">>>>> [$1] $(date)" | tee -a $LOG; }

# ── 0. B-fast용 render request json 생성 (real_depth 프로파일 → request) ──
step "0. render request 생성 (prepare_B_renderer_request.sh)"
DEPTH_DIR=./data/real_depth/npy OUT_DIR=./data/domain_profile GLOB="shot_*_g1.npy" \
  bash ./scripts/prepare_B_renderer_request.sh >> $LOG 2>&1
ls -la ./data/domain_profile/pseudo_regen_request.json | tee -a $LOG

# ── 1. warmup detector (30ep) ──
step "1. warmup detector (30ep)"
if [ -f ./runs/depth_detector_warmup_split/best.pt ]; then
  echo "  warmup best.pt 존재 → 스킵" | tee -a $LOG
else
  python train_depth_vq_detector.py \
    --scene_manifest ./data/2d_dataset/splits/train.json \
    --val_scene_manifest ./data/2d_dataset/splits/val.json \
    --out_dir ./runs/depth_detector_warmup_split \
    --num_classes 27 --input_mode zv --stage det \
    --epochs 30 --batch_size 4 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
fi
[ -f ./runs/depth_detector_warmup_split/best.pt ] || { echo "!! warmup 실패"; exit 1; }

# ── 2. B-fast target90 dataset 생성 (1000장) ──
step "2. B-fast target90 생성 (1000장)"
if [ -f ./data/2d_dataset_B_fast_target90/splits/train.json ]; then
  echo "  B-fast target90 존재 → 스킵" | tee -a $LOG
else
  PARTIAL_OBJECT_PROB=1.0 TRUNCATION_OBJECT_PROB=0.50 SOFT_PIXEL_DROPOUT_RATE=0.04 \
  PARTIAL_TARGET_VISIBLE_MIN=0.85 PARTIAL_TARGET_VISIBLE_MAX=0.95 PARTIAL_TARGET_VISIBLE_MEAN=0.90 \
  STL_DIR=./data/stl_dataset REF_DATASET=./data/2d_dataset \
  OUT_ROOT=./data/2d_dataset_B_fast_target90 \
  REQUEST_JSON=./data/domain_profile/pseudo_regen_request.json \
  NUM_SCENES=1000 POINTS_PER_ASSET=15000 SPLAT_RADIUS=1 \
    bash ./scripts/render_B_dataset_fast.sh >> $LOG 2>&1
fi
[ -f ./data/2d_dataset_B_fast_target90/splits/train.json ] || { echo "!! B-fast 생성 실패"; exit 1; }

# ── 3. AB 학습 (target90 + sensorized, 100ep) ──
step "3. AB 학습 (target90 sensorized, 100ep)"
if [ -f ./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt ]; then
  echo "  AB best.pt 존재 → 스킵" | tee -a $LOG
else
  DATA_ROOT=./data/2d_dataset_B_fast_target90 \
  OUT_DIR=./runs/depth_vq_detector_AB_fast_target90_sensorized \
  CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
  INIT_CKPT=./runs/depth_detector_warmup_split/best.pt \
  EPOCHS=100 BATCH_SIZE=4 NUM_WORKERS=0 \
    bash ./scripts/train_AB_blenderproc_sensorized.sh >> $LOG 2>&1
fi
[ -f ./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt ] || { echo "!! AB 학습 실패"; exit 1; }

# ── 4. C real dataset 생성 (train30/val20/test50, foreground cleaning) ──
step "4. C real dataset 생성 (30/20/50)"
if [ -f ./data/real_labelme_dataset_C_fgclean_30_20_50/splits/test.json ]; then
  echo "  C dataset 존재 → 스킵" | tee -a $LOG
else
  DEPTH_DIR=./data/real_depth/npy LABEL_DIR=./data/real_labels \
  OUT_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
  REF_DATASET=./data/2d_dataset GLOB="shot_*.npy" \
  CENTER_CROP="1/6,5/6" DEPTH_KEEP_RANGE="0.40,0.60" REAL_UINT16_MAX_DEPTH_M=10.0 \
  FOREGROUND_DEPTH_MODE=dilated_label FOREGROUND_DILATE_PX=8 \
  TRAIN_COUNT=30 VAL_COUNT=20 SEED=42 \
    bash ./scripts/build_C_real_labelme_dataset.sh >> $LOG 2>&1
fi
[ -f ./data/real_labelme_dataset_C_fgclean_30_20_50/splits/test.json ] || { echo "!! C dataset 실패"; exit 1; }

# ── 5. C real fine-tuning (AB → real 30장, lr 3e-5, 120ep) ──
step "5. C real fine-tune (120ep, lr 3e-5)"
if [ -f ./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt ]; then
  echo "  C finetune best.pt 존재 → 스킵" | tee -a $LOG
else
  REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
  INIT_CKPT=./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt \
  CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
  OUT_DIR=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50 \
  EPOCHS=120 BATCH_SIZE=2 LR=3e-5 IMAGE_SIZE="320,576" \
    bash ./scripts/train_C_real_finetune.sh >> $LOG 2>&1
fi
[ -f ./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt ] || { echo "!! C finetune 실패"; exit 1; }

# ── 6. 평가: held-out test 50장 (목표 F1 0.7) ──
step "6. 평가 test 50장 (s0.5/nms0.3/iou0.25)"
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 LABEL_DIR=./data/real_labels \
CKPT=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt \
OUT_DIR=./eval_real_C_test_s050_nms030_iou025 \
SCORE_THRESH=0.50 NMS_THRESH=0.30 IOU_THRESH=0.25 \
  bash ./scripts/eval_C_real_test.sh >> $LOG 2>&1

echo "" | tee -a $LOG
echo "========== 파이프라인 종료 $(date) ==========" | tee -a $LOG
echo ">>> test 50장 결과:" | tee -a $LOG
cat ./eval_real_C_test_s050_nms030_iou025/eval_real_metrics.json 2>&1 | tee -a $LOG
