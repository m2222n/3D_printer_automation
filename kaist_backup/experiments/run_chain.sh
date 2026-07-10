#!/bin/bash
set -e
export PATH=/opt/conda/bin:$PATH
cd /workspace/cadence/Mentoring
ROOT=/workspace/cadence
DATA=$ROOT/data/2d_dataset
PC=$ROOT/data/pc_dataset
RUNS=$ROOT/runs

echo "[CHAIN] wait for 3D encoder to finish..."
while pgrep -f train_cad_encoder >/dev/null; do sleep 15; done
echo "[CHAIN] 3D encoder done. best.pt:"; ls -la $RUNS/cad_pointnet2/best.pt || { echo "NO best.pt"; exit 1; }

echo "[CHAIN] === STEP5 build CAD memory bank ==="
python build_cad_memory_bank.py \
  --manifest $PC/manifest.json \
  --checkpoint $RUNS/cad_pointnet2/best.pt \
  --output $RUNS/cad_pointnet2/cad_memory_bank.npz \
  --n_points 4096 --save_local
echo "[CHAIN] memory bank done"

echo "[CHAIN] === STEP6 detector warmup (det, 30ep, workers=0) ==="
python train_depth_vq_detector.py \
  --scene_manifest $DATA/splits/train.json \
  --val_scene_manifest $DATA/splits/val.json \
  --out_dir $RUNS/depth_detector_warmup_split \
  --num_classes 27 --input_mode zv --stage det \
  --epochs 30 --batch_size 4 --num_workers 0 \
  --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8
echo "[CHAIN] warmup done"; ls -la $RUNS/depth_detector_warmup_split/best.pt

echo "[CHAIN] === STEP7 VQ joint (100ep, workers=0) ==="
python train_depth_vq_detector.py \
  --scene_manifest $DATA/splits/train.json \
  --val_scene_manifest $DATA/splits/val.json \
  --cad_memory $RUNS/cad_pointnet2/cad_memory_bank.npz \
  --init_checkpoint $RUNS/depth_detector_warmup_split/best.pt \
  --out_dir $RUNS/depth_vq_detector_split \
  --num_classes 27 --input_mode zv --stage joint \
  --epochs 100 --batch_size 4 --num_workers 0 \
  --lr 1e-4 --weight_decay 1e-4 \
  --num_queries 100 --hidden_dim 256 --backbone_dim 64 --decoder_layers 6 --nheads 8
echo "[CHAIN] joint done"; ls -la $RUNS/depth_vq_detector_split/best.pt

echo "[CHAIN] === STEP8 eval on test ==="
python eval_depth_vq_detector.py \
  --checkpoint $RUNS/depth_vq_detector_split/best.pt \
  --scene_manifest $DATA/splits/test.json \
  --out_json $RUNS/depth_vq_detector_split/eval_test.json \
  --batch_size 4 --num_workers 0 --mask_thresh 0.5
echo "[CHAIN] === ALL DONE ==="
cat $RUNS/depth_vq_detector_split/eval_test.json
