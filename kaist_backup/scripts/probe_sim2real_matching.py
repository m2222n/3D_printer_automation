#!/usr/bin/env python3
"""단일 부품 sim↔real 정합성 검증 (교수님 7/1 지시).

의도(교수님):
  "학습 전에 부품 하나만 대상으로, 촘촘히 찍은 합성과 실측 1장이
   매칭되는지, 얼마나 잘 되는지 정량·정성으로 확인하자.
   depth 값 범위·부품 크기가 다를 수 있다 → 데이터 정합성 확인."

핵심 설계:
  - 비교는 반드시 **조교 파이프라인의 정규화(robust_normalize_depth)를 통과한 뒤** 한다.
    (raw로 비교하면 median-빼기 효과를 못 봄. 모델이 실제 보는 표현으로 비교해야 의미.)
  - robust_normalize_depth = 조교 `depth_preprocess.py` 로직을 numpy로 그대로 복제
    (venv에 torch 없어 직접 import 불가 → 순수 numpy 함수라 동치 재현).

산출:
  - 정량: raw depth 통계(min/med/max) + 정규화 후 통계 → sim vs real 표(JSON)
  - 정성: 부품 1개 depth를 [raw | normalized] 나란히 시각화 PNG

STAGE 1 (이 스크립트): 이미 있는 합성 npz(부품별 crop) vs 실측 crop 비교.
  거리 스윕 렌더 없이도, 정규화가 절대거리 갭을 흡수하는지 즉시 확인 가능.
STAGE 2 (후속): 부품 1종을 카메라 높이 0.4~3.0m로 렌더한 '거리 스윕' 세트 vs 실측.
"""
import json, glob, os, argparse
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TARGET_PART = "main_body"   # 형상 크고 뚜렷 (g1 전 장에 존재 확인됨). --part로 변경 가능
REAL_NPY_DIR = "/data/jtm/synth_out/real_capture100/npy"
REAL_JSON_DIR = "/data/jtm/synth_out/real_capture100/labelme_json"
SYNTH_CROP_DIR = "/data/jtm/synth_out/dataset_2denc/crops"   # 부품별 crop npz
SYNTH_NPZ_DIR = "/data/jtm/synth_out/dataset_2denc/npz"      # scene npz
OUT_DIR = "/home/jtm/kaist_project/docs/sim2real_probe_0701"
PNG_SCALE = 2.0   # label_png(1696x960) = npy(848x480) x2


# ---- 조교 robust_normalize_depth 동치 재현 (순수 numpy) --------------------
def robust_normalize_depth(depth, valid):
    """조교 depth_preprocess.robust_normalize_depth 와 동일.
    (z - median) / (p95 - p05), 배경 0, [-5,5] clip."""
    z = depth.astype(np.float32).copy()
    if valid.sum() < 10:
        z[:] = 0.0
        return z, 0.0, 1.0
    vals = z[valid]
    med = float(np.median(vals))
    p05, p95 = np.percentile(vals, [5, 95])
    scale = float(max(p95 - p05, 1e-3))
    z = (z - med) / scale
    z[~valid] = 0.0
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    z = np.clip(z, -5.0, 5.0)
    return z.astype(np.float32), med, scale


def stats(depth_valid_vals):
    v = depth_valid_vals
    if v.size == 0:
        return {}
    return {
        "n_px": int(v.size),
        "min": round(float(v.min()), 4),
        "p05": round(float(np.percentile(v, 5)), 4),
        "median": round(float(np.median(v)), 4),
        "p95": round(float(np.percentile(v, 95)), 4),
        "max": round(float(v.max()), 4),
        "std": round(float(v.std()), 4),
    }


def poly_to_mask(points, h, w, scale):
    from PIL import Image, ImageDraw
    img = Image.new("L", (w, h), 0)
    pts = [(x / scale, y / scale) for x, y in points]
    ImageDraw.Draw(img).polygon(pts, outline=1, fill=1)
    return np.array(img, dtype=bool)


