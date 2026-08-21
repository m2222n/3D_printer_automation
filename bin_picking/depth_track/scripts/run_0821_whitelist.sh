#!/usr/bin/env bash
# ============================================================================
# 공정 화이트리스트 + thr 0.20 정식 측정 (2026-08-21)
# ============================================================================
# 🎯 무엇을 재나 = 8/21에 신설한 "공정 제외 6종 예측 버리기"가 **thr 0.20에서**
#    F1을 얼마 올리는가. 8/21 오전 계산은 thr 0.45 예측 파일로 낸 것이라
#    채택값(0.20)에서의 정식 수치가 없었다.
#
# ⭐ 변수는 화이트리스트 **하나뿐**이다. 나머지(thr 0.20·iou·mask·nms·crop·
#    depth_keep·라벨·데이터·체크포인트)는 run_0820_thr020.sh와 완전히 동일하게 둔다
#    ⇒ 차이가 "조건 차이"가 아니라 **"화이트리스트 유무"임이 보장**된다.
#
# 🚨 모델 = T100(BASE)만 쓴다. 재학습 C는 90장을 학습했으므로(train72+val18)
#    거기서 재면 train-on-test다(8/20에 밟은 함정).
#    T100은 7/7자라 8/18 촬영보다 한 달 이상 앞서 물리적으로 학습했을 수 없다.
#
# ✅ 결과 (2026-08-21, T100, thr 0.20) — 이 스크립트로 재현 가능
#      [0818] 예측 641건 · 제외종 34건(5.3%)
#              현행        TP 371 FP 270 FN 259  F1 0.5838   ← 8/20 값 정확히 재현
#              +화이트리스트 TP 371 FP 236 FN 259  F1 0.5998  (+0.0160 · P +0.0324)
#      [c1]   예측 91건 · 제외종 8건(8.8%)
#              현행 F1 0.4041 → +화이트리스트 0.4216 (+0.0175)
#      ⇒ recall은 두 조건 모두 **정확히 불변**(설계 그대로: precision 전용 게이트)
#
# 🚨🚨 이 측정에서 발견한 것 = **A100 평가기가 7/6자로 낡아 8/19 동치 처리가 없었다.**
#    첫 실행이 TP 341/FP 300/F1 0.5366으로 나와 8/20 기록(371/270/0.5838)과 어긋났고,
#    데이터·라벨 md5 대조(둘 다 동일) → 플래그 대조(동일) → **평가기 diff**에서 원인이 나왔다.
#    `EQUIVALENT_CAD_NAMES`(14_13 → 13_variant)가 A100 쪽에 없어 맞은 것을
#    FP·FN으로 이중 계상하고 있었다. 6000 평가기를 동기화한 뒤 8/20 값이 재현됐다.
#    ⭐ 교훈 = **"같은 조건"이라고 쓰기 전에 코드 버전까지 대조할 것**
#       (원본 백업 = `eval_real_depth_vq_detector.py.BACKUP_0706`)
#
# 🚨🚨 정정 (같은 날, 태민님 지적) = 이 스크립트 첫 커밋에 나는
#    *"c1/c2/c3에는 14_13 라벨이 없어 8/20 배포 판정에 영향이 없다"* 고 적었다.
#    **확인하지 않고 쓴 단정이었고 틀렸다** — 조건별 전수 확인 결과:
#        c1  10장 GT 102  14_13 **2건**
#        c2  10장 GT 107  14_13 **9건**
#        c3  10장 GT  90  14_13 **7건**
#        0818 90장 GT 630 14_13 **0건**  ← 0818은 병합 라벨링이라 원래 0
#    ⚠️ 처음엔 "c1에 18건"이라 셌는데 그것도 틀렸다 — 라벨 디렉토리(`real_labels_c1`)를
#       c1/c2/c3가 **공유**하므로 디렉토리 전체를 세면 세 조건이 합쳐진다.
#       **조건별 npy 파일명으로 걸러야** 맞다(2+9+7=18이 그 합계였다).
#    ⇒ **8/20 재판정(7모델×4조건) 전체가 낡은 평가기 값**이고,
#      동기화 후 재측정하니 **c2 기준선이 0.0985 → 0.1281로 올라가**
#      *"C만 c1·c2 동반 상승"* 이라는 8/20 근거가 **무너졌다**(C의 c2 0.1170 < 0.1281).
#    📌 **배포 보류(T100 유지) 결론은 유지되나 근거가 바뀐다**
#      = *"이득이 작아서"* 가 아니라 *"c2가 기준선 미달"* 이다.
#    ⭐ grep 한 번이면 됐다 → [[never-state-unverified]]
# ============================================================================
set -uo pipefail
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
MN=/workspace/cadence/mentoring_new
CKPT=/workspace/cadence/runs/T100_csblur_lr1e4_ep80/best.pt
THR=0.20
OUTDIR=/workspace/cadence/eval_0821_wl
MASTER=/workspace/cadence/runs/V0821_whitelist.log

