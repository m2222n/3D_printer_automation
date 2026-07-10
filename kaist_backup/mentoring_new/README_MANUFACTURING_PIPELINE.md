# Manufacturing 코드 실행 README

이 문서는 현재 `manufacturing` 프로젝트를 다른 사람에게 공유할 때 바로 따라 실행할 수 있도록 정리한 실행 순서입니다.  
프로젝트 목표는 **CAD/STL 기반 pseudo depth dataset + real depth dataset을 이용해 depth-only multi-object detection / CAD decision 모델을 학습·평가**하는 것입니다.

> 참고: 일부 폴더명과 config 경로는 기존 코드 호환을 위해 그대로 둡니다. README의 프로젝트 명칭은 `manufacturing`으로 통일했습니다.

---

## 0. 기본 경로와 데이터 구조

예상 프로젝트 루트:

```bash
cd /data4/haksoo/mentoring_new
```

주요 입력 데이터:

```text
data/
 ├─ stl_dataset/                    # 27개 STL CAD 파일
 ├─ 2d_dataset/                      # 기존 synthetic pseudo dataset
 │   ├─ npz/                         # scene_NNNNN.npz
 │   ├─ crops/                       # sceneNNNNN_instII_catCC.npz
 │   └─ vis/                         # 확인용 PNG, 학습에는 사용하지 않음
 ├─ real_depth/
 │   └─ npy/                         # shot_*.npy 실증 depth
 ├─ real_labels/                     # LabelMe JSON labels
 └─ domain_profile/          # real profile / B dataset request
```

기존 synthetic scene npz 포맷:

```text
scene_NNNNN.npz
 ├─ depth        : (H,W) float32, meter 단위, 배경 NaN
 ├─ inst_id      : (H,W) int32, instance id, 배경 0
 ├─ category_id  : (H,W) int32, category id, 배경 0
 └─ meta         : JSON string
```

crop npz 포맷:

```text
sceneNNNNN_instII_catCC.npz
 ├─ depth          : crop depth, 배경 NaN
 ├─ mask           : bool visible mask
 ├─ label          : int32 category id
 ├─ quat_wxyz      : pose quaternion
 ├─ euler_zyx_deg  : pose Euler angle
 ├─ bbox_yxyx      : scene-level bbox
 └─ stl            : STL filename, CAD matching용
```

`vis/*.png`는 사람이 보기 위한 overlay 이미지입니다. 실제 학습 입력은 `npz` 안의 `depth`입니다.

---

## 1. 환경 준비

```bash
conda activate deco_diff
pip install numpy scipy pillow matplotlib tqdm trimesh torch torchvision
```

`BlenderProc` generator는 현재 권장하지 않습니다. BlenderProc 경로에서는 camera pose, segmentation, duplicate output registry 문제가 반복되었으므로, 현재는 검증된 **fast point-splat CAD renderer**를 사용합니다.

---

## 2. STL → CAD point cloud dataset 생성

STL 파일에서 3D encoder용 point cloud를 만듭니다.

```bash
python stl_to_pointcloud_dataset.py \
  --input_dir ./data/stl_dataset \
  --output_dir ./data/cad_pointcloud_dataset \
  --n_points 8192 \
  --edge_ratio 0.2 \
  --sharp_angle_deg 35 \
  --recursive \
  --export_ply
```

출력:

```text
data/cad_pointcloud_dataset/
 ├─ manifest.json
 ├─ <cad_id>.npz
 ├─ <cad_id>.json
 └─ optional <cad_id>.ply
```

---

## 3. 3D CAD encoder 학습 및 CAD memory bank 생성

### 3.1 3D encoder 학습

```bash
cd /data4/haksoo/mentoring_new/cad3d_encoder_code

python train_cad_encoder.py \
  --manifest ../data/cad_pointcloud_dataset/manifest.json \
  --out_dir ../runs/cad_pointnet2 \
  --epochs 100 \
  --batch_size 16 \
  --n_points 4096 \
  --rotation_aug none
```

### 3.2 CAD memory bank 생성

```bash
python build_cad_memory_bank.py \
  --manifest ../data/cad_pointcloud_dataset/manifest.json \
  --checkpoint ../runs/cad_pointnet2/best.pt \
  --output ../runs/cad_pointnet2/cad_memory_bank.npz \
  --n_points 4096 \
  --save_local
```

생성된 파일:

```text
runs/cad_pointnet2/cad_memory_bank.npz
 ├─ cad_ids
 ├─ class_names
 ├─ embeddings
 ├─ local_xyz
 └─ local_tokens
```

다시 프로젝트 루트로 이동합니다.

