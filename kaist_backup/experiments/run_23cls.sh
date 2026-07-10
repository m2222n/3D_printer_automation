#!/bin/bash
# 23클래스 대칭쌍 병합 학습 — 병목(대칭쌍 종류혼동) 직격.
# lr 4판(T100night) 완료를 기다린 후 시작(GPU 경합 방지). 전부 test102(23cls) 평가.
export PATH=/opt/conda/bin:$PATH
MN=/workspace/cadence/mentoring_new
MENT=/workspace/cadence/Mentoring
DS=$MN/data/real_labelme_dataset_23cls
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank_23cls.npz
LABELS=$MN/data/real_labels
CSBLUR=/workspace/cadence/runs/retrain_csblur_joint/best.pt
CSHEAVY=/workspace/cadence/runs/retrain_csblurheavy_joint/best.pt
MASTER=/workspace/cadence/runs/T23cls_master.log

# --- 즉시 시작 (lr 4판 중단, 23클래스 우선) ---
echo "===== 23클래스 학습 시작 $(date -u) =====" > $MASTER

# --- test102(23cls) depth symlink 생성 (원본 depth 공유, 라벨은 23cls memory로 채점) ---
# eval은 depth_dir/glob + label_dir 사용. depth는 원본과 동일하므로 E200 symlink 재사용 가능.
DEPTHDIR=$MN/data/real_labelme_dataset_E200_noside/test_depth_symlinks_t100

run_one () {
  NAME=$1; INIT=$2; LR=$3; EPOCHS=$4
  OUT=/workspace/cadence/runs/${NAME}
  LOG=/workspace/cadence/runs/${NAME}.log
  EVALOUT=/workspace/cadence/eval_${NAME}_test102
  echo ">>> [$NAME] init=$(basename $(dirname $INIT)) lr=$LR ep=$EPOCHS 시작 $(date -u)" >> $MASTER
  cd $MENT
  python train_depth_vq_detector.py \
    --scene_manifest $DS/splits/train_t100.json \
    --val_scene_manifest $DS/splits/val_t100.json \
    --cad_memory $CAD --init_checkpoint $INIT --out_dir $OUT \
    --num_classes 23 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr $LR --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 > $LOG 2>&1
  echo ">>> [$NAME] eval(test 102장, 23cls) $(date -u)" >> $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DEPTHDIR --glob "shot*.npy" --label_dir $LABELS --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.50 --nms_iou_type mask --bbox_source mask \
    --cad_memory $CAD --save_predictions >> $LOG 2>&1
  echo ">>> [$NAME] 결과:" >> $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json >> $MASTER 2>&1
  python3 -c "import json;h=json.load(open('$OUT/history.json'));b=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last=%d loss=%.3f)'%(b['epoch'],b['val']['loss_total'],h[-1]['epoch'],h[-1]['val']['loss_total']))" >> $MASTER 2>&1
}

# 23클래스 lr 서칭 (27클래스서 lr1e-4가 최적이었음, 그 주변 + heavy)
run_one "T23_csblur_lr1e4_ep80"   $CSBLUR  1e-4  80
run_one "T23_csblur_lr1.5e4_ep80" $CSBLUR  1.5e-4 80
run_one "T23_heavy_lr1e4_ep80"    $CSHEAVY 1e-4  80

echo "===== 23클래스 학습 전체 완료 $(date -u) =====" >> $MASTER
