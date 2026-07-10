import numpy as np, glob, os

def one(tag, pat):
    files = sorted(glob.glob(pat, recursive=True))
    files = [x for x in files if "/npz/" in x or "real_capture" in x]
    if not files:
        print(tag, "파일없음", pat); return
    f = files[0]
    d = np.load(f); dep = d["depth"].astype(np.float32); inst = d["inst_id"]
    bg = inst == 0; part = inst > 0
    name = os.path.basename(f)
    bgvals = dep[bg]
    print("--- %s  %s ---" % (tag, name))
    print("  배경(inst=0) depth 고유값수 %d  min %.3f max %.3f  NaN %d" % (
        len(np.unique(bgvals[np.isfinite(bgvals)])),
        np.nanmin(bgvals) if np.isfinite(bgvals).any() else -1,
        np.nanmax(bgvals) if np.isfinite(bgvals).any() else -1,
        np.isnan(bgvals).sum()))
    pv = dep[part]
    print("  부품 depth min %.3f max %.3f  NaN %d" % (
        np.nanmin(pv), np.nanmax(pv), np.isnan(pv).sum()))

one("camnear(0-1)", "data/dataset_2denc_camnear_01/**/*.npz")
one("real(0-1)   ", "data/real_capture100_eval/**/*.npz")
one("camsweep(raw)", "data/2d_dataset_camsweep/**/*.npz")
