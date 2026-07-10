#!/bin/bash
# 7/4 camsweep+정규화 재학습 = 39.6% baseline 위에 미팅 안건 ①값도메인통일 ②정규화 적용.
# 데이터: 2d_dataset_camsweep_norm01 (크기정합 camsweep 0.4~1.0m + 부품 per-scene 0-1 + 배경 NaN = 실측 eval과 동일 도메인).
#   camsweep(39.6%)은 raw meter(0.37~0.95)라 실측(0-1)과 값도메인 어긋나 있었음 → 통일.
# CAD memory bank 6/23 재사용 (STEP5 스킵). warmup30 → joint100 → 합성 test + 실측 100장 eval(F1).
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd /workspace/cadence/Mentoring
ROOT=/workspace/cadence
RUNS=$ROOT/runs
CADMEM=$RUNS/cad_pointnet2/cad_memory_bank.npz
REAL=$ROOT/data/real_capture100_eval
LOG=$RUNS/retrain_csblur_0704.log
MAX_RETRY=2
NAME=csblur
DATA=$ROOT/data/2d_dataset_camsweep_blur_light

echo "===== camsweep+edgeblur_light 재학습 시작 $(date) =====" | tee -a $LOG

run_stage () {
  local SNAME=$1 OUT=$2; shift 2
  if [ -f "$OUT/best.pt" ]; then echo "[$SNAME] best.pt 존재 → 스킵(resume)" | tee -a $LOG; return 0; fi
  local try=1
  while [ $try -le $MAX_RETRY ]; do
    echo "[$SNAME] 시도 $try/$MAX_RETRY $(date)" | tee -a $LOG
    python -u "$@" >> $LOG 2>&1
    if [ -f "$OUT/best.pt" ]; then echo "[$SNAME] 성공(시도 $try) $(date)" | tee -a $LOG; return 0; fi
    echo "[$SNAME] 시도 $try 실패, 재시도" | tee -a $LOG
    rm -rf "$OUT" 2>/dev/null; try=$((try+1))
  done
  echo "[$SNAME] 실패, 중단" | tee -a $LOG; return 1
}

WU=$RUNS/retrain_${NAME}_warmup
JO=$RUNS/retrain_${NAME}_joint
echo "----- [$NAME] 데이터=$DATA $(date) -----" | tee -a $LOG

if [ ! -f "$DATA/splits/train.json" ]; then
   python -u tools/make_scene_splits.py --data_root "$DATA" --out_dir "$DATA/splits" --overwrite >> $LOG 2>&1; fi

run_stage "${NAME}:warmup" "$WU" \
  train_depth_vq_detector.py \
  --scene_manifest $DATA/splits/train.json --val_scene_manifest $DATA/splits/val.json \
  --out_dir $WU --num_classes 27 --input_mode zv --stage det \
  --epochs 30 --batch_size 4 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 \
  || exit 1

run_stage "${NAME}:joint" "$JO" \
  train_depth_vq_detector.py \
  --scene_manifest $DATA/splits/train.json --val_scene_manifest $DATA/splits/val.json \
  --cad_memory $CADMEM --init_checkpoint $WU/best.pt \
  --out_dir $JO --num_classes 27 --input_mode zv --stage joint \
  --epochs 100 --batch_size 4 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 \
  || exit 1

python -u eval_depth_vq_detector.py --checkpoint $JO/best.pt \
  --scene_manifest $DATA/splits/test.json --out_json $JO/eval_synth_test.json \
  --batch_size 4 --num_workers 0 --mask_thresh 0.5 --score_thresh 0.5 --iou_thresh 0.5 >> $LOG 2>&1
echo "[$NAME] 합성 test: $(grep -oE '"(f1_score|matched_class_acc)": [0-9.]*' $JO/eval_synth_test.json | tr '\n' ' ')" | tee -a $LOG

python -u eval_depth_vq_detector.py --checkpoint $JO/best.pt \
  --data_root $REAL --out_json $JO/eval_real100.json \
  --batch_size 4 --num_workers 0 --mask_thresh 0.5 --score_thresh 0.5 --iou_thresh 0.5 >> $LOG 2>&1
echo "[$NAME] 실측 eval: $(grep -oE '"(f1_score|precision|recall|matched_class_acc|matched_cad_acc|matched_mask_iou)": [0-9.]*' $JO/eval_real100.json | tr '\n' ' ')" | tee -a $LOG

echo "===== camsweep+edgeblur_light 재학습 종료 $(date) =====" | tee -a $LOG
