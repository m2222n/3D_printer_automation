#!/usr/bin/env python3
"""정성 비교 (7/2 미팅): 같은 부품(main_body, cid=23)의 depth 형상 프로파일을
   합성-기존 / 합성-camsweep / 실측 세 소스로 나란히 시각화.
   목적: cam_sweep 재생성이 실측의 '원거리·작게·곡면' 프로파일에 더 가까워지는지 눈으로 확인.
"""
import glob, os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TARGET_CID = 23   # main_body
DATASETS = {
    "synth_orig (cam_h 0.36~0.44, FOV auto)": "/data/jtm/synth_out/dataset_2denc/npz",
    "synth_camsweep (cam_h 0.4~1.0, FOV fixed)": "/data/jtm/synth_out/dataset_2denc_camsweep/npz",
    "real (Blaze, per-scene 0-1)": "/data/jtm/synth_out/real_capture100/synthformat",
}

def find_scene_with_cid(npz_dir, cid, is_real=False):
    """해당 cid 부품이 가장 크게 찍힌 scene의 (부품 depth crop, 픽셀수) 반환."""
    best = None
    files = sorted(glob.glob(os.path.join(npz_dir, "*.npz")))
    for f in files[:400]:
        try:
            d = np.load(f, allow_pickle=True)
            cat = d["category_id"]; depth = d["depth"]
        except Exception:
            continue
        m = (cat == cid)
        n = int(m.sum())
        if n < 50:
            continue
        # crop bbox
        ys, xs = np.where(m)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        crop = np.where(m, depth, np.nan)[y0:y1+1, x0:x1+1]
        if best is None or n > best[2]:
            best = (os.path.basename(f), crop, n)
    return best

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, (title, d) in zip(axes, DATASETS.items()):
    if not os.path.isdir(d):
        ax.set_title(title + "\n(폴더 없음)"); ax.axis("off"); continue
    res = find_scene_with_cid(d, TARGET_CID)
    if res is None:
        ax.set_title(title + "\n(main_body 없음)"); ax.axis("off"); continue
    name, crop, n = res
    valid = crop[~np.isnan(crop)]
    # 각 소스가 서로 다른 스케일(m vs 0-1)이라, 형상만 보게 per-crop min-max 정규화
    lo, hi = np.nanpercentile(crop, 2), np.nanpercentile(crop, 98)
    im = ax.imshow(crop, cmap="turbo", vmin=lo, vmax=hi)
    spread_mm = (np.nanpercentile(valid,95) - np.nanpercentile(valid,5))
    unit = "" if "real" in title else "m"
    ax.set_title(f"{title}\n{name} | 픽셀 {n} | med {np.median(valid):.3f}{unit}\n"
                 f"crop {crop.shape[1]}x{crop.shape[0]}px", fontsize=8)
    ax.axis("off")
    plt.colorbar(im, ax=ax, fraction=0.046)

fig.suptitle("main_body depth profile: synth_orig vs synth_camsweep vs real (7/2)", fontsize=11)
plt.tight_layout()
out = "/home/jtm/kaist_project/docs/sim2real_probe_0701/profile_compare_0702.png"
plt.savefig(out, dpi=110, bbox_inches="tight")
print("저장:", out)

# 수치 요약도 출력
print("\n=== 부품 픽셀 크기 / 형상 변화폭 요약 (main_body) ===")
for title, d in DATASETS.items():
    if not os.path.isdir(d): print(f"  {title}: 폴더 없음"); continue
    res = find_scene_with_cid(d, TARGET_CID)
    if res is None: print(f"  {title}: 없음"); continue
    name, crop, n = res
    v = crop[~np.isnan(crop)]
    print(f"  {title[:30]:30s}: 최대픽셀수 {n:6d}, crop {crop.shape[1]}x{crop.shape[0]}")
