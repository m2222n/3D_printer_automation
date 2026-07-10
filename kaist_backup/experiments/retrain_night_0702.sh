#!/bin/bash
# 7/2 밤 무인 재학습 — 도메인 갭 대응 실험 2종 (순차) + 자동 재시도 + 간이 resume
# 진단 결과: 진범 = depth 노이즈/도메인 갭 (크기 아님) → noise 버전이 본命.
# CAD memory bank/3D encoder는 6/23 산물 재사용 (STEP5 스킵).
# 각 실험: warmup(det 30ep) → joint(VQ 100ep) → 합성 test + 실측 100장 eval.
# ⭐ 개선: python -u(실시간 로그) + 각 단계 최대 2회 재시도 + best.pt 있으면 스킵(resume).
set -u
export PATH=/opt/conda/bin:$PATH
export CUDA_VISIBLE_DEVICES=0
export PYTHONUNBUFFERED=1
cd /workspace/cadence/Mentoring
ROOT=/workspace/cadence
RUNS=$ROOT/runs
CADMEM=$RUNS/cad_pointnet2/cad_memory_bank.npz
REAL=$ROOT/data/real_capture100_eval
LOG=$RUNS/retrain_night_0702.log
MAX_RETRY=2

echo "===== 재학습 시작 $(date) =====" | tee -a $LOG

# 단계 실행 + 재시도. best.pt 있으면 스킵(resume). 성공(0)/실패(1) 반환.
run_stage () {
  local NAME=$1 OUT=$2; shift 2
  if [ -f "$OUT/best.pt" ]; then echo "[$NAME] best.pt 이미 존재 → 스킵(resume)" | tee -a $LOG; return 0; fi
  local try=1
  while [ $try -le $MAX_RETRY ]; do
    echo "[$NAME] 시도 $try/$MAX_RETRY 시작 $(date)" | tee -a $LOG
    python -u "$@" >> $LOG 2>&1
    if [ -f "$OUT/best.pt" ]; then echo "[$NAME] ✅ 성공(시도 $try) $(date)" | tee -a $LOG; return 0; fi
    echo "[$NAME] ⚠️ 시도 $try 실패(best.pt 없음), 재시도" | tee -a $LOG
    rm -rf "$OUT" 2>/dev/null   # 부분 산출물 제거 후 재시도
    try=$((try+1))
  done
  echo "[$NAME] ❌ $MAX_RETRY회 모두 실패, 중단" | tee -a $LOG; return 1
}

run_one () {
  local NAME=$1 DATA=$2
  local WU=$RUNS/retrain_${NAME}_warmup
  local JO=$RUNS/retrain_${NAME}_joint
  echo "----- [$NAME] 데이터=$DATA $(date) -----" | tee -a $LOG

  if [ ! -f "$DATA/splits/train.json" ]; then
     python -u tools/make_scene_splits.py --data_root "$DATA" --out_dir "$DATA/splits" --overwrite >> $LOG 2>&1; fi

  # STEP6 warmup (det)
  run_stage "${NAME}:warmup" "$WU" \
    train_depth_vq_detector.py \
    --scene_manifest $DATA/splits/train.json --val_scene_manifest $DATA/splits/val.json \
    --out_dir $WU --num_classes 27 --input_mode zv --stage det \
    --epochs 30 --batch_size 4 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 \
    || return 1

  # STEP7 joint (VQ)
  run_stage "${NAME}:joint" "$JO" \
    train_depth_vq_detector.py \
    --scene_manifest $DATA/splits/train.json --val_scene_manifest $DATA/splits/val.json \
    --cad_memory $CADMEM --init_checkpoint $WU/best.pt \
    --out_dir $JO --num_classes 27 --input_mode zv --stage joint \
    --epochs 100 --batch_size 4 --num_workers 0 --lr 1e-4 --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 \
    || return 1

  # STEP8-a 합성 test eval
  python -u eval_depth_vq_detector.py --checkpoint $JO/best.pt \
    --scene_manifest $DATA/splits/test.json --out_json $JO/eval_synth_test.json \
    --batch_size 4 --num_workers 0 --mask_thresh 0.5 >> $LOG 2>&1
  echo "[$NAME] 합성 test: $(grep -o '\"matched_class_acc\": [0-9.]*' $JO/eval_synth_test.json)" | tee -a $LOG

  # STEP8-b ⭐ 실측 100장 eval
  python -u eval_depth_vq_detector.py --checkpoint $JO/best.pt \
    --data_root $REAL --out_json $JO/eval_real100.json \
    --batch_size 4 --num_workers 0 --mask_thresh 0.5 >> $LOG 2>&1
  echo "[$NAME] ⭐실측 eval: $(grep -oE '\"(matched_class_acc|matched_cad_acc|hungarian_recall|matched_mask_iou)\": [0-9.]*' $JO/eval_real100.json | tr '\n' ' ')" | tee -a $LOG
  echo "[$NAME] ===== 완료 $(date) =====" | tee -a $LOG
}

# 본命 먼저: noisy(진범=노이즈). 그 다음 camsweep(스케일 대조군). 하나 실패해도 다음은 진행.
run_one noisy    $ROOT/data/2d_dataset_camsweep_noisy || echo "[noisy] 실패했으나 camsweep 계속" | tee -a $LOG
run_one camsweep $ROOT/data/2d_dataset_camsweep      || echo "[camsweep] 실패" | tee -a $LOG

echo "===== 전체 재학습 종료 $(date) =====" | tee -a $LOG
echo "=== 결과 요약 ===" | tee -a $LOG
grep "⭐실측 eval" $LOG | tee -a $LOG
