#!/usr/bin/env bash
# 26클래스(roll_cover 1쌍만 병합) 재학습 = 병목직격 3판
#   P: 26cls 순수 (lr 1e-4)         = 정직 baseline
#   Q: 26cls + loss_cad_ce 2.0       = 종류식별 loss 강화(병목 직격)
#   R: 26cls + 약한 노이즈/결측 aug   = 실측 도메인갭 적응
# 공통: csblur best.pt init, real 200장(26cls), ep50, image 320x576, num_workers 0
# eval: test102 + 26cls 병합라벨(real_labels_26cls) + --cad_memory 제거 + nms 0.30
set -e
export PATH=/opt/conda/bin:$PATH
cd /workspace/cadence
MENT=/workspace/cadence/mentoring_new
MN=/workspace/cadence/mentoring_new
DS=$MN/data/real_labelme_dataset_26cls
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank_26cls.npz
CSBLUR=/workspace/cadence/runs/retrain_csblur_joint/best.pt
DEPTHDIR=$MN/data/real_labelme_dataset_E200_noside/test_depth_symlinks_t100
LABELS26=$MN/data/real_labels_26cls
MASTER=/workspace/cadence/runs/T26cls_master.log

# ── 26cls 병합 라벨셋 생성 (roll_cover_right -> left) ──
python3 - <<'PY'
import json, glob, os
SRC="/workspace/cadence/mentoring_new/data/real_labels"
DST="/workspace/cadence/mentoring_new/data/real_labels_26cls"
MERGE={"guide_paper_roll_cover_right":"guide_paper_roll_cover_left"}
os.makedirs(DST,exist_ok=True)
nf=nr=0
for f in glob.glob(os.path.join(SRC,"*.json")):
    d=json.load(open(f))
    for s in d.get("shapes",[]):
        if s["label"] in MERGE: s["label"]=MERGE[s["label"]]; nr+=1
    json.dump(d,open(os.path.join(DST,os.path.basename(f)),"w"))
    nf+=1
print(f"[merge label] files={nf} relabeled={nr}")
PY

echo "===== 26cls 병목직격 3판 시작 $(date -u) =====" > $MASTER

run_one () {
  NAME=$1; TRAIN=$2; shift 2; EXTRA="$@"
  OUT=/workspace/cadence/runs/${NAME}
  LOG=/workspace/cadence/runs/${NAME}.log
  EVALOUT=/workspace/cadence/eval_${NAME}_test102
  echo ">>> [$NAME] train ($TRAIN) $EXTRA $(date -u)" | tee -a $MASTER
  cd $MENT
  python $TRAIN \
    --scene_manifest $DS/splits/train_t100.json \
    --val_scene_manifest $DS/splits/val_t100.json \
    --cad_memory $CAD --init_checkpoint $CSBLUR --out_dir $OUT \
    --num_classes 26 --input_mode zv --image_size "320,576" --stage joint \
    --epochs 50 --batch_size 2 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 \
    $EXTRA > $LOG 2>&1
  echo ">>> [$NAME] eval(test 102장, 26cls, 병합라벨) $(date -u)" | tee -a $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DEPTHDIR --glob "shot*.npy" --label_dir $LABELS26 --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.30 --nms_iou_type mask --bbox_source mask \
    --diagnose_label_mismatch --save_predictions >> $LOG 2>&1 || echo "  [ERR] eval 실패" | tee -a $MASTER
  cd /workspace/cadence
  echo ">>> [$NAME] 결과:" | tee -a $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
  python3 -c "import json;h=json.load(open('$OUT/history.json'));b=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last=%d)'%(b['epoch'],b['val']['loss_total'],h[-1]['epoch']))" 2>&1 | tee -a $MASTER
  echo "" | tee -a $MASTER
}

# P: 정직 baseline
run_one "T26_P_baseline_lr1e4"  train_depth_vq_detector.py
# Q: cad_ce loss 강화 (종류식별 직격)
run_one "T26_Q_cadce2_lr1e4"    train_depth_vq_detector_cadce2.py
# R: 약한 노이즈/결측 aug (도메인갭)
run_one "T26_R_aug_lr1e4"       train_depth_vq_detector.py \
    --train_noise_sigma_m 0.003 --train_random_dropout_prob 0.1 --train_hole_prob 0.5 --train_boundary_dropout_prob 0.15

echo "===== 26cls 3판 완료 $(date -u) =====" | tee -a $MASTER
echo "[참고] 27cls test100 0.684 / 23cls(4쌍병합·부당) 0.750 / L판 test40 0.818" | tee -a $MASTER
