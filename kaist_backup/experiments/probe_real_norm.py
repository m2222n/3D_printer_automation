import numpy as np, glob, os
# 실측 여러 장에서 부품 depth의 min/max가 장마다 정확히 0/1인지 = per-scene min-max 확인
files = sorted(glob.glob("data/real_capture100_eval/**/*.npz", recursive=True))[:8]
for f in files:
    d = np.load(f); dep = d["depth"].astype(np.float32); inst = d["inst_id"]
    part = inst > 0
    pv = dep[part]
    print("%s  부품 min %.4f max %.4f  (배경 NaN수 %d)" % (
        os.path.basename(f), pv.min(), pv.max(), np.isnan(dep).sum()))
