#!/usr/bin/env bash
# 0707 F1 최대화: G(csblur lr1e-4 ep50, F1 0.799)가 best_val ep35 → 학습 여유 있음.
# 병목=종류식별(g2 0.797). 레버: (1)더 긴 학습 (2)lr 더↑로 종류head 적응 (3)heavy init.
# 전부 E200 동일 데이터/평가셋. 변수 하나씩만. 순차(GPU 경합 회피).
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
MN=/workspace/cadence/mentoring_new
MENT=/workspace/cadence/Mentoring
DS=$MN/data/real_labelme_dataset_E200_noside
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz
CSBLUR=/workspace/cadence/runs/retrain_csblur_joint/best.pt
CSHEAVY=/workspace/cadence/runs/retrain_csblurheavy_joint/best.pt
LABELS=$MN/data/real_labels
MASTER=/workspace/cadence/runs/LMN_0707_master.log

run_one () {
  NAME=$1; INIT=$2; LR=$3; EPOCHS=$4
  OUT=/workspace/cadence/runs/${NAME}_0707
  LOG=/workspace/cadence/runs/${NAME}_0707.log
  EVALOUT=/workspace/cadence/eval_${NAME}_0707_test40
  echo ">>> [$NAME] init=$(basename $(dirname $INIT)) lr=$LR ep=$EPOCHS 시작 $(date -u)" | tee -a $MASTER
  cd $MENT
  echo "===== $NAME (init=$INIT lr=$LR ${EPOCHS}ep) $(date -u) =====" > $LOG
  python train_depth_vq_detector.py \
    --scene_manifest $DS/splits/train.json \
    --val_scene_manifest $DS/splits/val.json \
    --cad_memory $CAD --init_checkpoint $INIT --out_dir $OUT \
    --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr $LR --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
  echo ">>> [$NAME] eval(test 40장) $(date -u)" | tee -a $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DS/test_depth_symlinks --glob "shot*.npy" --label_dir $LABELS --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.30 --nms_iou_type mask --bbox_source mask \
    --diagnose_label_mismatch --save_predictions >> $LOG 2>&1
  echo ">>> [$NAME] 결과:" | tee -a $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
  python3 -c "import json;h=json.load(open(\"$OUT/history.json\"));best=min(h,key=lambda e:e[\"val\"][\"loss_total\"]);print(\"  best_val ep=%d loss=%.3f (last ep=%d loss=%.3f)\"%(best[\"epoch\"],best[\"val\"][\"loss_total\"],h[-1][\"epoch\"],h[-1][\"val\"][\"loss_total\"]))" 2>&1 | tee -a $MASTER
  echo "" | tee -a $MASTER
}

echo "===== LMN 무인 시작 $(date -u) =====" > $MASTER
run_one "L_csblur_lr1e4_ep80" $CSBLUR  1e-4 80   # G 학습 더 (best@35였으니 여유)
run_one "M_csblur_lr2e4_ep50" $CSBLUR  2e-4 50   # lr 더↑ = 종류head 더 밀기
run_one "N_heavy_lr1e4_ep80"  $CSHEAVY 1e-4 80   # J(heavy 0.769) + 더 긴 학습
echo "===== LMN 무인 완료 $(date -u) =====" | tee -a $MASTER

# 대칭쌍 병합 후처리 채점 (학습 불필요)
echo "===== 대칭병합 채점 (L/M/N) $(date -u) =====" | tee -a $MASTER
cd /workspace/cadence
python3 symmerge_score.py \
  eval_L_csblur_lr1e4_ep80_0707_test40 \
  eval_M_csblur_lr2e4_ep50_0707_test40 \
  eval_N_heavy_lr1e4_ep80_0707_test40 2>&1 | tee -a $MASTER
echo "===== 전체 완료 $(date -u) =====" | tee -a $MASTER
