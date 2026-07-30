#!/usr/bin/env bash
# ============================================================================
# cross-session 촬영분 추론 — 7/31 공장 촬영 → 6000에서 바로 돌리기
# ============================================================================
# ⭐ 왜 미리 만드나: 금요일 촬영 후 경로·파라미터를 다시 찾으면 시간이 든다.
#    7/29 CPU 평가에 쓴 것과 **완전히 동일한 조건**을 박아둬서, 결과 차이가
#    "조건 차이"가 아니라 **"세션 차이"임이 보장되게** 한다.
#
# 🚨 이 스크립트의 목적 = 하나의 질문에 답하는 것:
#    "학습에 쓰지 않은 새 환경에서도 인식이 유지되는가?"
#
#    비교 기준(7/29, 학습에 쓴 세션): F1 0.8184 / precision 0.855 / recall 0.785
#    ⚠️ 단 그 값은 train이 섞인 값 = 재현 확인이지 일반화 측정이 아니다.
#       이번 값이 처음으로 나오는 **진짜 일반화 지표**다.
#
# ⚠️ 라벨이 없으면 F1은 못 낸다(labelme 라벨링 필요). 라벨 없이도 가능한 것:
#    검출 건수·신뢰도·z 분포 → "찾긴 찾나"의 육안 확인. 그래서 두 모드를 지원한다.
#
# 사용법:
#   # 라벨 없이 (촬영 직후 바로) — 검출되는지만 확인
#   bash eval_crosssession.sh /data/jtm/blaze_crosssession_0731 nolabel
#
#   # 라벨 붙인 뒤 — F1 비교
#   bash eval_crosssession.sh /data/jtm/blaze_crosssession_0731 labeled
# ============================================================================
set -euo pipefail

CAPTURE_DIR="${1:?사용법: bash eval_crosssession.sh <촬영디렉토리> [nolabel|labeled]}"
MODE="${2:-nolabel}"

VENV="/data/jtm/depth_venv/bin/python"
CKPT="/data/jtm/a100_backup_0710/checkpoints/extracted/runs/T100_csblur_lr1e4_ep80/best.pt"
REPO="/home/jtm/3D_printer_automation"
EVAL_DIR="$REPO/bin_picking/depth_track/mentoring_new"
OUT_DIR="${CAPTURE_DIR}_eval"

# npy가 촬영 디렉토리에 바로 있는 경우와 npy/ 하위에 있는 경우 모두 대응
if compgen -G "$CAPTURE_DIR/shot*.npy" > /dev/null; then
  DEPTH_DIR="$CAPTURE_DIR"
elif compgen -G "$CAPTURE_DIR/npy/shot*.npy" > /dev/null; then
  DEPTH_DIR="$CAPTURE_DIR/npy"
else
  echo "🔴 shot*.npy 를 못 찾음: $CAPTURE_DIR"; exit 1
fi

N=$(ls "$DEPTH_DIR"/shot*.npy | wc -l)
echo "============================================================"
echo " cross-session 추론"
echo "   촬영분   : $DEPTH_DIR ($N 장)"
echo "   모드     : $MODE"
echo "   비교기준 : 7/29 학습세션 F1 0.8184 (train 섞인 값)"
echo "============================================================"

# ⭐ 조건 메모 먼저 보여준다 — 어느 조건이 취약한지 해석할 때 필요
if [ -f "$CAPTURE_DIR/capture_meta.json" ]; then
  echo ""
  echo "[촬영 조건]"
  $VENV - "$CAPTURE_DIR/capture_meta.json" <<'PY'
import json, sys, collections
m = json.load(open(sys.argv[1]))
for k, v in sorted(m.get("conditions", {}).items()):
    print(f"  c{k}: {v}")