```bash
cd /data4/haksoo/mentoring_new
```

---

## 4. synthetic dataset split 생성

기존 synthetic dataset을 train/val/test로 나눕니다.

```bash
python tools/make_scene_splits.py \
  --data_root ./data/2d_dataset \
  --out_dir ./data/2d_dataset/splits \
  --train_ratio 0.8 \
  --val_ratio 0.1 \
  --test_ratio 0.1 \
  --seed 42 \
  --stratify_bg_kind \
  --overwrite
```

출력:

```text
data/2d_dataset/splits/
 ├─ train.json
 ├─ val.json
 ├─ test.json
 └─ split_summary.json
```

---

## 5. synthetic baseline / A sensorized 학습

### 5.1 detector warmup

CAD VQ를 붙이기 전에 depth → bbox/mask/class detector를 먼저 안정화합니다.

```bash
python train_depth_vq_detector.py \
  --scene_manifest ./data/2d_dataset/splits/train.json \
  --val_scene_manifest ./data/2d_dataset/splits/val.json \
  --out_dir ./runs/depth_detector_warmup_split \
  --num_classes 27 \
  --input_mode zv \
  --stage det \
  --epochs 30 \
  --batch_size 4 \
  --num_workers 4 \
  --lr 1e-4 \
  --weight_decay 1e-4 \
  --num_queries 100 \
  --hidden_dim 256 \
  --backbone_dim 64 \
  --decoder_layers 6 \
  --nheads 8
```

### 5.2 A: pseudo sensorized augmentation 학습

기존 synthetic dataset에 real-like sensor corruption을 적용해 학습합니다.

```bash
python train_depth_vq_detector.py \
  --scene_manifest ./data/2d_dataset/splits/train.json \
  --val_scene_manifest ./data/2d_dataset/splits/val.json \
  --cad_memory ./runs/cad_pointnet2/cad_memory_bank.npz \
  --init_checkpoint ./runs/depth_detector_warmup_split/best.pt \
  --out_dir ./runs/depth_vq_detector_A_sensorized \
  --num_classes 27 \
  --input_mode zv \
  --image_size "320,576" \
  --stage joint \
  --epochs 100 \
  --batch_size 4 \
  --num_workers 4 \
  --lr 1e-4 \
  --weight_decay 1e-4 \
  --num_queries 100 \
  --hidden_dim 256 \
  --backbone_dim 64 \
  --decoder_layers 6 \
  --nheads 8 \
  --train_depth_median_range "0.45,0.55" \
  --randomize_train_depth_median \
  --train_robust_depth_median_range "0.35,0.60" \
  --train_robust_prob 0.25 \
  --train_avg_pool_kernel 3 \
  --avg_pool_valid_threshold 0.05 \
  --pseudo_uint16_max_depth_m 10.0 \
  --train_noise_sigma_m 0.0015 \
  --train_noise_rel_sigma 0.002 \
  --train_random_dropout_prob 0.02 \
  --train_boundary_dropout_prob 0.35 \
  --train_boundary_radius 2 \
  --train_hole_prob 2.0 \
  --train_valid_ratio_range "0.04,0.08"
```

---

## 6. B-fast dataset 생성

BlenderProc 대신 검증된 fast point-splat renderer를 사용합니다.  
STL point cloud를 직접 projection해서 `depth / inst_id / category_id / crops / vis / splits`를 생성합니다.

### 6.1 no occlusion + soft pixel dropout 버전

지역 occlusion은 적용하지 않고, 실제 depth처럼 sparse missing pixel만 넣습니다.

```bash
PARTIAL_OBJECT_PROB=0.0 \
TRUNCATION_OBJECT_PROB=0.0 \
SOFT_PIXEL_DROPOUT_RATE=0.04 \
STL_DIR=./data/stl_dataset \
REF_DATASET=./data/2d_dataset \
OUT_ROOT=./data/2d_dataset_B_fast_no_occ \
REQUEST_JSON=./data/domain_profile/pseudo_regen_request.json \
NUM_SCENES=1000 \
POINTS_PER_ASSET=15000 \
SPLAT_RADIUS=1 \
bash ./scripts/render_B_dataset_fast.sh
```

### 6.2 target90 partial 버전

필요 시 partial observation을 약하게 넣습니다. 최종 visible ratio가 대부분 0.85~0.95, 중심 0.90 근처가 되도록 합니다.

