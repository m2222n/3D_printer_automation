#!/usr/bin/env bash
# 23클래스 3판 정식 재-eval
# 7/8 밤 eval 실패 원인:
#   ① --cad_memory 인자를 eval 스크립트가 안 받음 (argparse 즉사)
#   ② GT 라벨이 27클래스 이름 그대로라 병합 예측과 문자열 불일치 → 부당 오답
# fix: --cad_memory 제거 + 4쌍 병합한 라벨셋(real_labels_23cls) 사용 + nms 0.30(LMN 성공값)
set -e
export PATH=/opt/conda/bin:$PATH
cd /workspace/cadence
MN=/workspace/cadence/mentoring_new
DEPTHDIR=$MN/data/real_labelme_dataset_E200_noside/test_depth_symlinks_t100
SRC=$MN/data/real_labels
DST=$MN/data/real_labels_23cls
MASTER=/workspace/cadence/runs/T23cls_reeval_master.log

# ── 1) 병합 라벨셋 생성 (4쌍 → 대표 이름) ──────────────────────────
python3 - <<'PY'
import json, glob, os, shutil
SRC="/workspace/cadence/mentoring_new/data/real_labels"
DST="/workspace/cadence/mentoring_new/data/real_labels_23cls"
MERGE = {
    "09_guide_paper_r": "07_guide_paper_l",
    "guide_paper_roll_cover_right": "guide_paper_roll_cover_left",
    "r_guide_a_r": "r_guide_a_l",
    "06_sol_block_back": "03_sol_block_front",
}
os.makedirs(DST, exist_ok=True)
n_files=n_relabel=0
for f in glob.glob(os.path.join(SRC,"*.json")):
    d=json.load(open(f))
    for s in d.get("shapes",[]):
        if s["label"] in MERGE:
            s["label"]=MERGE[s["label"]]; n_relabel+=1
    json.dump(d, open(os.path.join(DST,os.path.basename(f)),"w"))
    n_files+=1
print(f"[merge] files={n_files} relabeled_shapes={n_relabel}")
PY

echo "===== 23cls 재-eval 시작 $(date -u) =====" > $MASTER

reeval () {
  NAME=$1
  OUT=/workspace/cadence/runs/${NAME}
  EVALOUT=/workspace/cadence/eval_${NAME}_test102_reeval
  LOG=/workspace/cadence/runs/${NAME}_reeval.log
  echo ">>> [$NAME] eval(test 102장, 23cls, 병합라벨) $(date -u)" | tee -a $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DEPTHDIR --glob "shot*.npy" --label_dir $DST --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.30 --nms_iou_type mask --bbox_source mask \
    --diagnose_label_mismatch --save_predictions > $LOG 2>&1 || echo "  [ERR] eval 실패 → $LOG 확인" | tee -a $MASTER
  cd /workspace/cadence
  echo ">>> [$NAME] 결과:" | tee -a $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
  echo "" | tee -a $MASTER
}

reeval "T23_csblur_lr1e4_ep80"
reeval "T23_csblur_lr1.5e4_ep80"
reeval "T23_heavy_lr1e4_ep80"
echo "===== 23cls 재-eval 완료 $(date -u) =====" | tee -a $MASTER
echo "" | tee -a $MASTER
echo "[참고] 27cls 최고: L판 F1 0.818 / 대칭병합 후처리 0.805 / test100 재학습 0.684" | tee -a $MASTER
