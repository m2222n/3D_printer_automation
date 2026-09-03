#!/usr/bin/env python3
"""홀 축 방향 전수 조사 — "눕힌 채로 드릴 면이 위를 향하는가" (2026-09-03)

목적
  리그립 스테이션이 필요한지 가르는 입력값을 만든다.
  부품은 빈에 가장 얇은 변을 높이로 눕는다(8/6 전제 = DB lying_height_mm 와 bbox 최소축이 27종 전부 일치).
  그 자세에서 각 홀의 축이
    · 높이축과 평행(위/아래)  → 위에서 드릴 가능 (관통이면 어느 면이 위든 OK, 막힘이면 그 면이 위일 때만)
    · 높이축과 수직(측면)     → 눕힌 채로는 못 뚫는다 = 리그립 필요
  를 전수 분류한다.

방법 (8/4 find_holes3 와 같은 계열 — trimesh 없이 STL 직접 파싱, numpy 만)
  1. 삼각형을 평면 패치로 묶는다 (법선 + 평면 오프셋 양자화)
  2. 패치의 경계 에지(패치 안에서 1회만 나타나는 에지)를 루프로 이어 붙인다
  3. 루프를 평면 2D 로 투영해 원 피팅(Kasa) — 잔차 작고 점 8개 이상이면 "원형 개구"
     패치 안에서 면적이 가장 큰 루프는 외곽선이므로 제외 (보스 윗면 원은 홀이 아니다)
  4. 같은 축선·같은 지름의 개구가 반대 법선 평면에 쌍으로 있으면 관통홀로 병합

🚨 8/4 기록(총 171 개구 · 02_sol_block_b 20 · 01_sol_block_a 18 · plate_e 15 · 관통 43)을
   기준선으로 재현 확인할 것 — 재현이 안 되면 도구 탓인지 데이터 탓인지 못 가른다(8/7 교훈).

사용
  /data/jtm/depth_venv/bin/python bin_picking/tests/survey_hole_axes.py \
      --stl-dir ~/kaist_render/stl --db bin_picking/config/grasp_database.yaml \
      --out /data/jtm/hole_axis_survey_0903
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict

import numpy as np

# ---------------------------------------------------------------- STL 로드
def load_stl(path: str) -> np.ndarray:
    """(N,3,3) float64 삼각형 배열. 바이너리/ASCII 자동 판별."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        vals = re.findall(rb"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", data)
        return np.array(vals, dtype=float).reshape(-1, 3, 3)
    n = struct.unpack("<I", data[80:84])[0]
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    arr = np.frombuffer(data[84:84 + n * 50], dtype=rec)
    return arr["v"].astype(float)


# ---------------------------------------------------------------- 기하 유틸
def tri_normals(tri: np.ndarray) -> np.ndarray:
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    l = np.linalg.norm(n, axis=1, keepdims=True)
    l[l == 0] = 1.0
    return n / l


def plane_basis(n: np.ndarray):
    """법선 n 에 수직인 정규직교 기저 (u, v)."""
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a); u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v


def fit_circle_2d(pts: np.ndarray):
    """Kasa 대수 피팅. (cx, cy, r, rms_residual)"""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x ** 2 + y ** 2)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    a, bb, c = sol
    cx, cy = -a / 2, -bb / 2
    r2 = cx ** 2 + cy ** 2 - c
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    res = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r
    return cx, cy, r, float(np.sqrt(np.mean(res ** 2)))


def polygon_area_2d(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def chain_loops(edges):
    """경계 에지 리스트 [(a,b), ...] (정수 정점 id) → 루프 리스트 [[id,...], ...]"""
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b); adj[b].append(a)
    used = set()
    loops = []
    for start in list(adj):
        if start in used:
            continue
        loop = [start]; used.add(start)
        prev, cur = None, start
        while True:
            nxts = [x for x in adj[cur] if x != prev and x not in used]
            if not nxts:
                break
            nxt = nxts[0]
            loop.append(nxt); used.add(nxt)
            prev, cur = cur, nxt
        if len(loop) >= 3 and start in adj[cur]:
            loops.append(loop)
    return loops


