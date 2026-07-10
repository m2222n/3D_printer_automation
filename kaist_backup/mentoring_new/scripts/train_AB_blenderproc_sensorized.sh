#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT=${DATA_ROOT:-./data/2d_dataset_B_blenderproc}
OUT_DIR=${OUT_DIR:-./runs/depth_vq_detector_AB_blenderproc_sensorized}
CAD_MEMORY=${CAD_MEMORY:-./runs/cad_pointnet2/cad_memory_bank.npz}
INIT_CKPT=${INIT_CKPT:-./runs/depth_detector_warmup_split/best.pt}
EPOCHS=${EPOCHS:-100}
BATCH_SIZE=${BATCH_SIZE:-4}
NUM_WORKERS=${NUM_WORKERS:-4}

python train_depth_vq_detector.py \
  --scene_manifest "$DATA_ROOT/splits/train.json" \
  --val_scene_manifest "$DATA_ROOT/splits/val.json" \
  --cad_memory "$CAD_MEMORY" \
  --init_checkpoint "$INIT_CKPT" \
  --out_dir "$OUT_DIR" \
  --num_classes 27 \
  --input_mode zv \
  --image_size "320,576" \
  --stage joint \
  --epochs "$EPOCHS" \
  --batch_size "$BATCH_SIZE" \
  --num_workers "$NUM_WORKERS" \
  --lr 1e-4 \
  --weight_decay 1e-4 \
  --num_queries 100 \
  --hidden_dim 256 \
  --backbone_dim 64 \
  --decoder_layers 6 \
  --nheads 8 \
  --train_depth_median_range "0.45,0.55" \
  --randomize_train_depth_median \
  --train_robust_depth_median_range "0.35,0.60" \
  --train_robust_prob 0.25 \
  --train_avg_pool_kernel 3 \
  --avg_pool_valid_threshold 0.05 \
  --pseudo_uint16_max_depth_m 10.0 \
  --train_noise_sigma_m 0.0015 \
  --train_noise_rel_sigma 0.002 \
  --train_random_dropout_prob 0.02 \
  --train_boundary_dropout_prob 0.35 \
  --train_boundary_radius 2 \
  --train_hole_prob 2.0 \
  --train_valid_ratio_range "0.04,0.08"
