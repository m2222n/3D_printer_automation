#!/usr/bin/env bash
set -euo pipefail

REAL_ROOT=${REAL_ROOT:-./data/real_labelme_dataset_C}
LABEL_DIR=${LABEL_DIR:-./data/real_labels}
CKPT=${CKPT:-./runs/depth_vq_detector_C_real_finetuned/best.pt}
OUT_DIR=${OUT_DIR:-./eval_real_C_test_s050_nms030_iou025}
SCORE_THRESH=${SCORE_THRESH:-0.50}
NMS_THRESH=${NMS_THRESH:-0.30}
IOU_THRESH=${IOU_THRESH:-0.25}
TMP_DEPTH_DIR=${TMP_DEPTH_DIR:-$REAL_ROOT/test_depth_symlinks}

python ./tools/link_real_split_depths.py \
  --split_json "$REAL_ROOT/splits/test.json" \
  --out_dir "$TMP_DEPTH_DIR"

python eval_real_depth_vq_detector.py \
  --checkpoint "$CKPT" \
  --depth_dir "$TMP_DEPTH_DIR" \
  --glob "shot_*_g1.npy" \
  --label_dir "$LABEL_DIR" \
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
