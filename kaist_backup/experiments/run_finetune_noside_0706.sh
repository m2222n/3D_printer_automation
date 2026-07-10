#!/usr/bin/env bash
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd /workspace/cadence/Mentoring
MN=/workspace/cadence/mentoring_new
C=$MN/data/real_labelme_dataset_Cnew100_noside
OUT=/workspace/cadence/runs/Cnew100_noside_finetune_0706
LOG=/workspace/cadence/runs/Cnew100_noside_finetune_0706.log
echo "===== 조교방식 fine-tune (신규100 side제거X) 시작 $(date) =====" > $LOG
python train_depth_vq_detector.py \
  --scene_manifest $C/splits/train.json \
  --val_scene_manifest $C/splits/val.json \
  --cad_memory /workspace/cadence/runs/cad_pointnet2/cad_memory_bank.npz \
  --init_checkpoint /workspace/cadence/runs/retrain_csblur_joint/best.pt \
  --out_dir $OUT \
  --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
  --epochs 80 --batch_size 2 --num_workers 0 --lr 3e-5 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
echo "===== 학습 종료, test 20장 평가 $(date) =====" >> $LOG
cd $MN
REAL_ROOT=$C LABEL_DIR=./data/real_labels \
CKPT=$OUT/best.pt \
OUT_DIR=/workspace/cadence/eval_Cnew100_noside_test \
SCORE_THRESH=0.50 NMS_THRESH=0.30 IOU_THRESH=0.25 \
  bash ./scripts/eval_C_real_test.sh >> $LOG 2>&1
echo "===== 평가 종료 $(date) =====" >> $LOG
echo ">>> 결과:" >> $LOG
grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" /workspace/cadence/eval_Cnew100_noside_test/eval_real_metrics.json >> $LOG 2>&1
