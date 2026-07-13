#!/usr/bin/env bash
# ============================================================================
# depth_track 발표 성능(F1 0.684) 재현 스크립트
# ----------------------------------------------------------------------------
# 발표 메인 지표 = 27종 실측 test100(102 scene) F1_micro 0.6836
#   (위치 IoU 0.843 / 저장된 원본 결과: data/checkpoints/.../eval_real_metrics.json)
#
# 이 스크립트는 그 결과를 낸 eval 명령을 "정확히 그대로" 재현한다.
# eval 파라미터는 저장된 summary(iou 0.25·score 0.45·nms 0.5·center_crop 1/6,5/6
#   ·depth_keep 0.40,0.60·mask 모드)를 그대로 박음.
#
# ⚠️ GPU 필수. 학습 서버(A100 등)에서 실행. 6000엔 GPU 없음.
# ⚠️ 발표 eval에 쓴 test split 심볼릭·라벨 변환본은 A100 현지 산출물이라
#    A100에서 실행하는 것이 가장 확실(2026-07-13 확인: A100에 전부 생존).
#    다른 GPU 서버로 옮기면 depth_dir/label_dir을 그 서버 경로로 바꿀 것.
# ============================================================================
set -euo pipefail

# --- 실행 위치: 코드 루트(mentoring_new의 부모) ---
# A100이면 CADENCE=/workspace/cadence, 회사 편입본이면 이 파일 기준 상위
CADENCE="${CADENCE:-/workspace/cadence}"

# --- 발표 메인 모델 + 발표 test 데이터 (A100 경로, 2026-07-13 생존 확인) ---
CKPT="${CKPT:-$CADENCE/runs/T100_csblur_lr1e4_ep80/best.pt}"
DEPTH_DIR="${DEPTH_DIR:-$CADENCE/mentoring_new/data/real_labelme_dataset_E200_noside/test_depth_symlinks_t100}"
LABEL_DIR="${LABEL_DIR:-$CADENCE/mentoring_new/data/real_labels}"
OUT_DIR="${OUT_DIR:-$CADENCE/runs/_reproduce_f1_0684_$(hostname)}"

cd "$CADENCE/mentoring_new"

echo "=== depth_track F1 0.684 재현 eval $(date) ==="
echo "  checkpoint : $CKPT"
echo "  depth_dir  : $DEPTH_DIR  ($(ls "$DEPTH_DIR"/*.npy 2>/dev/null | wc -l) scene)"
echo "  label_dir  : $LABEL_DIR"
echo "  out_dir    : $OUT_DIR"
echo ""

python eval_real_depth_vq_detector.py \
  --checkpoint       "$CKPT" \
  --depth_dir        "$DEPTH_DIR" \
  --label_dir        "$LABEL_DIR" \
  --out_dir          "$OUT_DIR" \
  --glob             'shot*.npy' \
  --match_key        cad_id \
  --eval_mode        mask \
  --iou_thresh       0.25 \
  --score_thresh     0.45 \
  --mask_thresh      0.5 \
  --score_mode       det \
  --nms_iou_thresh   0.5 \
  --nms_iou_type     mask \
  --bbox_source      mask \
  --center_crop      '1/6,5/6' \
  --depth_keep_range '0.40,0.60' \
  --save_predictions \
  --diagnose_label_mismatch

echo ""
echo "=== 재현 결과 vs 발표 원본 대조 ==="
python - "$OUT_DIR/eval_real_metrics.json" <<'PY'
import json, sys
got = json.load(open(sys.argv[1]))["summary"]
ref_f1 = 0.683649289099526   # 발표 원본 f1_micro
g = got["f1_micro"]
print(f"  재현 f1_micro = {g:.6f}")
print(f"  발표 f1_micro = {ref_f1:.6f}")
print(f"  차이          = {abs(g-ref_f1):.6f}")
print("  ✅ 재현 성공 (동일)" if abs(g-ref_f1) < 1e-4 else "  ⚠️ 불일치 — 경로/데이터/버전 확인")
print(f"  matched_iou   = {got.get('mean_matched_iou_macro'):.4f} (발표 0.843)")
PY
