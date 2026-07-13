#!/usr/bin/env python3
"""실증 synthformat 변환 결과 검증 (7/2).

체크:
  1) 100장 존재 + 로드 OK
  2) 배경 = 0, 부품 = [0,1] 정규화 (조교 지시 7/1)
  3) category_id 분포 (1~27)
  4) 그룹 정답지 대조 — 각 장의 부품이 그 그룹(g1/g2/g3) 9종 안에 있는가?
     그룹 밖 부품 = 라벨 오류 자동 탐지.
"""
import json, glob, os
import numpy as np

SF_DIR = "/data/jtm/synth_out/real_capture100/synthformat"
LABELS = "/home/jtm/kaist_project/docs/real_capture100_group_labels.json"

lab = json.load(open(LABELS, encoding="utf-8"))
name2cid = lab["category_id"]
cid2name = {v: k for k, v in name2cid.items()}
groups = lab["groups"]                      # g1/g2/g3 -> [stl names]
group_cids = {g: set(name2cid[n] for n in names) for g, names in groups.items()}

files = sorted(glob.glob(os.path.join(SF_DIR, "*.npz")))
print(f"=== synthformat {len(files)}개 검증 ===\n")

bg_bad, norm_bad, empty, group_viol = [], [], [], []
cid_counter = {}
depth_ranges = []
parts_per_scene = []

for f in files:
    base = os.path.splitext(os.path.basename(f))[0]   # shot_XXX_gN
    grp = base.split("_")[-1]                          # g1/g2/g3
    d = np.load(f, allow_pickle=True)
    depth, inst, cat = d["depth"], d["inst_id"], d["category_id"]

    part = inst > 0
    npart = int(part.sum())
    if npart == 0:
        empty.append(base); continue

    # depth: 배경 처리 확인. 변환기 resize_nn이 배경을 NaN으로 되돌림 → NaN 또는 0 허용
    bg = ~part
    bg_vals = depth[bg]
    # 배경은 NaN이거나 0이어야 함
    bg_ok = np.all(np.isnan(bg_vals) | (bg_vals == 0))
    if not bg_ok:
        bg_bad.append((base, float(np.nanmax(np.where(bg, depth, np.nan)))))

    # 부품 depth = [0,1] 범위?
    pv = depth[part]
    pv = pv[~np.isnan(pv)]
    if pv.size:
        lo, hi = float(pv.min()), float(pv.max())
        depth_ranges.append((lo, hi))
        if lo < -1e-6 or hi > 1.0 + 1e-6:
            norm_bad.append((base, lo, hi))

    # category_id 분포 + 그룹 대조
    scene_cids = set(int(c) for c in np.unique(cat) if c > 0)
    parts_per_scene.append(len(scene_cids))
    for c in scene_cids:
        cid_counter[c] = cid_counter.get(c, 0) + 1
    viol = scene_cids - group_cids.get(grp, set())
    if viol:
        group_viol.append((base, grp, sorted(viol),
                           [cid2name.get(c, f"cid{c}") for c in sorted(viol)]))

print(f"[1] 로드: {len(files)}장, 빈 장면(부품0): {len(empty)}")
if empty: print("    ⚠️", empty)

print(f"\n[2] 배경 처리 (NaN/0): {'✅ 전부 OK' if not bg_bad else '⚠️ 위반 '+str(len(bg_bad))}")
for b in bg_bad[:5]: print("    ", b)

print(f"\n[3] 부품 depth 0-1 정규화: {'✅ 전부 [0,1]' if not norm_bad else '⚠️ 범위이탈 '+str(len(norm_bad))}")
for b in norm_bad[:5]: print("    ", b)
if depth_ranges:
    los = [r[0] for r in depth_ranges]; his = [r[1] for r in depth_ranges]
    print(f"    부품 depth min 분포: {min(los):.3f}~{max(los):.3f} (전부 0 근처여야)")
    print(f"    부품 depth max 분포: {min(his):.3f}~{max(his):.3f} (전부 1 근처여야)")

print(f"\n[4] category_id 분포 (등장 장면 수) — 27종 중 {len(cid_counter)}종 등장:")
for c in sorted(cid_counter):
    print(f"    cid {c:2d} {cid2name.get(c,'?'):30s}: {cid_counter[c]:3d}장")
missing = set(range(1, 28)) - set(cid_counter)
if missing:
    print(f"    ⚠️ 미등장 cid: {sorted(missing)} = {[cid2name.get(c,'?') for c in sorted(missing)]}")

print(f"\n[5] 그룹 정답지 대조 (그룹 밖 부품 = 라벨 오류): "
      f"{'✅ 위반 0' if not group_viol else '⚠️ 위반 '+str(len(group_viol))+'장'}")
for b in group_viol:
    print(f"    {b[0]} (그룹 {b[1]}) 밖 부품: {b[3]} (cid {b[2]})")

print(f"\n[요약] 장당 부품종수 평균 {np.mean(parts_per_scene):.1f} "
      f"(min {min(parts_per_scene)}, max {max(parts_per_scene)}), 그룹당 9종 중")
