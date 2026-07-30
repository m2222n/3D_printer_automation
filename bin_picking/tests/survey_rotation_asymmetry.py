#!/usr/bin/env python3
"""27종 회전 비대칭 조사 — `angle` 산출 작업의 실제 가치를 숫자로 판정.

⭐ 왜 이 조사부터 하나
----------------------
`angle`(회전각) 산출은 재택에서 가능한 작업이지만 **북극성 기준 3순위**다
(1=실환경 인식 검증, 2=hand-eye). 그래서 착수 전에 **실제로 필요한지**를 먼저 센다.

  - 부품이 대부분 원형·정사각형이면 → 각도 없이도 집힘 → **작업 가치 낮음**
  - 길쭉한 부품이 많으면 → **각도 없이는 못 집음 = 필수**

7/29 대칭쌍 분석에서 얻은 방식과 같다: 낙관/비관 가설을 세우지 말고 **숫자를 먼저 본다.**

판정 기준 = "로봇이 각도 없이 집을 수 있나"
--------------------------------------------
평면(top-down) 파지를 전제로, 부품을 **위에서 본 실루엣**의 종횡비를 본다.
그리퍼는 두 손가락이 마주보며 닫히므로, 실루엣이 길쭉하면 **긴 축에 수직으로**
접근해야 한다 = 각도 필수.

  aspect = 긴 변 / 짧은 변 (위에서 본 OBB)

  aspect < 1.15  → 사실상 정사각/원형. 어느 각도로 접근해도 비슷 → 각도 불필요
  1.15 ~ 1.5     → 애매. 그리퍼 여유(stroke)에 따라 갈림
  > 1.5          → 🔴 길쭉함. 각도 틀리면 그리퍼가 부품을 가로질러 내려옴

⚠️ 한계 (정직하게)
  - `grasp_database.yaml:22-23`이 명시한 대로 이 값들은 **STL 기준**이고 실제 파지는
    로봇 티칭 후 실측 교정이 필요하다.
  - 안정 자세(stable pose)에 따라 위에서 본 실루엣이 달라진다. 여기서는 **STL 원본
    방향의 z축 투영**을 쓴다 = 근사. 정밀히 하려면 `stable_poses_all29.yaml` 연동 필요.
  - 그래서 결과는 "정확한 답"이 아니라 **작업 착수 판단용 규모 추정**이다.

실행: .venv/binpick/bin/python bin_picking/tests/survey_rotation_asymmetry.py
"""
from __future__ import annotations
import glob
import json
import os
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
CAD_DIR = ROOT / "models" / "cad"
REAL_DIR = "/data/jtm/synth_out/6elements_100"

# 판정 임계 (위 주석 근거)
T_SQUARE = 1.15
T_ELONGATED = 1.5


def detected_labels() -> dict:
    """실측 100장에 실제로 나온 종류만 대상으로 한다(46개 STL 전체가 아님)."""
    cnt = {}
    for f in glob.glob(f"{REAL_DIR}/*.json"):
        for d in json.load(open(f))["detections"]:
            cnt[d["label"]] = cnt.get(d["label"], 0) + 1
    return cnt


def find_stl(label: str) -> Path | None:
    """라벨 → STL 경로. 라벨과 파일명이 완전히 일치하지 않는 경우가 있어 보정."""
    cand = CAD_DIR / f"{label}.stl"
    if cand.exists():
        return cand
    # cad_id 접미사(__해시)나 _l/_r 변형 대응
    base = label.split("__")[0]
    for p in CAD_DIR.glob("*.stl"):
        if p.stem == base:
            return p
    # 느슨한 매칭 (13_x2_bcf8ccb4 → 13_x2 등)
    for p in CAD_DIR.glob("*.stl"):
        if base.startswith(p.stem) or p.stem.startswith(base):
            return p
    return None


