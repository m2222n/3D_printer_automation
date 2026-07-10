#!/usr/bin/env bash
# 밤샘 무인: E판(200장 side제거X, 50ep) + F판(동일데이터, 30ep) 순차 fine-tune + 자동 eval(test 40장 전체)
# 병목=종류식별(위치F1 0.89 vs 종류acc 0.61, 좌우/앞뒤 대칭쌍 혼동). 데이터 2배(200장)+epoch 요인분리.
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1

MN=/workspace/cadence/mentoring_new
MENT=/workspace/cadence/Mentoring
DS=$MN/data/real_labelme_dataset_E200_noside
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz
INIT=/workspace/cadence/runs/retrain_csblur_joint/best.pt
LABELS=$MN/data/real_labels
MASTER=/workspace/cadence/runs/EF_0707_master.log

echo "===== EF 무인 시작 $(date -u) =====" > $MASTER

run_one () {
  NAME=$1; EPOCHS=$2
  OUT=/workspace/cadence/runs/${NAME}_0707
  LOG=/workspace/cadence/runs/${NAME}_0707.log
  EVALOUT=/workspace/cadence/eval_${NAME}_0707_test40
  echo ">>> [$NAME] 학습 시작 epochs=$EPOCHS $(date -u)" | tee -a $MASTER
  cd $MENT
  echo "===== $NAME fine-tune (E200 noside, ${EPOCHS}ep) $(date -u) =====" > $LOG
  python train_depth_vq_detector.py \
    --scene_manifest $DS/splits/train.json \
    --val_scene_manifest $DS/splits/val.json \
    --cad_memory $CAD \
    --init_checkpoint $INIT \
    --out_dir $OUT \
    --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr 3e-5 --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
  echo ">>> [$NAME] 학습 종료, eval(test 40장 전체) $(date -u)" | tee -a $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py \
    --checkpoint $OUT/best.pt \
    --depth_dir $DS/test_depth_symlinks \
    --glob "shot*.npy" \
    --label_dir $LABELS \
    --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 \
    --real_uint16_max_depth_m 10.0 --center_crop "1/6,5/6" \
    --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.30 --nms_iou_type mask \
    --bbox_source mask --diagnose_label_mismatch --save_predictions >> $LOG 2>&1
  echo ">>> [$NAME] eval 결과:" | tee -a $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
  # val best epoch 기록(과적합 판독용)
  python3 -c "import json;h=json.load(open('$OUT/history.json'));best=min(h,key=lambda e:e['val']['loss_total']);print('  best_val epoch=%d val_loss_total=%.3f (last ep val=%.3f)'%(best['epoch'],best['val']['loss_total'],h[-1]['val']['loss_total']))" 2>&1 | tee -a $MASTER
  echo "" | tee -a $MASTER
}

run_one "E200noside_ep50" 50
run_one "F200noside_ep30" 30

echo "===== EF 무인 완료 $(date -u) =====" | tee -a $MASTER
echo ">>> 최종 요약:" | tee -a $MASTER
grep -E "eval 결과|f1_micro|best_val|학습 시작" $MASTER | tee -a $MASTER
