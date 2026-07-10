import numpy as np, glob, os
# camsweep 3장 정규화 로직을 실제 데이터에 적용해서 결과 분포가 실측과 맞는지 검증
src = sorted(glob.glob("data/2d_dataset_camsweep/npz/*.npz"))[:3]
for f in src:
    d = np.load(f); dep = d["depth"].astype(np.float32); inst = d["inst_id"]
    part = inst > 0
    pv = dep[part]; pv = pv[np.isfinite(pv)]
    lo, hi = float(pv.min()), float(pv.max()); rng = hi - lo if hi > lo else 1.0
    new = np.full_like(dep, np.nan)
    pm = part & np.isfinite(dep)
    new[pm] = np.clip((dep[pm] - lo) / rng, 0, 1)
    npv = new[part]; npv = npv[np.isfinite(npv)]
    print("%s  raw[%.3f~%.3f] → norm[%.3f~%.3f] med %.3f  배경NaN %d" % (
        os.path.basename(f), lo, hi, npv.min(), npv.max(), np.median(npv), np.isnan(new).sum()))
print("\n실측 타겟: 부품 min~0, max~1, 배경 NaN ~254k")