def top_view_aspect(mesh: trimesh.Trimesh) -> tuple[float, float, float, float]:
    """위(z축)에서 본 실루엣의 OBB 종횡비.

    ⭐ 축정렬 bbox가 아니라 **최소 회전 사각형**을 쓴다. 부품이 STL 안에서 비스듬히
       놓여 있으면 축정렬 bbox는 실제보다 정사각형에 가깝게 나와 판정을 흐린다
       (7/29에 `edge`가 축정렬이라 각도를 못 낸 것과 같은 함정).
    """
    pts = mesh.vertices[:, :2]  # z축 투영 = 위에서 본 모양
    # 2D 최소 회전 사각형: PCA로 주축을 찾아 그 축에서 폭을 재는 방식
    c = pts.mean(axis=0)
    q = pts - c
    cov = np.cov(q.T)
    w, v = np.linalg.eigh(cov)
    proj = q @ v                      # 주축 정렬 좌표계로 회전
    ext = proj.max(axis=0) - proj.min(axis=0)
    long_mm, short_mm = float(max(ext)), float(min(ext))
    aspect = long_mm / max(short_mm, 1e-6)
    height = float(mesh.vertices[:, 2].max() - mesh.vertices[:, 2].min())
    return aspect, long_mm, short_mm, height


def main():
    labels = detected_labels()
    print(f"실측 100장 등장 종류: {len(labels)}종\n")

    rows, missing = [], []
    for label in sorted(labels):
        stl = find_stl(label)
        if stl is None:
            missing.append(label)
            continue
        try:
            m = trimesh.load(stl, force="mesh")
            aspect, lo, sh, h = top_view_aspect(m)
            rows.append({
                "label": label, "stl": stl.name, "n": labels[label],
                "aspect": aspect, "long_mm": lo, "short_mm": sh, "h_mm": h,
            })
        except Exception as e:
            print(f"  ⚠️ {label}: 로드 실패 {type(e).__name__}")

    rows.sort(key=lambda r: -r["aspect"])

    print(f"{'부품':<32} {'검출':>4} {'종횡비':>7} {'긴변':>7} {'짧은변':>7}  판정")
    print("-" * 84)
    n_elong = n_mid = n_square = 0
    for r in rows:
        a = r["aspect"]
        if a > T_ELONGATED:
            verdict = "🔴 각도 필수"; n_elong += 1
        elif a > T_SQUARE:
            verdict = "🟡 애매"; n_mid += 1
        else:
            verdict = "🟢 각도 불필요"; n_square += 1
        print(f"{r['label']:<32} {r['n']:>4} {a:>7.2f} {r['long_mm']:>7.1f} "
              f"{r['short_mm']:>7.1f}  {verdict}")

    total = len(rows)
    print("-" * 84)
    print(f"\n=== 집계 ({total}종 중) ===")
    print(f"  🔴 각도 필수  (>{T_ELONGATED})     : {n_elong:2d}종  ({100*n_elong/max(total,1):.0f}%)")
    print(f"  🟡 애매      ({T_SQUARE}~{T_ELONGATED})  : {n_mid:2d}종  ({100*n_mid/max(total,1):.0f}%)")
    print(f"  🟢 각도 불필요(<{T_SQUARE})      : {n_square:2d}종  ({100*n_square/max(total,1):.0f}%)")

    # 검출 건수 가중 = 실제로 로봇이 마주칠 빈도
    tot_n = sum(r["n"] for r in rows)
    elong_n = sum(r["n"] for r in rows if r["aspect"] > T_ELONGATED)
    print(f"\n  검출 건수 기준: 길쭉한 부품이 {elong_n}/{tot_n}건 "
          f"({100*elong_n/max(tot_n,1):.0f}%)")

    print("\n=== 판단 ===")
    pct = 100 * n_elong / max(total, 1)
    if pct >= 40:
        print(f"  🔴 각도 산출 = **필수**. {n_elong}종({pct:.0f}%)이 각도 없이는 파지 불가.")
    elif pct >= 15:
        print(f"  🟡 각도 산출 = **필요하나 부분적**. {n_elong}종({pct:.0f}%)만 해당.")
        print("     → 대칭 부품부터 먼저 E2E를 닫고, 각도는 그 다음에 얹는 전략이 가능.")
    else:
        print(f"  🟢 각도 산출 = **후순위 가능**. 길쭉한 부품 {n_elong}종({pct:.0f}%)뿐.")

    if missing:
        print(f"\n⚠️ STL 못 찾음 {len(missing)}종: {', '.join(missing[:8])}")
        print("   (라벨↔파일명 불일치. 판정에서 제외됨 = 위 집계는 이만큼 불완전)")


if __name__ == "__main__":
    main()
