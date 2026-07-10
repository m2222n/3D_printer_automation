#!/bin/bash
# test100 재학습 3판 (조교 4:1:5 = train80/val18/test102). 전부 csblur best.pt → real fine-tune.
# 변수 하나씩: lr/epoch. test40의 결론(csblur lr1e-4 80ep=0.818) 재현 + test100 조건 확인.
export PATH=/opt/conda/bin:$PATH
MN=/workspace/cadence/mentoring_new
MENT=/workspace/cadence/Mentoring
DS=$MN/data/real_labelme_dataset_E200_noside
CAD=/workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz
LABELS=$MN/data/real_labels
CSBLUR=/workspace/cadence/runs/retrain_csblur_joint/best.pt
MASTER=/workspace/cadence/runs/T100_0707_master.log
echo "===== test100 재학습 시작 $(date -u) =====" > $MASTER

run_one () {
  NAME=$1; LR=$2; EPOCHS=$3
  OUT=/workspace/cadence/runs/${NAME}
  LOG=/workspace/cadence/runs/${NAME}.log
  EVALOUT=/workspace/cadence/eval_${NAME}_test102
  echo ">>> [$NAME] lr=$LR ep=$EPOCHS 시작 $(date -u)" >> $MASTER
  cd $MENT
  python train_depth_vq_detector.py \
    --scene_manifest $DS/splits/train_t100.json \
    --val_scene_manifest $DS/splits/val_t100.json \
    --cad_memory $CAD --init_checkpoint $CSBLUR --out_dir $OUT \
    --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr $LR --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 > $LOG 2>&1
  echo ">>> [$NAME] eval(test 102장) $(date -u)" >> $MASTER
  cd $MN
  python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt \
    --depth_dir $DS/test_depth_symlinks_t100 --glob "shot*.npy" --label_dir $LABELS --out_dir $EVALOUT \
    --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 \
    --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.45 --mask_thresh 0.5 \
    --score_mode det --nms_iou_thresh 0.50 --nms_iou_type mask --bbox_source mask \
    --save_predictions >> $LOG 2>&1
  echo ">>> [$NAME] 결과:" >> $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json >> $MASTER 2>&1
  python3 -c "import json;h=json.load(open('$OUT/history.json'));b=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last=%d loss=%.3f)'%(b['epoch'],b['val']['loss_total'],h[-1]['epoch'],h[-1]['val']['loss_total']))" >> $MASTER 2>&1
}

run_one "T100_csblur_lr1e4_ep80" 1e-4 80   # L 재현 = 메인 후보
run_one "T100_csblur_lr1e4_ep50" 1e-4 50   # G 재현
run_one "T100_csblur_lr3e5_ep50" 3e-5 50   # 저lr 대조
echo "===== test100 재학습 완료 $(date -u) =====" >> $MASTER