```bash
PARTIAL_OBJECT_PROB=1.0 \
TRUNCATION_OBJECT_PROB=0.50 \
SOFT_PIXEL_DROPOUT_RATE=0.04 \
PARTIAL_TARGET_VISIBLE_MIN=0.85 \
PARTIAL_TARGET_VISIBLE_MAX=0.95 \
PARTIAL_TARGET_VISIBLE_MEAN=0.90 \
STL_DIR=./data/stl_dataset \
REF_DATASET=./data/2d_dataset \
OUT_ROOT=./data/2d_dataset_B_fast_target90 \
REQUEST_JSON=./data/domain_profile/pseudo_regen_request.json \
NUM_SCENES=1000 \
POINTS_PER_ASSET=15000 \
SPLAT_RADIUS=1 \
bash ./scripts/render_B_dataset_fast.sh
```

생성 후 확인:

```bash
cat ./data/2d_dataset_B_fast_target90/profile_check/B_dataset_profile_summary.json
cat ./data/2d_dataset_B_fast_target90/profile_check/B_dataset_visible_ratio_stats.json
ls -lh ./data/2d_dataset_B_fast_target90/profile_check/B_dataset_preview_2x2.png
```

---

## 7. AB 학습

B-fast dataset + A sensorized augmentation으로 학습합니다.

### 7.1 no-occlusion B-fast 학습

```bash
DATA_ROOT=./data/2d_dataset_B_fast_no_occ \
OUT_DIR=./runs/depth_vq_detector_AB_fast_no_occ_sensorized \
CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
INIT_CKPT=./runs/depth_detector_warmup_split/best.pt \
EPOCHS=100 \
BATCH_SIZE=4 \
bash ./scripts/train_AB_blenderproc_sensorized.sh
```

### 7.2 target90 B-fast 학습

```bash
DATA_ROOT=./data/2d_dataset_B_fast_target90 \
OUT_DIR=./runs/depth_vq_detector_AB_fast_target90_sensorized \
CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
INIT_CKPT=./runs/depth_detector_warmup_split/best.pt \
EPOCHS=100 \
BATCH_SIZE=4 \
bash ./scripts/train_AB_blenderproc_sensorized.sh
```

---

## 8. Real LabelMe dataset C 생성

Real supervised fine-tuning용 dataset을 만듭니다.  
LabelMe polygon을 이용해 side/background depth를 제거하는 foreground-cleaning을 적용합니다.

### 8.1 real depth와 label 매칭 개수 확인

```bash
python - <<'PY'
from pathlib import Path

depth_dir = Path("./data/real_depth/npy")
label_dir = Path("./data/real_labels")

depths = {p.stem for p in depth_dir.glob("shot_*.npy")}
labels = {p.stem for p in label_dir.glob("*.json")}
matched = sorted(depths & labels)

print("depth files:", len(depths))
print("label files:", len(labels))
print("matched    :", len(matched))
PY
```

### 8.2 train 30 / val 20 / test 50 split으로 C dataset 생성

```bash
DEPTH_DIR=./data/real_depth/npy \
LABEL_DIR=./data/real_labels \
OUT_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
REF_DATASET=./data/2d_dataset \
GLOB="shot_*.npy" \
CENTER_CROP="1/6,5/6" \
DEPTH_KEEP_RANGE="0.40,0.60" \
REAL_UINT16_MAX_DEPTH_M=10.0 \
FOREGROUND_DEPTH_MODE=dilated_label \
FOREGROUND_DILATE_PX=8 \
TRAIN_COUNT=30 \
VAL_COUNT=20 \
SEED=42 \
bash ./scripts/build_C_real_labelme_dataset.sh
```

split 확인:

```bash
python - <<'PY'
import json
root = "./data/real_labelme_dataset_C_fgclean_30_20_50/splits"
for split in ["train", "val", "test", "all"]:
    d = json.load(open(f"{root}/{split}.json"))
    print(split, len(d["scenes"]))
PY
```

정상 기대값:

```text
train 30
val 20
test 50
all 100
```

---

## 9. C real fine-tuning

AB checkpoint에서 real LabelMe train split으로 fine-tuning합니다.

```bash
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
INIT_CKPT=./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt \
CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
OUT_DIR=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50 \
EPOCHS=120 \
BATCH_SIZE=2 \
LR=3e-5 \
IMAGE_SIZE="320,576" \
bash ./scripts/train_C_real_finetune.sh
```

학습이 불안정하면 learning rate를 낮춰 재시도합니다.

```bash
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
INIT_CKPT=./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt \
CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz \
OUT_DIR=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50_lr1e5 \
EPOCHS=120 \
BATCH_SIZE=2 \
LR=1e-5 \
IMAGE_SIZE="320,576" \
bash ./scripts/train_C_real_finetune.sh
```

---

## 10. Real evaluation

### 10.1 held-out test 50장 평가