shots = m.get("shots", {})
cnt = collections.Counter(str(s.get("condition")) for s in shots.values())
ok = sum(1 for s in shots.values() if s.get("ok"))
print(f"  장수: {dict(sorted(cnt.items()))} / OK 판정 {ok}/{len(shots)}")
meds = [s.get("median_mm", 0) for s in shots.values() if s.get("median_mm")]
if meds:
    print(f"  거리 중앙값: {min(meds)}~{max(meds)}mm  (부품 대역 400~600 확인)")
PY
else
  echo "⚠️ capture_meta.json 없음 — 조건 기록 확인 불가"
fi

mkdir -p "$OUT_DIR"
cd "$EVAL_DIR"

# 7/29와 동일 파라미터 (조건을 고정해 세션 차이만 남긴다)
COMMON=(
  --checkpoint "$CKPT"
  --depth_dir  "$DEPTH_DIR"
  --out_dir    "$OUT_DIR"
  --glob 'shot*.npy'
  --match_key cad_id --eval_mode mask
  --iou_thresh 0.25 --score_thresh 0.45 --mask_thresh 0.5 --score_mode det
  --nms_iou_thresh 0.5 --nms_iou_type mask --bbox_source mask
  --center_crop '1/6,5/6' --depth_keep_range '0.40,0.60'
  --save_predictions
)

if [ "$MODE" = "labeled" ]; then
  LABEL_DIR="${LABEL_DIR:-$CAPTURE_DIR/labelme_json}"
  [ -d "$LABEL_DIR" ] || { echo "🔴 라벨 디렉토리 없음: $LABEL_DIR"; exit 1; }
  echo ""; echo "▶ 라벨 모드 — F1 산출"
  PYTHONPATH="$REPO" $VENV eval_real_depth_vq_detector.py "${COMMON[@]}" \
    --label_dir "$LABEL_DIR" --diagnose_label_mismatch 2>&1 | tail -30
  echo ""
  echo "=== 🚨 핵심 비교 ==="
  $VENV - "$OUT_DIR/eval_real_metrics.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))["summary"]
f1, p, r = s["f1_micro"], s["precision_micro"], s["recall_micro"]
base = 0.8184
print(f"  새 세션 F1 : {f1:.4f}  (precision {p:.3f} / recall {r:.3f})")
print(f"  학습 세션   : {base:.4f}")
print(f"  차이        : {f1-base:+.4f}  ({100*(f1-base)/base:+.1f}%)")
print()
if f1 >= base - 0.05:
    print("  🟢 유지됨 → 일반화 OK. 로봇 연동으로 진행 가능")
elif f1 >= base - 0.20:
    print("  🟡 하락 → 실측 데이터 보강 필요. 8월 계획에 반영")
else:
    print("  🔴 폭락 → 다른 공정 분류의 cross-session 0.34~0.70 전례와 같은 양상.")
    print("     ⭐ 8월 최우선 = 실측 데이터 확대·재학습 (각도·통신보다 앞)")
PY
else
  echo ""; echo "▶ 라벨 없는 모드 — 검출되는지만 확인"
  # eval은 라벨을 강제하므로(:418) 전용 스크립트를 쓴다.
  # ✅ 7/29 실측 5장으로 검증됨: 장당 8.40건(기준 8.01의 105%), shot_001_g1=9건 일치
  PYTHONPATH="$REPO" $VENV "$REPO/bin_picking/depth_track/scripts/detect_nolabel.py" \
    --depth_dir "$DEPTH_DIR" --out_dir "${OUT_DIR}_detect" \
    --checkpoint "$CKPT" 2>&1 | tail -25
  echo ""
  echo "⏭️ F1(맞게 찾았는지)을 보려면 labelme 라벨링 후:"
  echo "   bash $0 $CAPTURE_DIR labeled"
fi

echo ""
echo "산출물: $OUT_DIR"
echo ""
echo "다음: 6요소 좌표까지 보려면"
echo "  PYTHONPATH=$REPO $VENV $REPO/bin_picking/src/pipeline/depth_track_to_6elements.py \\"
echo "    --pred-dir $OUT_DIR/predictions --out-dir ${OUT_DIR}_6elem --depth-dir $DEPTH_DIR"
