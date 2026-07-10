#!/usr/bin/env bash
set -euo pipefail

CKPT=${CKPT:-./runs/depth_vq_detector_A_sensorized/best.pt}
OUT_DIR=${OUT_DIR:-./eval_real_A_sensorized}

python eval_real_depth_vq_detector.py \
  --checkpoint "$CKPT" \
  --depth_dir ./data/real_depth/npy \
  --glob "shot_*_g1.npy" \
  --label_dir ./data/real_labels \
  --out_dir "$OUT_DIR" \
  --match_key cad_id \
  --eval_mode mask \
  --iou_thresh 0.25 \
  --real_uint16_max_depth_m 10.0 \
  --center_crop "1/6,5/6" \
  --depth_keep_range "0.40,0.60" \
  --score_thresh ${SCORE_THRESH:-0.10} \
  --mask_thresh ${MASK_THRESH:-0.5} \
  --score_mode det \
  --nms_iou_thresh ${NMS_THRESH:-0.10} \
  --nms_iou_type mask \
  --bbox_source mask \
  --diagnose_label_mismatch \
  --save_predictions