```bash
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
LABEL_DIR=./data/real_labels \
CKPT=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt \
OUT_DIR=./eval_real_C_fgclean_30_20_50_test_s050_nms030_iou025 \
SCORE_THRESH=0.50 \
NMS_THRESH=0.30 \
IOU_THRESH=0.25 \
bash ./scripts/eval_C_real_test.sh
```

출력:

```text
eval_real_C_fgclean_30_20_50_test_s050_nms030_iou025/
 ├─ eval_real_metrics.json
 ├─ eval_real_per_scene.csv
 ├─ all_predictions.json
 └─ predictions/
```

### 10.2 전체 100장 sanity check

전체 100장은 train/val/test가 섞이므로 정식 generalization 수치로 쓰면 안 됩니다. fine-tuning이 제대로 먹었는지 확인하는 용도입니다.

```bash
LABEL_DIR=./data/real_labels \
DEPTH_DIR=./data/real_depth/npy \
CKPT=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt \
OUT_DIR=./eval_real_C_fgclean_30_20_50_all_s050_nms030_iou025 \
SCORE_THRESH=0.50 \
NMS_THRESH=0.30 \
IOU_THRESH=0.25 \
bash ./scripts/eval_C_real_all.sh
```

---

## 11. 단일 real shot inference + visualization

```bash
python infer_depth_vq_detector.py \
  --checkpoint ./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt \
  --depth ./data/real_depth/npy/shot_001_g1.npy \
  --label_dir ./data/real_labels \
  --out_dir ./pred_shot_001_crop \
  --real_uint16_max_depth_m 10.0 \
  --center_crop "1/6,5/6" \
  --depth_keep_range "0.40,0.60" \
  --score_thresh 0.50 \
  --mask_thresh 0.5 \
  --score_mode det \
  --nms_iou_thresh 0.30 \
  --nms_iou_type mask \
  --bbox_source mask \
  --visualize \
  --include_gt_visualization \
  --debug_scores
```

출력:

```text
pred_shot_001_crop/
 ├─ predictions.json
 ├─ predicted_masks.npz
 └─ visualization.png
```

---

## 12. score / NMS grid search

C fine-tuning 이후에는 optimal score threshold가 달라질 수 있으므로 test split에서 작은 grid를 다시 돌립니다.

```bash
for s in 0.30 0.40 0.50 0.60; do
  for n in 0.20 0.30 0.40; do
    REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 \
    LABEL_DIR=./data/real_labels \
    CKPT=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt \
    OUT_DIR=./eval_real_C_test_s${s}_nms${n}_iou025 \
    SCORE_THRESH=${s} \
    NMS_THRESH=${n} \
    IOU_THRESH=0.25 \
    bash ./scripts/eval_C_real_test.sh
  done
done
```

---

## 13. 참고 성능 로그

현재까지 관찰된 예시입니다.

```text
AB-fast-target90, real all 34-shot setting:
  score_thresh = 0.50
  nms_iou      = 0.30
  IoU thresh   = 0.25
  Precision    ≈ 0.228
  Recall       ≈ 0.077
  F1           ≈ 0.115
```

C fine-tuning 이후에는 held-out test split 기준으로 다시 기록해야 합니다.

---

## 14. 권장 실험 표 구조

```text
Baseline:
  original pseudo only

A:
  original pseudo + sensorized augmentation

B-fast:
  CAD/STL point-splat regenerated pseudo dataset

AB-fast:
  B-fast dataset + sensorized augmentation

C:
  AB-fast checkpoint + limited real LabelMe supervised fine-tuning
```

C는 real annotation을 학습에 쓰므로, 보고할 때는 반드시 synthetic-only setting과 분리해서 표기합니다.

---

## 15. 문제 발생 시 체크리스트

### `unrecognized arguments` 에러

`infer_depth_vq_detector.py` 또는 `eval_real_depth_vq_detector.py`가 오래된 버전입니다.

```bash
python infer_depth_vq_detector.py --help | grep -E "label_dir|center_crop|depth_keep|score_mode|nms_iou|bbox_source|debug_scores"
```

### `scene split manifest` 관련 에러

split json의 `scenes`가 string list인지 dict list인지 확인합니다.

```bash
python tools/fix_scene_split_manifest.py ./data/2d_dataset_B_fast_target90/splits
```

### generated B-fast scene이 비어 보이는 경우

```bash
python - <<'PY'
import numpy as np, json
f = "./data/2d_dataset_B_fast_target90/npz/scene_00000.npz"
z = np.load(f, allow_pickle=True)
print(z.files)
print("finite depth:", np.isfinite(z["depth"]).sum())
print("inst ids:", np.unique(z["inst_id"])[:20])
print("cat ids:", np.unique(z["category_id"])[:20])
meta = json.loads(str(z["meta"].item()))
print("visible:", meta.get("visible_inst_ids"))
PY
```

