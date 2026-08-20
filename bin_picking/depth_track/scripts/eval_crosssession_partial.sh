#!/usr/bin/env bash
# ============================================================================
# cross-session 부분 평가 — 라벨이 있는 장면만 골라 F1을 낸다
# ============================================================================
# ⭐ 왜 별도로 만드나: `eval_crosssession.sh labeled`는 촬영 디렉토리의 npy 전체를
#    돌리고 라벨이 없으면 **에러로 멈춘다**(`--missing_label error` 기본).
#    라벨링은 손이 많이 가서 한 번에 30장을 다 끝내기 어려우므로,
#    **라벨이 붙은 것만으로 중간 점검**할 수 있어야 한다.
#
# ⭐ 조건별로도 볼 수 있다. cross-session 촬영은 조건이 3개(c1/c2/c3)이고
#    난이도가 크게 다르다(부품 대역 픽셀 c1 17k / c2 33k / c3 170k).
#    c3은 땅바닥이 부품과 같은 거리 대역에 들어와 배경이 안 걸러진다
#    → 조건을 섞어 평균만 보면 원인이 묻힌다.
#
# 사용법:
#   bash eval_crosssession_partial.sh <촬영디렉토리>            # 라벨 있는 전부
#   bash eval_crosssession_partial.sh <촬영디렉토리> 'shot*_c1' # c1만
# ============================================================================
set -euo pipefail

CAPTURE_DIR="${1:?사용법: bash eval_crosssession_partial.sh <촬영디렉토리> [glob]}"
PATTERN="${2:-shot*}"

VENV="/data/jtm/depth_venv/bin/python"
CKPT="/data/jtm/a100_backup_0710/checkpoints/extracted/runs/T100_csblur_lr1e4_ep80/best.pt"
REPO="/home/jtm/3D_printer_automation"
EVAL_DIR="$REPO/bin_picking/depth_track/mentoring_new"
LABEL_DIR="${LABEL_DIR:-$CAPTURE_DIR/labelme_json}"

[ -d "$LABEL_DIR" ] || { echo "🔴 라벨 디렉토리 없음: $LABEL_DIR"; exit 1; }

# npy 위치 (디렉토리 직하 / npy 하위 모두 대응)
if compgen -G "$CAPTURE_DIR/shot*.npy" > /dev/null; then
  SRC_NPY="$CAPTURE_DIR"
elif compgen -G "$CAPTURE_DIR/npy/shot*.npy" > /dev/null; then
  SRC_NPY="$CAPTURE_DIR/npy"
else
  echo "🔴 shot*.npy 를 못 찾음: $CAPTURE_DIR"; exit 1
fi

# ⭐ 라벨이 있는 npy만 임시 디렉토리로 모은다(원본은 건드리지 않는다).
WORK="$CAPTURE_DIR/_partial_eval"
rm -rf "$WORK"; mkdir -p "$WORK/npy"

n=0; missing=0
for j in "$LABEL_DIR"/${PATTERN}.json; do
  [ -e "$j" ] || continue
  stem=$(basename "$j" .json)
  if [ -f "$SRC_NPY/$stem.npy" ]; then
    ln -sf "$SRC_NPY/$stem.npy" "$WORK/npy/$stem.npy"; n=$((n+1))
  else
    echo "  ⚠️ 라벨은 있는데 npy 없음: $stem"; missing=$((missing+1))
  fi
done

if [ "$n" -eq 0 ]; then
  echo "🔴 '$PATTERN' 에 해당하는 라벨이 없음. 라벨 파일명은 npy와 같아야 한다."
  echo "   예: shot_001_c1.npy ↔ shot_001_c1.json"
  ls "$LABEL_DIR" | head -5; exit 1
fi

echo "============================================================"
echo " cross-session 부분 평가"
echo "   패턴     : $PATTERN"
echo "   평가 장수: $n 장  (라벨 없는 것은 자동 제외)"
echo "   비교기준 : 7/29 학습세션 F1 0.8184 (⚠️ train 섞인 값)"
echo "============================================================"

OUT="$WORK/out"
cd "$EVAL_DIR"

# 7/29·eval_crosssession.sh 와 동일 파라미터 (조건 고정 = 세션 차이만 남긴다)
PYTHONPATH="$REPO" $VENV eval_real_depth_vq_detector.py \
  --checkpoint "$CKPT" --depth_dir "$WORK/npy" --out_dir "$OUT" \
  --glob 'shot*.npy' --match_key cad_id --eval_mode mask \