# ---- 실측: 특정 장에서 TARGET_PART crop (mm) ------------------------------
def load_real_part(shot_json):
    base = os.path.splitext(os.path.basename(shot_json))[0]
    raw = np.load(os.path.join(REAL_NPY_DIR, base + ".npy")).astype(np.float32)  # mm
    h, w = raw.shape
    lj = json.load(open(shot_json, encoding="utf-8"))
    for s in lj.get("shapes", []):
        if s["label"].replace(".stl", "") == TARGET_PART:
            m = poly_to_mask(s["points"], h, w, PNG_SCALE) & (raw > 0)
            if m.sum() < 10:
                continue
            ys, xs = np.where(m)
            y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
            crop = np.where(m, raw, 0.0)[y0:y1, x0:x1]  # mm, 배경 0
            crop_m = crop / 1000.0                        # m
            crop_m[crop_m == 0] = np.nan                  # 배경 NaN(정규화 valid에서 제외)
            return crop_m, base
    return None, base


# ---- 합성: TARGET_PART crop npz 로드 (m, 배경 NaN) ------------------------
def load_synth_part(max_n=30):
    """crop npz 8000여개 → stl 키로 TARGET_PART만 골라 max_n개 로드."""
    out = []
    for f in sorted(glob.glob(os.path.join(SYNTH_CROP_DIR, "*.npz"))):
        try:
            z = np.load(f, allow_pickle=True)
        except Exception:
            continue
        # crop npz 구조: keys = depth/mask/label/quat/euler/bbox/stl (개별 키)
        stl = ""
        if "stl" in z.files:
            stl = str(z["stl"]).replace(".stl", "")
        elif "label" in z.files:
            stl = str(z["label"]).replace(".stl", "")
        if stl != TARGET_PART:
            continue
        d = z["depth"].astype(np.float32) if "depth" in z.files else z[z.files[0]].astype(np.float32)
        out.append((d, os.path.basename(f)))
        if len(out) >= max_n:
            break
    return out


def summarize(depth_m, name):
    """raw(부품 유효픽셀) 통계 + 정규화 후 통계."""
    valid = np.isfinite(depth_m) & (depth_m > 0)
    raw_vals = depth_m[valid]
    z_norm, med, scale = robust_normalize_depth(depth_m, valid)
    return {
        "name": name,
        "raw_m": stats(raw_vals),
        "norm_median_subtracted": stats(z_norm[valid]),
        "norm_med": round(med, 4), "norm_scale": round(scale, 4),
    }