정상 기준:

```text
finite depth > 0
inst ids에 1 이상 존재
cat ids에 1 이상 존재
visible_inst_ids가 비어 있지 않음
```

### LabelMe real dataset에서 side/background depth가 normalization을 망가뜨리는 경우

C build 시 반드시 foreground cleaning을 사용합니다.

```bash
FOREGROUND_DEPTH_MODE=dilated_label
FOREGROUND_DILATE_PX=8
```

---

## 16. 최종 추천 실행 순서

공유받은 사람이 처음부터 재현하려면 아래 순서만 따르면 됩니다.

```bash
# 1. STL → point cloud
python stl_to_pointcloud_dataset.py --input_dir ./data/stl_dataset --output_dir ./data/cad_pointcloud_dataset --n_points 8192 --edge_ratio 0.2 --sharp_angle_deg 35 --recursive --export_ply

# 2. CAD encoder / memory bank
cd cad3d_encoder_code
python train_cad_encoder.py --manifest ../data/cad_pointcloud_dataset/manifest.json --out_dir ../runs/cad_pointnet2 --epochs 100 --batch_size 16 --n_points 4096 --rotation_aug none
python build_cad_memory_bank.py --manifest ../data/cad_pointcloud_dataset/manifest.json --checkpoint ../runs/cad_pointnet2/best.pt --output ../runs/cad_pointnet2/cad_memory_bank.npz --n_points 4096 --save_local
cd ..

# 3. synthetic split + warmup
python tools/make_scene_splits.py --data_root ./data/2d_dataset --out_dir ./data/2d_dataset/splits --train_ratio 0.8 --val_ratio 0.1 --test_ratio 0.1 --seed 42 --stratify_bg_kind --overwrite

# 4. B-fast dataset 생성
PARTIAL_OBJECT_PROB=1.0 TRUNCATION_OBJECT_PROB=0.50 SOFT_PIXEL_DROPOUT_RATE=0.04 PARTIAL_TARGET_VISIBLE_MIN=0.85 PARTIAL_TARGET_VISIBLE_MAX=0.95 PARTIAL_TARGET_VISIBLE_MEAN=0.90 STL_DIR=./data/stl_dataset REF_DATASET=./data/2d_dataset OUT_ROOT=./data/2d_dataset_B_fast_target90 REQUEST_JSON=./data/domain_profile/pseudo_regen_request.json NUM_SCENES=1000 POINTS_PER_ASSET=15000 SPLAT_RADIUS=1 bash ./scripts/render_B_dataset_fast.sh

# 5. AB 학습
DATA_ROOT=./data/2d_dataset_B_fast_target90 OUT_DIR=./runs/depth_vq_detector_AB_fast_target90_sensorized CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz INIT_CKPT=./runs/depth_detector_warmup_split/best.pt EPOCHS=100 BATCH_SIZE=4 bash ./scripts/train_AB_blenderproc_sensorized.sh

# 6. C real dataset 생성
DEPTH_DIR=./data/real_depth/npy LABEL_DIR=./data/real_labels OUT_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 REF_DATASET=./data/2d_dataset GLOB="shot_*.npy" CENTER_CROP="1/6,5/6" DEPTH_KEEP_RANGE="0.40,0.60" REAL_UINT16_MAX_DEPTH_M=10.0 FOREGROUND_DEPTH_MODE=dilated_label FOREGROUND_DILATE_PX=8 TRAIN_COUNT=30 VAL_COUNT=20 SEED=42 bash ./scripts/build_C_real_labelme_dataset.sh

# 7. C fine-tuning
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 INIT_CKPT=./runs/depth_vq_detector_AB_fast_target90_sensorized/best.pt CAD_MEMORY=./runs/cad_pointnet2/cad_memory_bank.npz OUT_DIR=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50 EPOCHS=120 BATCH_SIZE=2 LR=3e-5 IMAGE_SIZE="320,576" bash ./scripts/train_C_real_finetune.sh

# 8. held-out test 평가
REAL_ROOT=./data/real_labelme_dataset_C_fgclean_30_20_50 LABEL_DIR=./data/real_labels CKPT=./runs/depth_vq_detector_C_real_finetuned_fgclean_30_20_50/best.pt OUT_DIR=./eval_real_C_fgclean_30_20_50_test_s050_nms030_iou025 SCORE_THRESH=0.50 NMS_THRESH=0.30 IOU_THRESH=0.25 bash ./scripts/eval_C_real_test.sh
```