# 공정 제외 6종 — 회사 grasp_database.yaml의 pickability=not_pickable에서 온 값.
# (top_inner_sheet004는 모델 27종에 없어 제외 목록에 있어도 무영향)
EXCLUDED="11_sw_block 17_mks_holder bracket_sensor2 bracket_case main_body top_inner_sheet"

echo "===== 0821 화이트리스트 측정 (thr $THR, T100) $(date -u) =====" > $MASTER
echo "제외 6종: $EXCLUDED" | tee -a $MASTER
echo "" | tee -a $MASTER

run_one () {  # $1=cond $2=labeldir
  OUT=$OUTDIR/$1
  mkdir -p $OUT
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $CKPT \
    --depth_dir $MN/data/real_depth_$1/npy --glob 'shot*.npy' \
    --label_dir $2 --out_dir $OUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 \
    --real_uint16_max_depth_m 10.0 \
    --center_crop '1/6,5/6' --depth_keep_range '0.40,0.60' \
    --score_thresh $THR --mask_thresh 0.5 --score_mode det \
    --nms_iou_thresh 0.5 --nms_iou_type mask --bbox_source mask \
    --diagnose_label_mismatch --save_predictions > /dev/null 2>&1
}

# 화이트리스트를 예측 JSON에 사후 적용해 재채점한다.
# ⭐ 평가기를 고치지 않는 이유 = 평가기를 건드리면 "게이트 효과"와 "평가기 변경"이
#    섞여 원인을 못 가른다. 같은 예측에 필터만 걸어 두 수치를 낸다.
score_py () {
python - "$1" "$EXCLUDED" <<'PY'
import json,sys,glob,os
from pathlib import Path
out=Path(sys.argv[1]); excl=set(sys.argv[2].split())
EQ={'14_13':'13_variant'}
def canon(n):
    n=str(n).split('__')[0]
    return EQ.get(n,n)

pj=out/'all_predictions.json'
if not pj.exists():
    cand=sorted(out.glob('**/all_predictions.json'))
    if not cand: print('  ERR: all_predictions.json 없음'); sys.exit(0)
    pj=cand[0]
scenes=json.load(open(pj))

# GT 로드 — 평가기와 같은 라벨 디렉토리를 쓴다
import re
lbl=Path(sys.argv[1]).name
# 마스크 IoU 재계산은 무겁다. 여기서는 "제외종 예측 건수"만 세고
# 평가기 정식 수치(TP/FP/FN)에서 FP만 차감해 F1을 낸다.
# 🚨 근거 = 제외 6종은 GT에 0건이므로 그 예측은 전부 FP다(TP를 건드릴 수 없다).
tot=ex=0
for sc in scenes.values():
    for p in sc.get('predictions',[]):
        tot+=1
        if canon(p.get('cad_id')) in excl: ex+=1

m=json.load(open(out/'eval_real_metrics.json'))['summary']
tp,fp,fn=m['tp'],m['fp'],m['fn']
def f1(tp,fp,fn):
    P=tp/(tp+fp) if tp+fp else 0.0
    R=tp/(tp+fn) if tp+fn else 0.0
    return P,R,(2*P*R/(P+R) if P+R else 0.0)
P0,R0,F0=f1(tp,fp,fn)
P1,R1,F1_=f1(tp,fp-ex,fn)
print(f"  예측 {tot}건 · 제외종 {ex}건 ({ex/tot*100:.1f}%)" if tot else "  예측 0건")
print(f"  현행        TP {tp:4d} FP {fp:4d} FN {fn:4d}  P {P0:.4f} R {R0:.4f} F1 {F0:.4f}")
print(f"  +화이트리스트 TP {tp:4d} FP {fp-ex:4d} FN {fn:4d}  P {P1:.4f} R {R1:.4f} F1 {F1_:.4f}")
print(f"  ⇒ F1 {F1_-F0:+.4f} · P {P1-P0:+.4f} · R {R1-R0:+.4f}")
PY
}

for pair in "0818 $MN/data/real_labels_0818" "c1 $MN/data/real_labels_c1"; do
  set -- $pair
  echo "[$1]" | tee -a $MASTER
  run_one $1 $2
  score_py $OUTDIR/$1 | tee -a $MASTER
  echo "" | tee -a $MASTER
done

echo "완료 $(date -u)" | tee -a $MASTER
