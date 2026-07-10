#!/usr/bin/env bash
set -euo pipefail

CKPT=${CKPT:-./runs/depth_vq_detector_AB_blenderproc_sensorized/best.pt}
OUT_DIR=${OUT_DIR:-./eval_real_AB_blenderproc_s050_nms030_iou025}
SCORE_THRESH=${SCORE_THRESH:-0.50}
NMS_THRESH=${NMS_THRESH:-0.30}
IOU_THRESH=${IOU_THRESH:-0.25}

python eval_real_depth_vq_detector.py \
  --checkpoint "$CKPT" \
  --depth_dir ./data/real_depth/npy \
  --glob "shot_*_g1.npy" \
  --label_dir ./data/real_labels \
  --out_dir "$OUT_DIR" \
  --match_key cad_id \
  --eval_mode mask \
  --iou_thresh "$IOU_THRESH" \
  --real_uint16_max_depth_m 10.0 \
  --center_crop "1/6,5/6" \
  --depth_keep_range "0.40,0.60" \
  --score_thresh "$SCORE_THRESH" \
  --mask_thresh 0.5 \
  --score_mode det \
  --nms_iou_thresh "$NMS_THRESH" \
  --nms_iou_type mask \
  --bbox_source mask \
  --diagnose_label_mismatch \
  --save_predictions
