#!/usr/bin/env bash
# 밤샘 무인 2차: lr 스윕 × init(csblur/csblurheavy) 요인분리. 200장 noside 동일 데이터.
# 병목=종류식별(61%). lr이 cad_ce/cad_align(종류) loss에 미치는 효과 + csblurheavy(class acc 최고) 출발점 검증.
# ⚠️ E/F(1차)가 끝난 뒤 이어서 실행 → GPU 경합 회피(지난주 동시 6판=ep2배 교훈).
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
MASTER=/workspace/cadence/runs/GHIJ_0707_master.log

# E/F 1차가 끝날 때까지 대기 (master 로그에 "EF 무인 완료" 뜰 때까지)
echo "===== GHIJ 대기: E/F 완료 기다림 $(date -u) =====" > $MASTER
while ! grep -q "EF 무인 완료" /workspace/cadence/runs/EF_0707_master.log 2>/dev/null; do
  sleep 60
done
echo "===== E/F 완료 확인, GHIJ 2차 시작 $(date -u) =====" | tee -a $MASTER

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
    --cad_memory $CAD \
    --init_checkpoint $INIT \
    --out_dir $OUT \
    --num_classes 27 --input_mode zv --image_size "320,576" --stage joint \
    --epochs $EPOCHS --batch_size 2 --num_workers 0 --lr $LR --weight_decay 1e-4 \
    --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
  echo ">>> [$NAME] eval(test 40장) $(date -u)" | tee -a $MASTER
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
  echo ">>> [$NAME] 결과:" | tee -a $MASTER
  grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
  python3 -c "import json;h=json.load(open('$OUT/history.json'));best=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last ep=%d loss=%.3f)'%(best['epoch'],best['val']['loss_total'],h[-1]['epoch'],h[-1]['val']['loss_total']))" 2>&1 | tee -a $MASTER
  echo "" | tee -a $MASTER
}

#         이름            init      lr     ep
run_one "G_csblur_lr1e4"   $CSBLUR  1e-4  50   # lr↑ 공격적
run_one "H_csblur_lr1e5"   $CSBLUR  1e-5  50   # lr↓ 보수적
run_one "I_heavy_lr3e5"    $CSHEAVY 3e-5  50   # init=csblurheavy (class acc 최고 출발점)
run_one "J_heavy_lr1e4"    $CSHEAVY 1e-4  50   # init heavy + lr↑ (최적조합 후보)


# ── K판: 고해상도 384x640 (6판과 lr·init·epoch 동일, 해상도만↑ → 대칭쌍 디테일 요인분리) ──
NAME=K_csblur_hires384; OUT=/workspace/cadence/runs/${NAME}_0707; LOG=/workspace/cadence/runs/${NAME}_0707.log; EVALOUT=/workspace/cadence/eval_${NAME}_0707_test40
echo ">>> [$NAME] init=csblur lr=3e-5 ep=50 imgsize=384,640 시작 $(date -u)" | tee -a $MASTER
cd $MENT
echo "===== $NAME (csblur 3e-5 50ep 384,640) $(date -u) =====" > $LOG
python train_depth_vq_detector.py --scene_manifest $DS/splits/train.json --val_scene_manifest $DS/splits/val.json --cad_memory $CAD --init_checkpoint $CSBLUR --out_dir $OUT --num_classes 27 --input_mode zv --image_size "384,640" --stage joint --epochs 50 --batch_size 2 --num_workers 0 --lr 3e-5 --weight_decay 1e-4 --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8 >> $LOG 2>&1
echo ">>> [$NAME] eval(test 40장) $(date -u)" | tee -a $MASTER
cd $MN
python eval_real_depth_vq_detector.py --checkpoint $OUT/best.pt --depth_dir $DS/test_depth_symlinks --glob "shot*.npy" --label_dir $LABELS --out_dir $EVALOUT --match_key cad_id --eval_mode mask --iou_thresh 0.25 --real_uint16_max_depth_m 10.0 --center_crop "1/6,5/6" --depth_keep_range "0.40,0.60" --score_thresh 0.50 --mask_thresh 0.5 --score_mode det --nms_iou_thresh 0.30 --nms_iou_type mask --bbox_source mask --diagnose_label_mismatch --save_predictions >> $LOG 2>&1
echo ">>> [$NAME] 결과:" | tee -a $MASTER
grep -oE "\"(f1_micro|precision_micro|recall_micro|mean_matched_iou_macro)\": [0-9.]*" $EVALOUT/eval_real_metrics.json 2>&1 | tee -a $MASTER
python3 -c "import json;h=json.load(open('$OUT/history.json'));best=min(h,key=lambda e:e['val']['loss_total']);print('  best_val ep=%d loss=%.3f (last ep=%d loss=%.3f)'%(best['epoch'],best['val']['loss_total'],h[-1]['epoch'],h[-1]['val']['loss_total']))" 2>&1 | tee -a $MASTER
echo "" | tee -a $MASTER

echo "===== GHIJ 2차 완료 $(date -u) =====" | tee -a $MASTER
echo ">>> 최종 요약(전체 판):" | tee -a $MASTER

# ── 대칭쌍 병합 후처리 채점 (학습 불필요, 6판 전부에 적용) ──
echo "" | tee -a $MASTER
echo "===== 대칭쌍 병합 후처리 채점 (6판) $(date -u) =====" | tee -a $MASTER
cd /workspace/cadence
python3 symmerge_score.py \
  eval_E200noside_ep50_0707_test40 \
  eval_F200noside_ep30_0707_test40 \
  eval_G_csblur_lr1e4_0707_test40 \
  eval_H_csblur_lr1e5_0707_test40 \
  eval_I_heavy_lr3e5_0707_test40 \
  eval_J_heavy_lr1e4_0707_test40 eval_K_csblur_hires384_0707_test40 2>&1 | tee -a $MASTER
echo "===== 전체 완료 (학습6판 + 대칭병합) $(date -u) =====" | tee -a $MASTER
