"""깨끗한 추론 예시 시각화 — eval 저장 예측(all_predictions) 기반, eval과 100% 일치.
shot_016_g1: 부품 9개 전부 정답(F1=1.0, maskIoU 0.89). depth 배경 + 예측 박스 + 종류명.
"""
import json, numpy as np, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches

PRED = "/workspace/cadence/eval_T100_csblur_lr1e4_ep80_test102/predictions/shot_016_g1.json"
DEPTH = "/workspace/cadence/mentoring_new/data/real_labelme_dataset_E200_noside/test_depth_symlinks_t100/shot_016_g1.npy"
OUT = "/workspace/cadence/viz_clean_016.png"

d = json.load(open(PRED))
preds = d["predictions"]
crop = d.get("crop_bbox_yxyx")  # [y0,x0,y1,x1] — bbox가 crop 좌표계일 수 있음
src_hw = d.get("source_depth_hw")

# depth 로드 (uint16 → m, 조교 변환식 uint16*10/65535)
raw = np.load(DEPTH).astype(np.float32)
depth_m = raw * 10.0 / 65535.0
depth_m[depth_m <= 0] = np.nan

# crop 영역만 (bbox가 crop 좌표계이므로 배경도 crop에 맞춤)
if crop:
    y0, x0, y1, x1 = [int(v) for v in crop]
    depth_crop = depth_m[y0:y1, x0:x1]
else:
    depth_crop = depth_m
    x0 = y0 = 0

fig, ax = plt.subplots(figsize=(7, 8))
# depth 컬러맵 (가까울수록 난색 = turbo reversed)
vmin, vmax = np.nanpercentile(depth_crop, 2), np.nanpercentile(depth_crop, 98)
ax.imshow(depth_crop, cmap="turbo_r", vmin=vmin, vmax=vmax)
ax.set_facecolor("black")

cmap = plt.cm.tab10
for i, p in enumerate(preds):
    x1b, y1b, x2b, y2b = p["bbox_xyxy"]  # crop 좌표계로 가정
    name = p["cad_id"].split("__")[0]  # 해시 접미사 제거
    col = cmap(i % 10)
    rect = patches.Rectangle((x1b, y1b), x2b - x1b, y2b - y1b,
                             linewidth=2, edgecolor=col, facecolor="none")
    ax.add_patch(rect)
    ax.text(x1b, y1b - 3, name, color="white", fontsize=8,
            bbox=dict(facecolor=col, edgecolor="none", pad=1, alpha=0.9))

ax.set_title("Inference on real depth — 9/9 parts detected, all classes correct (F1=1.0)", fontsize=11)
ax.axis("off")
plt.tight_layout()
plt.savefig(OUT, dpi=140, bbox_inches="tight", facecolor="white")
print("saved:", OUT, "preds:", len(preds))