# ⭐⭐ score_thresh = 0.20 (2026-08-20 스윕으로 교체, 옛값 0.45)
#   8/18 90장 실측 스윕 — 0.10/0.15/0.20/0.30/0.45 중 **0.20이 최적점**(양쪽으로 하락).
#     0.45(옛) F1 0.5445 · R 0.500   |   ⭐0.20 F1 0.5838 · R 0.589   (+0.0393, 학습 불필요)
#   🚨 판정 근거는 F1이 아니라 **"집을 수 있는 부품 수"**:
#     GT 630개 중 집을 수 있는 것 **491 → 577개(+86)** = 77.9% → **91.6%(+13.7%p)**
#     추가 치명은 +9건뿐 ⇒ **9.6 : 1**로 이득.
#   ⚠️ 파지 "비율"은 95.5%→94.7%로 살짝 내려가는데 **분모(찾은 수)가 커져서**다.
#      비율만 보면 후퇴로 보이지만 **건수로는 크게 이득** — 여기서 헷갈리지 말 것.
#   📌 recall은 0.10에서 이미 포화(0.592) ⇒ **임계값을 더 낮춰도 안 나온다**
#      = 남은 recall 손실은 threshold가 아니라 모델이 후보를 안 내는 것.
  --iou_thresh 0.25 --score_thresh 0.20 --mask_thresh 0.5 --score_mode det \
  --nms_iou_thresh 0.5 --nms_iou_type mask --bbox_source mask \
  --center_crop '1/6,5/6' --depth_keep_range '0.40,0.60' \
  --save_predictions --label_dir "$LABEL_DIR" --diagnose_label_mismatch 2>&1 | tail -12

echo ""
$VENV - "$OUT/eval_real_metrics.json" <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1])); s = d["summary"]; per = d["per_scene"]
base = 0.8184
f1, p, r = s["f1_micro"], s["precision_micro"], s["recall_micro"]

print("=== 🚨 핵심 비교 ===")
print(f"  이번 세션 F1 : {f1:.4f}   (precision {p:.3f} / recall {r:.3f})")
print(f"  학습 세션    : {base:.4f}")
print(f"  차이         : {f1-base:+.4f}  ({100*(f1-base)/base:+.1f}%)")
print()

# ⭐ 위치 vs 종류 분리 — 폭락했을 때 원인이 어느 쪽인지 가른다.
#    (세척기 폭락은 "검출은 되는데 분류가 틀리는" 형태였을 수 있다)
st = sum(x.get("spatial_tp_ignore_label", 0) for x in per)
sf = sum(x.get("spatial_fp_ignore_label", 0) for x in per)
sn = sum(x.get("spatial_fn_ignore_label", 0) for x in per)
lc = sum(x.get("spatial_label_correct", 0) for x in per)
if st + sf + sn:
    sp = st / max(st + sf, 1); sr = st / max(st + sn, 1)
    print("=== 원인 분해 (위치 vs 종류) ===")
    print(f"  위치만 (라벨 무시) : F1 {2*sp*sr/max(sp+sr,1e-9):.4f}  (P {sp:.3f} / R {sr:.3f})")
    print(f"  그중 종류 정답     : {lc}/{st} = {lc/max(st,1):.3f}")
    print()
    if sr >= 0.85 and lc / max(st, 1) < 0.7:
        print("  ⭐ 해석 = 위치는 찾는데 종류를 틀린다 → 데이터 보강·RGB 융합 쪽")
    elif sr < 0.7:
        print("  ⭐ 해석 = 아예 못 찾는다 → 도메인 갭(조명·배경). 재촬영·재학습 쪽")

print("=== 조건별 ===")
by = collections.defaultdict(lambda: [0, 0, 0])
for x in per:
    key = x["file"].rsplit("_", 1)[-1].replace(".npy", "")
    by[key][0] += x.get("tp", 0); by[key][1] += x.get("fp", 0); by[key][2] += x.get("fn", 0)
for k in sorted(by):
    tp, fp, fn = by[k]
    pp = tp / max(tp + fp, 1); rr = tp / max(tp + fn, 1)
    print(f"  {k}: F1 {2*pp*rr/max(pp+rr,1e-9):.4f}  TP {tp} FP {fp} FN {fn}")

print()
if f1 >= base - 0.05:
    print("  🟢 유지됨 → 일반화 OK. 로봇 연동으로 진행 가능")
elif f1 >= base - 0.20:
    print("  🟡 하락 → 실측 데이터 보강 필요. 8월 계획에 반영")
else:
    print("  🔴 폭락 → 다른 공정 분류의 cross-session 0.34~0.70 전례와 같은 양상")
    print("     ⭐ 8월 최우선 = 실측 데이터 확대·재학습 (각도·통신보다 앞)")
print()
print("  ⚠️ 표본이 적으면 수치가 흔들린다. 조건별 장수를 함께 볼 것.")
PY

echo ""
echo "산출물: $OUT"
