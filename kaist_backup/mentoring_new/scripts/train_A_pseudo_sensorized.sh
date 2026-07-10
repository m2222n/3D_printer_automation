#!/usr/bin/env bash
set -euo pipefail

CKPT_INIT=${CKPT_INIT:-./runs/depth_detector_warmup_split/best.pt}
CAD_MEMORY=${CAD_MEMORY:-./runs/cad_pointnet2/cad_memory_bank.npz}
TRAIN_MANIFEST=${TRAIN_MANIFEST:-./data/2d_dataset/splits/train.json}
VAL_MANIFEST=${VAL_MANIFEST:-./data/2d_dataset/splits/val.json}
OUT_DIR=${OUT_DIR:-./runs/depth_vq_detector_A_sensorized}

python train_depth_vq_detector.py \
  --scene_manifest "$TRAIN_MANIFEST" \
  --val_scene_manifest "$VAL_MANIFEST" \
  --cad_memory "$CAD_MEMORY" \
  --init_checkpoint "$CKPT_INIT" \
  --out_dir "$OUT_DIR" \
  --num_classes 27 \
  --input_mode zv \
  --image_size "320,576" \
  --stage joint \
  --epochs ${EPOCHS:-100} \
  --batch_size ${BATCH_SIZE:-4} \
  --num_workers ${NUM_WORKERS:-4} \
  --lr ${LR:-1e-4} \
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
