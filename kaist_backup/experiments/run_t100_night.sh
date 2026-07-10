#!/bin/bash
# test100(4:1:5) 밤샘 하이퍼파라미터 서칭 — 0.684 → 0.75 목표.
# 전부 real train80 fine-tune, eval=test102, score0.50/nms0.50, --diagnose(대칭병합 채점용).
export PATH=/opt/conda/bin:$PATH
MN=/workspace/cadence/mentoring_new
MENT=/workspace/cadence/Mentoring
DS=$MN/data/real_labelme_dataset_E200_noside
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz
LABELS=$MN/data/real_labels
CSBLUR=/workspace/cadence/runs/retrain_csblur_joint/best.pt
CSHEAVY=/workspace/cadence/runs/retrain_csblurheavy_joint/best.pt
MASTER=/workspace/cadence/runs/T100night_master.log
echo "===== test100 밤샘 서칭 시작 $(date -u) =====" > $MASTER

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
    --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr $LR --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 > $LOG 2>&1
  echo ">>> [$NAME] eval(test 102장) $(date -u)" >> $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DS/test_depth_symlinks_t100 --glob "shot*.npy" --label_dir $LABELS --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.50 --nms_iou_type mask --bbox_source mask \
    --diagnose_label_mismatch --save_predictions >> $LOG 2>&1
  echo ">>> [$NAME] 결과:" >> $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json >> $MASTER 2>&1
  python3 -c "import json;h=json.load(open('$OUT/history.json'));b=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last=%d loss=%.3f)'%(b['epoch'],b['val']['loss_total'],h[-1]['epoch'],h[-1]['val']['loss_total']))" >> $MASTER 2>&1
}

# train80은 금방 과적합(best_val ep~50) → epoch보다 lr 다양화가 핵심. 80ep 고정, lr 위주 4판.
# Track A: csblur lr 서칭 (train80 제약 내 최선)
run_one "T100n_csblur_lr1.5e4_ep80" $CSBLUR 1.5e-4 80   # lr 미세 상향 (0.684서 더?)
run_one "T100n_csblur_lr7e5_ep80"   $CSBLUR 7e-5   80    # 1e-4와 3e-5 사이
# Track C: heavy init (test40서 lr 높을때만 쓸만=class acc 강점)
run_one "T100n_heavy_lr1e4_ep80"    $CSHEAVY 1e-4  80    # heavy·lr1e-4
run_one "T100n_heavy_lr1.5e4_ep80"  $CSHEAVY 1.5e-4 80   # heavy·lr↑

echo "===== 밤샘 서칭 완료 $(date -u) =====" >> $MASTER
# 대칭병합 자동 채점 (diagnose 켜서 per_scene CSV에 spatial_pairs 포함)
cd /workspace/cadence
python3 symmerge_score.py \
  eval_T100n_csblur_lr1.5e4_ep80_test102 \
  eval_T100n_csblur_lr7e5_ep80_test102 \
  eval_T100n_heavy_lr1e4_ep80_test102 \
  eval_T100n_heavy_lr1.5e4_ep80_test102 \
  eval_T100_csblur_lr1e4_ep80_test102 >> $MASTER 2>&1
echo "===== 전체 완료 $(date -u) =====" >> $MASTER
