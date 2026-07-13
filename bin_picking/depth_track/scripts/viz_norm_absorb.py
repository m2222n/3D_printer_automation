#!/usr/bin/env python3
"""배율 상쇄 증명 시각화 (7/2 미팅): 실측 raw depth에 배율 k(÷3.5, 1, ×2, ×3.5)를 곱해도
robust_normalize_depth 통과 후 히스토그램이 완전히 겹침 → 선형 스케일 오류가 정규화에서 소거됨.
"""
import glob, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def robust_normalize_depth(depth, valid):
    z = depth.astype(np.float32).copy()
    if valid.sum() < 10:
        z[:] = 0.0; return z
    vals = z[valid]
    med = float(np.median(vals))
    p05, p95 = np.percentile(vals, [5, 95])
    scale = float(max(p95 - p05, 1e-3))
    z = (z - med) / scale
    z[~valid] = 0.0
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(z, -5.0, 5.0)

RAW = sorted(glob.glob("/data/jtm/synth_out/real_capture100/npy/*.npy"))[0]
raw = np.load(RAW).astype(np.float32)
valid = raw > 0

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

# 왼쪽: raw depth 히스토그램 (배율 곱하면 위치가 밀림)
for k, lab in [(1/3.5, "x1/3.5"), (1.0, "x1 (raw)"), (3.5, "x3.5")]:
    ax1.hist((raw[valid]*k).ravel(), bins=80, alpha=0.5, label=lab, density=True)
ax1.set_title("BEFORE normalize: raw depth * k\n(scale error shifts distribution)", fontsize=10)
ax1.set_xlabel("depth (mm * k)"); ax1.legend(fontsize=8)

# 오른쪽: robust_normalize 후 (전부 겹침)
for k, lab in [(1/3.5, "x1/3.5"), (1.0, "x1"), (2.0, "x2"), (3.5, "x3.5")]:
    z = robust_normalize_depth(raw*k, valid)
    ax2.hist(z[valid].ravel(), bins=80, alpha=0.45, label=lab, density=True)
ax2.set_title("AFTER robust_normalize_depth\n(all overlap -> scale error absorbed)", fontsize=10)
ax2.set_xlabel("normalized (median-subtracted / p05-p95)"); ax2.legend(fontsize=8)

fig.suptitle("Linear depth-scale error is fully absorbed by normalization (7/2 proof)", fontsize=11)
plt.tight_layout()
out = "/home/jtm/kaist_project/docs/sim2real_probe_0701/norm_absorb_0702.png"
plt.savefig(out, dpi=110, bbox_inches="tight")
print("저장:", out)