def viz_pair(real_raw, synth_raw, part, out_png):
    """정성: 실측 1개 + 합성 1개를 [raw | normalized] 4패널로 비교."""
    def norm_for_show(d):
        valid = np.isfinite(d) & (d > 0)
        z, _, _ = robust_normalize_depth(d, valid)
        z[~valid] = np.nan
        return z
    fig, ax = plt.subplots(2, 2, figsize=(9, 8))
    panels = [
        (real_raw, "REAL raw depth (m)", ax[0][0], "viridis"),
        (norm_for_show(real_raw), "REAL normalized (모델 입력)", ax[0][1], "coolwarm"),
        (synth_raw, "SYNTH raw depth (m)", ax[1][0], "viridis"),
        (norm_for_show(synth_raw), "SYNTH normalized (모델 입력)", ax[1][1], "coolwarm"),
    ]
    for d, title, a, cmap in panels:
        im = a.imshow(d, cmap=cmap)
        a.set_title(title, fontsize=11); a.axis("off")
        fig.colorbar(im, ax=a, fraction=0.046)
    fig.suptitle(f"sim2real 정합성: {part}  (정규화 후 두 행이 비슷해야 정합)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_png, dpi=90, bbox_inches="tight")
    plt.close(fig)


def main():
    global TARGET_PART
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="main_body")
    ap.add_argument("--n_real", type=int, default=5)
    ap.add_argument("--n_synth", type=int, default=30)
    args = ap.parse_args()
    TARGET_PART = args.part
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"=== 단일 부품 정합성 검증: {TARGET_PART} ===\n")

    # --- 실측 ---
    real = []
    real_arrs = []
    for jp in sorted(glob.glob(os.path.join(REAL_JSON_DIR, "*.json"))):
        crop, base = load_real_part(jp)
        if crop is not None:
            real.append(summarize(crop, "REAL:" + base))
            real_arrs.append(crop)
        if len(real) >= args.n_real:
            break
    print(f"실측 {TARGET_PART} crop: {len(real)}장")

    # --- 합성 ---
    synth_raw = load_synth_part(args.n_synth)
    synth = [summarize(d, "SYNTH:" + n) for d, n in synth_raw]
    print(f"합성 {TARGET_PART} crop: {len(synth)}장\n")

    if not real or not synth:
        print("⚠️ 한쪽이 비어 비교 불가. crop 경로/부품명 확인 필요.")
        # 합성 crop 폴더에 어떤 stl들이 있는지 힌트
        return

    # --- 집계 ---
    def agg(items, field, sub):
        arr = [it[field][sub] for it in items if it[field]]
        return round(float(np.median(arr)), 4) if arr else None

    report = {
        "part": TARGET_PART,
        "n_real": len(real), "n_synth": len(synth),
        "RAW_depth_m (median across crops)": {
            "real": {"median": agg(real, "raw_m", "median"),
                     "min": agg(real, "raw_m", "min"),
                     "max": agg(real, "raw_m", "max")},
            "synth": {"median": agg(synth, "raw_m", "median"),
                      "min": agg(synth, "raw_m", "min"),
                      "max": agg(synth, "raw_m", "max")},
        },
        "NORMALIZED (median across crops) — 조교 파이프라인 통과 후": {
            "real": {"median": agg(real, "norm_median_subtracted", "median"),
                     "p05": agg(real, "norm_median_subtracted", "p05"),
                     "p95": agg(real, "norm_median_subtracted", "p95"),
                     "std": agg(real, "norm_median_subtracted", "std")},
            "synth": {"median": agg(synth, "norm_median_subtracted", "median"),
                      "p05": agg(synth, "norm_median_subtracted", "p05"),
                      "p95": agg(synth, "norm_median_subtracted", "p95"),
                      "std": agg(synth, "norm_median_subtracted", "std")},
        },
        "detail_real": real, "detail_synth": synth,
    }

    out_json = os.path.join(OUT_DIR, f"probe_{TARGET_PART}.json")
    json.dump(report, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # --- 정성 시각화 (실측 1 + 합성 1) ---
    if real_arrs and synth_raw:
        out_png = os.path.join(OUT_DIR, f"probe_{TARGET_PART}.png")
        viz_pair(real_arrs[0], synth_raw[0][0], TARGET_PART, out_png)
        print(f"✅ 정성 시각화: {out_png}")

    # --- 콘솔 요약 ---
    print("─" * 64)
    print("RAW depth (m) — 절대 거리:")
    r = report["RAW_depth_m (median across crops)"]
    print(f"  실측  median={r['real']['median']}  ({r['real']['min']}~{r['real']['max']})")
    print(f"  합성  median={r['synth']['median']}  ({r['synth']['min']}~{r['synth']['max']})")
    print("  → 절대 거리는 다름 (예상). 아래 정규화 후가 핵심.\n")
    print("NORMALIZED (median 빼고 robust scale) — 모델이 실제 보는 표현:")
    n = report["NORMALIZED (median across crops) — 조교 파이프라인 통과 후"]
    print(f"  실측  median={n['real']['median']}  p05={n['real']['p05']}  p95={n['real']['p95']}  std={n['real']['std']}")
    print(f"  합성  median={n['synth']['median']}  p05={n['synth']['p05']}  p95={n['synth']['p95']}  std={n['synth']['std']}")
    print("  → 이 값들이 가까우면 정합 OK (절대 거리 갬을 정규화가 흡수).")
    print("─" * 64)
    print(f"\n✅ 리포트 저장: {out_json}")


if __name__ == "__main__":
    main()
