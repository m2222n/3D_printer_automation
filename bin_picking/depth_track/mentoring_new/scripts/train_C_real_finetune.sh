#!/usr/bin/env bash
set -euo pipefail

REAL_ROOT=${REAL_ROOT:-./data/real_labelme_dataset_C}
INIT_CKPT=${INIT_CKPT:-./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt}
CAD_MEMORY=${CAD_MEMORY:-./runs/cad_pointnet2/cad_memory_bank.npz}
OUT_DIR=${OUT_DIR:-./runs/depth_vq_detector_C_real_finetuned}
EPOCHS=${EPOCHS:-120}
BATCH_SIZE=${BATCH_SIZE:-2}
LR=${LR:-3e-5}
WEIGHT_DECAY=${WEIGHT_DECAY:-1e-4}
IMAGE_SIZE=${IMAGE_SIZE:-"320,576"}
DEVICE=${DEVICE:-cuda}

python train_depth_vq_detector.py \
  --scene_manifest "$REAL_ROOT/splits/train.json" \
  --val_scene_manifest "$REAL_ROOT/splits/val.json" \
  --cad_memory "$CAD_MEMORY" \
  --init_checkpoint "$INIT_CKPT" \
  --out_dir "$OUT_DIR" \
  --num_classes 27 \
  --input_mode zv \
  --image_size "$IMAGE_SIZE" \
  --stage joint \
  --epochs "$EPOCHS" \
  --batch_size "$BATCH_SIZE" \
  --num_workers 0 \
  --lr "$LR" \
  --weight_decay "$WEIGHT_DECAY" \
  --num_queries 100 \
  --hidden_dim 256 \
  --backbone_dim 64 \
  --decoder_layers 6 \
  --nheads 8 \
  --min_mask_area 4 \
  --eval_interval 1 \
  --clip_grad_norm 0.1 \
  --device "$DEVICE"