# ---------------------------------------------------------------- 홀 검출
def detect_openings(tri: np.ndarray, *, q_vert=1e-3, q_norm=2, q_off=0.05,
                    min_pts=8, r_min=0.5, r_max=20.0, rms_rel=0.03):
    """
    원형 개구(hole opening) 목록.
    각 항목 = dict(center(3), normal(3), radius, rms, n_pts, plane_offset)
    """
    nrm = tri_normals(tri)
    cent = tri.mean(axis=1)
    off = np.einsum("ij,ij->i", nrm, cent)
    keys = [tuple(np.round(nrm[i], q_norm)) + (round(off[i] / q_off) * q_off,) for i in range(len(tri))]
    groups = defaultdict(list)
    for i, k in enumerate(keys):
        groups[k].append(i)

    # 정점 id 부여(양자화)
    verts_q = np.round(tri.reshape(-1, 3) / q_vert).astype(np.int64)
    vid_map = {}
    vids = np.empty(len(verts_q), dtype=np.int64)
    for i, v in enumerate(map(tuple, verts_q)):
        vids[i] = vid_map.setdefault(v, len(vid_map))
    vids = vids.reshape(-1, 3)
    vpos = np.zeros((len(vid_map), 3))
    for v, i in vid_map.items():
        vpos[i] = np.array(v) * q_vert

    # 전역 에지 → 삼각형 목록 (홀/보스 판별용: 루프 건너편 벽면의 법선 방향)
    edge_tris = defaultdict(list)
    for i in range(len(tri)):
        a, b, c = vids[i]
        for e in ((a, b), (b, c), (c, a)):
            edge_tris[tuple(sorted(e))].append(i)

    openings = []
    bosses = 0
    for k, idxs in groups.items():
        if len(idxs) < 2:
            continue
        n = np.array(k[:3], dtype=float)
        if np.linalg.norm(n) == 0:
            continue
        n /= np.linalg.norm(n)
        idx_set = set(idxs)
        ecount = defaultdict(int)
        for i in idxs:
            a, b, c = vids[i]
            for e in ((a, b), (b, c), (c, a)):
                ecount[tuple(sorted(e))] += 1
        boundary = [e for e, cnt in ecount.items() if cnt == 1]
        if len(boundary) < min_pts:
            continue
        loops = chain_loops(boundary)
        if len(loops) < 2:
            continue  # 루프 하나 = 외곽선만 ⇒ 홀 없음(보스 윗면 원 등 제외)
        u, v = plane_basis(n)
        loop2d = []
        for lp in loops:
            P = vpos[lp]
            P2 = np.column_stack([P @ u, P @ v])
            loop2d.append((lp, P, P2, polygon_area_2d(P2)))
        outer_i = int(np.argmax([x[3] for x in loop2d]))
        for j, (lp, P, P2, area) in enumerate(loop2d):
            if j == outer_i or len(lp) < min_pts:
                continue
            fit = fit_circle_2d(P2)
            if fit is None:
                continue
            cx, cy, r, rms = fit
            if not (r_min <= r <= r_max) or rms > rms_rel * r:
                continue
            # 중심을 정확히: 2D 중심을 3D 로 되돌림
            c3 = cx * u + cy * v + n * float(np.mean(P @ n))
            # ---- 홀 vs 보스 판별 ----
            # 루프 에지 건너편(이 패치가 아닌) 삼각형 = 원통 벽면. 그 법선이 축 중심을 향하면 홀(안이 빈 공간),
            # 바깥을 향하면 보스(안이 재료). 8/4 v3 는 이 구분을 못 해 돌기 밑동을 홀로 셌을 수 있다.
            score, cnt = 0.0, 0
            for a_, b_ in zip(lp, lp[1:] + lp[:1]):
                e = tuple(sorted((a_, b_)))
                for t in edge_tris.get(e, ()):
                    if t in idx_set:
                        continue
                    mid = (vpos[a_] + vpos[b_]) / 2
                    to_axis = c3 - mid
                    to_axis -= np.dot(to_axis, n) * n
                    if np.linalg.norm(to_axis) < 1e-9:
                        continue
                    score += float(np.dot(nrm[t], to_axis / np.linalg.norm(to_axis)))
                    cnt += 1
            if cnt == 0:
                continue
            if score / cnt < 0:          # 벽면 법선이 축에서 멀어진다 = 보스
                bosses += 1
                continue
            openings.append(dict(center=c3, normal=n, radius=r, rms=rms, n_pts=len(lp)))
    detect_openings.last_bosses = bosses
    return openings


