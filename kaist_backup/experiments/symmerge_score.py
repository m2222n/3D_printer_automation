#!/usr/bin/env python3
# 대칭쌍 병합 후처리 채점 — 학습 불필요. per-scene CSV의 spatial_pairs를 파싱해
# 원본 F1 vs 대칭병합 F1을 재계산. C 모델서 +0.071 확인된 무료 카드.
# 사용: python symmerge_score.py <eval_out_dir> [<eval_out_dir> ...]
import csv, sys, os

# 거울상/앞뒤 = depth로 원천 구분 불가한 쌍 (진단 혼동 + 이름 근거)
SYM = [
    {"07_guide_paper_l", "09_guide_paper_r"},
    {"guide_paper_roll_cover_left", "guide_paper_roll_cover_right"},
    {"r_guide_a_l", "r_guide_a_r"},
    {"03_sol_block_front", "06_sol_block_back"},
]
def canon(name):
    for g in SYM:
        if name in g:
            return "|".join(sorted(g))
    return name

def score(csv_path):
    rows = list(csv.DictReader(open(csv_path)))
    tp = tp_m = 0
    for r in rows:
        for pair in r["spatial_pairs"].split(";"):
            pair = pair.strip()
            if not pair:
                continue
            d = dict(x.split("=", 1) for x in pair.split("|"))
            if "pred" not in d or "gt" not in d:
                continue
            if float(d.get("iou", 0)) < 0.5:
                continue
            tp += (d["pred"] == d["gt"])
            tp_m += (canon(d["pred"]) == canon(d["gt"]))
    n_pred = sum(int(r["n_pred"]) for r in rows)
    n_gt = sum(int(r["n_gt"]) for r in rows)
    def prf(t):
        p = t / n_pred if n_pred else 0
        rc = t / n_gt if n_gt else 0
        return p, rc, (2 * p * rc / (p + rc) if p + rc else 0)
    return prf(tp), prf(tp_m), tp, tp_m, n_pred, n_gt

print("=" * 78)
print("대칭쌍 병합 후처리 채점 (l↔r, front↔back 4쌍)")
print("=" * 78)
print(f"{'판(eval dir)':40s} {'원본 F1':>8s} {'병합 F1':>8s} {'Δ':>7s}")
print("-" * 78)
best = ("", 0.0)
for d in sys.argv[1:]:
    cp = os.path.join(d, "eval_real_per_scene.csv")
    if not os.path.exists(cp):
        print(f"{os.path.basename(d):40s}  (per_scene.csv 없음)")
        continue
    (p0, r0, f0), (pm, rm, fm), tp, tpm, npd, ngt = score(cp)
    name = os.path.basename(d.rstrip("/"))
    print(f"{name:40s} {f0:8.3f} {fm:8.3f} {fm-f0:+7.3f}")
    if fm > best[1]:
        best = (name, fm)
print("-" * 78)
print(f"🥇 대칭병합 기준 최고: {best[0]} = F1 {best[1]:.3f}")
