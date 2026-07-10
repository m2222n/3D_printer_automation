#!/bin/bash
# GPU 여유 생기면 이거 한 줄로 재시작:
#   setsid bash /workspace/cadence/run_chain_local.sh > /workspace/cadence/runs/chain2.log 2>&1 &
# 모델/하이퍼파라미터 = 조교 방침 그대로. 데이터만 A100 로컬(/root/cadence_local)로 변경(I/O 가속).
set -e
export PATH=/opt/conda/bin:$PATH
cd /workspace/cadence/Mentoring
RUNS=/workspace/cadence/runs
PC=/workspace/cadence/data/pc_dataset
LOCAL=/root/cadence_local/2d_dataset

echo "[CHAIN2] start $(date)"
# 3D encoder + memory bank는 이미 완료됨 → 있으면 건너뜀
if [ ! -f $RUNS/cad_pointnet2/cad_memory_bank.npz ]; then
  echo "[CHAIN2] (재)build memory bank"
  python build_cad_memory_bank.py --manifest $PC/manifest.json \
    --checkpoint $RUNS/cad_pointnet2/best.pt \
    --output $RUNS/cad_pointnet2/cad_memory_bank.npz --n_points 4096 --save_local
fi
echo "[CHAIN2] memory bank ready"

echo "[CHAIN2] === warmup (det 30ep) $(date) ==="
python train_depth_vq_detector.py \
  --scene_manifest $LOCAL/splits/train.json \
  --val_scene_manifest $LOCAL/splits/val.json \
  --out_dir $RUNS/depth_detector_warmup_split \
  --num_classes 27 --input_mode zv --stage det --device cuda \
  --epochs 30 --batch_size 4 --num_workers 0 \
  --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8
echo "[CHAIN2] warmup done $(date)"

echo "[CHAIN2] === joint (100ep) $(date) ==="
python train_depth_vq_detector.py \
  --scene_manifest $LOCAL/splits/train.json \
  --val_scene_manifest $LOCAL/splits/val.json \
  --cad_memory $RUNS/cad_pointnet2/cad_memory_bank.npz \
  --init_checkpoint $RUNS/depth_detector_warmup_split/best.pt \
  --out_dir $RUNS/depth_vq_detector_split \
  --num_classes 27 --input_mode zv --stage joint --device cuda \
  --epochs 100 --batch_size 4 --num_workers 0 \
  --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8
echo "[CHAIN2] joint done $(date)"

echo "[CHAIN2] === eval $(date) ==="
python eval_depth_vq_detector.py \
  --checkpoint $RUNS/depth_vq_detector_split/best.pt \
  --scene_manifest $LOCAL/splits/test.json \
  --out_json $RUNS/depth_vq_detector_split/eval_test.json \
  --batch_size 4 --num_workers 0 --mask_thresh 0.5
echo "[CHAIN2] === ALL DONE $(date) ==="
cat $RUNS/depth_vq_detector_split/eval_test.json