def merge_through(openings, *, tol_center=0.15, tol_r=0.1):
    """반대 법선·같은 축선·같은 지름의 개구 쌍 → 관통홀. 반환: holes 리스트"""
    used = [False] * len(openings)
    holes = []
    for i, a in enumerate(openings):
        if used[i]:
            continue
        match = None
        for j in range(i + 1, len(openings)):
            if used[j]:
                continue
            b = openings[j]
            if abs(abs(np.dot(a["normal"], b["normal"])) - 1) > 1e-3:
                continue
            if abs(a["radius"] - b["radius"]) > tol_r:
                continue
            # 축선 일치: 중심 차이 중 법선 수직 성분
            d = b["center"] - a["center"]
            perp = d - np.dot(d, a["normal"]) * a["normal"]
            if np.linalg.norm(perp) > tol_center:
                continue
            match = j
            break
        if match is None:
            holes.append(dict(axis=a["normal"], radius=a["radius"], center=a["center"],
                              through=False, depth=None, faces=1))
            used[i] = True
        else:
            b = openings[match]
            depth = abs(float(np.dot(b["center"] - a["center"], a["normal"])))
            holes.append(dict(axis=a["normal"], radius=a["radius"],
                              center=(a["center"] + b["center"]) / 2,
                              through=True, depth=depth, faces=2))
            used[i] = used[match] = True
    return holes


# ---------------------------------------------------------------- DB
def load_db_parts(path):
    """grasp_database.yaml 을 최소 파싱(pyyaml 없이) → {part: {pickability, lying_height_mm}}"""
    parts, cur = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  ([A-Za-z0-9_\"]+):\s*$", line)
            if m:
                cur = m.group(1).strip('"'); parts[cur] = {}; continue
            if cur:
                m2 = re.match(r'^\s+(pickability|lying_height_mm):\s*"?([^"#\s]+)"?', line)
                if m2:
                    parts[cur][m2.group(1)] = m2.group(2)
    return parts


# ---------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", default=os.path.expanduser("~/kaist_render/stl"))
    ap.add_argument("--db", default="bin_picking/config/grasp_database.yaml")
    ap.add_argument("--out", default="/data/jtm/hole_axis_survey_0903")
    ap.add_argument("--drill-dmax", type=float, default=5.5,
                    help="드릴 대상으로 볼 최대 지름(mm). M3·M5 계열 = 5.5 이하")
    ap.add_argument("--parallel-cos", type=float, default=0.9)
    args = ap.parse_args()

    db = load_db_parts(args.db) if os.path.exists(args.db) else {}
    os.makedirs(args.out, exist_ok=True)

    rows, total_open, total_holes, total_through = [], 0, 0, 0
    for fn in sorted(os.listdir(args.stl_dir)):
        if not fn.lower().endswith(".stl"):
            continue
        part = fn[:-4]
        tri = load_stl(os.path.join(args.stl_dir, fn))
        v = tri.reshape(-1, 3)
        ext = v.max(0) - v.min(0)
        lying_axis = int(np.argmin(ext))            # 눕힘 축 = bbox 최소축 (DB lying_height 와 일치 확인됨)
        e_up = np.zeros(3); e_up[lying_axis] = 1.0

        openings = detect_openings(tri)
        n_boss = getattr(detect_openings, "last_bosses", 0)
        holes = merge_through(openings)
        total_open += len(openings); total_holes += len(holes)
        total_through += sum(h["through"] for h in holes)

        vert_thru = vert_blind = side = 0
        vert_thru_d = vert_blind_d = side_d = 0          # 드릴 대상(≤dmax) 만
        blind_faces = defaultdict(int)                   # 막힘 홀이 어느 면(+/−)에 있나
        dias = []
        for h in holes:
            d = 2 * h["radius"]; dias.append(d)
            is_drill = d <= args.drill_dmax
            c = abs(float(np.dot(h["axis"], e_up)))
            if c >= args.parallel_cos:
                if h["through"]:
                    vert_thru += 1; vert_thru_d += is_drill
                else:
                    vert_blind += 1; vert_blind_d += is_drill
                    # 개구가 향하는 쪽: center 가 부품 중간보다 위인가
                    mid = (v.max(0)[lying_axis] + v.min(0)[lying_axis]) / 2
                    blind_faces["+" if h["center"][lying_axis] > mid else "-"] += 1
            else:
                side += 1; side_d += is_drill

        n_holes = len(holes)
        if n_holes == 0:
            verdict = "⬜ 홀 없음(드릴 대상 아님)"
        elif side_d > 0:
            verdict = "🔴 측면 홀 있음 → 리그립 필요"
        elif vert_blind_d > 0 and len(blind_faces) == 2:
            verdict = "🟠 양면에 막힘 홀 → 한 면 뚫고 뒤집어야(리그립)"
        elif vert_blind_d > 0:
            verdict = "🟡 한 면 막힘 홀 → 그 면이 위일 때만(뒤집힘 의존)"
        elif vert_thru_d > 0:
            verdict = "🟢 관통 홀만 → 리그립 불필요"
        else:
            verdict = "⬜ 드릴 대상 지름 없음(큰 홀만)"

        info = db.get(part, {})
        rows.append(dict(
            part=part, pickability=info.get("pickability", "?"),
            lying_axis="XYZ"[lying_axis], lying_height=float(ext[lying_axis]),
            db_lying_height=info.get("lying_height_mm"),
            openings=len(openings), bosses_excluded=n_boss, holes=n_holes,
            vert_through=vert_thru, vert_blind=vert_blind, side=side,
            drill_vert_through=vert_thru_d, drill_vert_blind=vert_blind_d, drill_side=side_d,
            blind_faces=dict(blind_faces),
            dia_min=round(min(dias), 2) if dias else None,
            dia_max=round(max(dias), 2) if dias else None,
            verdict=verdict,
            holes_detail=[dict(d=round(2 * h["radius"], 2), through=h["through"],
                               depth=None if h["depth"] is None else round(h["depth"], 2),
                               axis="XYZ"[int(np.argmax(np.abs(h["axis"])))],
                               vs_up=round(abs(float(np.dot(h["axis"], e_up))), 2),
                               center=[round(float(x), 2) for x in h["center"]]) for h in holes],
        ))

    # ------------------------------------------------ 출력
    with open(os.path.join(args.out, "hole_axis_survey.json"), "w", encoding="utf-8") as f:
        json.dump(dict(stl_dir=args.stl_dir, drill_dmax=args.drill_dmax,
                       totals=dict(openings=total_open, holes=total_holes, through=total_through),
                       parts=rows), f, ensure_ascii=False, indent=1)

    print(f"# 홀 축 조사 — 개구 {total_open} · 병합 홀 {total_holes} · 관통 {total_through}   (드릴 대상 = ø≤{args.drill_dmax})")
    print(f"# 보스(돌기) 밑동으로 제외된 원형 루프 = {sum(r['bosses_excluded'] for r in rows)}")
    print(f"# 8/4 기준선: 개구 171 · 관통 43 · 02_sol_block_b 20 · 01_sol_block_a 18 · plate_e 15")
    print()
    hdr = f"{'부품':30s} {'pick':12s} {'눕힘':4s} {'개구':>4s} {'홀':>3s} {'수직관통':>6s} {'수직막힘':>6s} {'측면':>4s} | {'드릴대상 관통/막힘/측면':>20s} | 판정"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['part']:30s} {r['pickability'][:12]:12s} {r['lying_axis']:4s} {r['openings']:4d} {r['holes']:3d} "
              f"{r['vert_through']:6d} {r['vert_blind']:6d} {r['side']:4d} | "
              f"{r['drill_vert_through']:6d}/{r['drill_vert_blind']:3d}/{r['drill_side']:3d}         | {r['verdict']}")
    md = os.path.join(args.out, "hole_axis_survey.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write("| 부품 | pickability | 눕힘축 | 개구 | 홀 | 수직관통 | 수직막힘 | 측면 | 드릴대상 관통/막힘/측면 | 판정 |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| `{r['part']}` | {r['pickability']} | {r['lying_axis']}({r['lying_height']:.1f}) | {r['openings']} | {r['holes']} | "
                    f"{r['vert_through']} | {r['vert_blind']} | {r['side']} | {r['drill_vert_through']}/{r['drill_vert_blind']}/{r['drill_side']} | {r['verdict']} |\n")
    print(f"\n→ {args.out}/hole_axis_survey.json · .md")


if __name__ == "__main__":
    main()
