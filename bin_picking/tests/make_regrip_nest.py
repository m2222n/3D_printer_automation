"""
리그립 네스트 STL 생성 — 부품 CAD 에서 "드릴 면이 위를 보는 자세로 서는 포켓" 을 뽑아 출력용 STL 을 만든다
=====================================================================================================

🎯 왜 있는가 (9/10 저녁 · 태민님 *"리그립 스테이션 지금 꼼꼼하게 진행하자"*)
  부품은 빈에 눕는다 ⇒ 측면 홀(드릴 대상 123개 중 50개 · 21종 중 15종)은 눕힌 채로 못 뚫는다.
  평평한 곳에 놓으면 다시 눕는다(안정 자세는 접촉 면적에 비례) ⇒ **세운 자세를 붙잡아 줄 형상(네스트)** 이 필요하다.
  구동부·I/O 0 인 **자기정렬 포켓** 이 1순위(9/8 판정) ⇒ 우리 Form 4 로 레진 출력해 시제품을 만든다.

원리
  ① 9/3 홀 축 조사(`hole_axis_survey.json`)에서 **드릴 대상(ø≤5.5) 측면 홀의 축**을 읽는다 → 그 축을 +Z(위)로 세운다
  ② 세운 자세의 **바닥 실루엣**(XY 투영) + 여유(clearance) = 포켓
  ③ 네스트 = 바닥판 + 포켓 벽(딱 맞는 구간) + **깔때기 구간**(위쪽 여유 ↑ = 로봇이 조금 어긋나 놓아도 미끄러져 들어간다)
  ④ 포켓 깊이 < 부품 높이 ⇒ 위로 **노출된 구간을 그리퍼가 다시 문다**

🚨 정직하게 — 이 스크립트가 못 하는 것
  - 조우 두께·조우가 포켓 벽과 간섭하는지는 [미확인](제조사 문의 4번) ⇒ 노출 높이를 넉넉히(기본 10mm 이상) 둔다
  - 그리퍼 파지 설정위치가 40mm(9/9 실물)라 **노출 구간의 폭이 40mm 미만이면 GUI 재설정 전엔 못 문다** ⇒ 결과에 경고를 찍는다
  - 레진 수축·프린터 오차(±0.1~0.2mm)는 clearance 0.5 로 흡수한다고 가정 [실측필요]
  - 부품이 포켓 안에서 **혼자 서는지**(무게중심이 포켓 깊이 안에 있나)는 계산으로 경고만 하고 실물이 답이다

사용
  python bin_picking/tests/make_regrip_nest.py --part 15_roller_bracket --out /data/jtm/handover_0908/regrip_nest_v1
  python bin_picking/tests/make_regrip_nest.py --part 16_cam_f_bracket  --out /data/jtm/handover_0908/regrip_nest_v1
  옵션 = --clearance 0.5 --pocket-depth 7 --base 4 --wall 8 --funnel-h 3 --funnel-extra 2 --up-axis X|Y|Z(자동)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CAD_DIR = REPO / "bin_picking" / "models" / "cad"
SURVEY = Path("/data/jtm/hole_axis_survey_0903/hole_axis_survey.json")
DRILL_DIA_MAX = 5.5          # 9/3 조사와 같은 기준 = 드릴 대상 지름
GRIP_STOP_MM = 40.0          # 9/9 실물: 파지2 빈손 정지 ≈ 40mm ⇒ 이보다 좁은 것은 GUI 재설정 전 못 문다

AXIS = {"X": np.array([1.0, 0, 0]), "Y": np.array([0, 1.0, 0]), "Z": np.array([0, 0, 1.0])}


def load_survey(part: str) -> dict | None:
    if not SURVEY.exists():
        return None
    d = json.loads(SURVEY.read_text(encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("parts") or d.get("results") or list(d.values())
    for it in items:
        if isinstance(it, dict) and it.get("part") == part:
            return it
    return None


def choose_up_axis(survey: dict | None, forced: str | None) -> tuple[str, list[dict]]:
    """드릴 대상 측면 홀의 축 → 위로 세울 축. 축이 둘이면 첫 번째를 쓰고 경고."""
    if forced:
        return forced, []
    if not survey:
        raise SystemExit("홀 축 조사가 없다 — --up-axis 를 직접 준다")
    side = [h for h in survey.get("holes_detail", []) if h.get("d", 99) <= DRILL_DIA_MAX and abs(h.get("vs_up", 1)) < 0.5]
    if not side:
        raise SystemExit(f"{survey['part']}: 드릴 대상 측면 홀이 없다(리그립 불필요) — 눕힌 채로 뚫는다")
    axes = sorted({h["axis"] for h in side})
    if len(axes) > 1:
        print(f"⚠️ 측면 홀 축이 둘({axes}) — 자세가 2개 필요하다. 이 실행은 {axes[0]} 축 네스트만 만든다(다른 축은 --up-axis {axes[1]})")
    return axes[0], side


def stand_part(mesh, up_axis: str):
    """부품 축 up_axis 를 +Z 로 세우고, XY 중심을 원점·바닥을 z=0 에 놓는다. 반환 = (세운 mesh, 4x4 변환)"""
    import trimesh
    T = trimesh.geometry.align_vectors(AXIS[up_axis], AXIS["Z"])
    m = mesh.copy()
    m.apply_transform(T)
    lo, hi = m.bounds
    shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])
    Tt = np.eye(4); Tt[:3, 3] = shift
    m.apply_transform(Tt)
    return m, Tt @ T


def footprint_polygon(mesh):
    """세운 부품의 바닥 실루엣(XY 투영) — 가장 큰 폴리곤(구멍은 채운다: 포켓은 외곽만 필요)"""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    p2 = mesh.projected(normal=[0, 0, 1])
    polys = list(p2.polygons_full)
    if not polys:
        raise SystemExit("투영 폴리곤이 없다")
    u = unary_union([Polygon(p.exterior.coords) for p in polys])
    if u.geom_type == "MultiPolygon":
        u = max(u.geoms, key=lambda g: g.area)
    return Polygon(u.exterior.coords)


def rect(cx, cy, w, h):
    from shapely.geometry import box
    return box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def build_nest(fp, *, clearance, pocket_depth, base, wall, funnel_h, funnel_extra):
    """바닥판 + 딱 맞는 벽 + 깔때기 벽. 세 덩어리를 이어 붙인다(슬라이서가 합친다)."""
    import trimesh
    from trimesh.creation import extrude_polygon

    tight = fp.buffer(clearance, join_style=2)                  # 모서리 유지(mitre)
    funnel = fp.buffer(clearance + funnel_extra, join_style=2)
    minx, miny, maxx, maxy = funnel.bounds
    outer = rect((minx + maxx) / 2, (miny + maxy) / 2, (maxx - minx) + 2 * wall, (maxy - miny) + 2 * wall)

    floor = extrude_polygon(outer, base)
    ring_tight = extrude_polygon(outer.difference(tight), pocket_depth)
    ring_tight.apply_translation([0, 0, base])
    ring_funnel = extrude_polygon(outer.difference(funnel), funnel_h)
    ring_funnel.apply_translation([0, 0, base + pocket_depth])
    nest = trimesh.util.concatenate([floor, ring_tight, ring_funnel])
    return nest, tight, funnel, outer


def main() -> int:
    ap = argparse.ArgumentParser(description="리그립 네스트 STL 생성")
    ap.add_argument("--part", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--up-axis", choices=("X", "Y", "Z"), default=None, help="비우면 홀 축 조사에서 자동")
    ap.add_argument("--clearance", type=float, default=0.5, help="포켓 여유 [mm/변] — 레진 오차 흡수")
    ap.add_argument("--pocket-depth", type=float, default=None, help="딱 맞는 벽 높이 [mm] (기본 = 부품 높이의 40%%)")
    ap.add_argument("--base", type=float, default=4.0)
    ap.add_argument("--wall", type=float, default=8.0)
    ap.add_argument("--funnel-h", type=float, default=3.0)
    ap.add_argument("--funnel-extra", type=float, default=2.0)
    a = ap.parse_args()

    import trimesh
    stl = CAD_DIR / f"{a.part}.stl"
    if not stl.exists():
        raise SystemExit(f"STL 없음: {stl}")
    mesh = trimesh.load(stl, force="mesh")
    survey = load_survey(a.part)
    up, side_holes = choose_up_axis(survey, a.up_axis)

    part, T = stand_part(mesh, up)
    H = float(part.extents[2])
    pocket_depth = a.pocket_depth if a.pocket_depth is not None else round(H * 0.4, 1)
    exposed = H - pocket_depth
    fp = footprint_polygon(part)
    nest, tight, funnel, outer = build_nest(fp, clearance=a.clearance, pocket_depth=pocket_depth, base=a.base,
                                            wall=a.wall, funnel_h=a.funnel_h, funnel_extra=a.funnel_extra)

    # 부품을 포켓 바닥에 올린 검사용 메시(자리 확인 · 슬라이서에서 겹쳐 보기)
    part_in = part.copy(); part_in.apply_translation([0, 0, a.base])

    # 노출 구간에서 그리퍼가 물 수 있는 폭(XY bbox) — 40mm 경계 경고
    top_slice = part.slice_plane([0, 0, pocket_depth + 0.5], [0, 0, 1])
    ex = top_slice.extents if top_slice is not None and len(top_slice.vertices) else part.extents
    grip_x, grip_y = float(ex[0]), float(ex[1])

    # 무게중심 높이 vs 포켓 깊이 — 낮을수록 혼자 선다
    com_z = float(part.center_mass[2]) if part.is_watertight else float(part.centroid[2])

    # 드릴 홀 위치를 네스트 좌표(포켓 바닥 z=base)로 변환 — 로봇 드릴 접근 좌표의 근거
    holes_nest = []
    for h in side_holes:
        c = np.array(h["center"] + [1.0]); cn = (T @ c)[:3] + np.array([0, 0, a.base])
        holes_nest.append({"d": h["d"], "through": h["through"], "xyz_nest_mm": [round(float(v), 2) for v in cn]})

    a.out.mkdir(parents=True, exist_ok=True)
    stem = f"nest_{a.part}_{up}up"
    nest.export(a.out / f"{stem}.stl")
    part_in.export(a.out / f"{stem}_part_check.stl")
    spec = {
        "part": a.part, "up_axis": up, "part_extents_standing_mm": [round(float(v), 2) for v in part.extents],
        "pocket_footprint_bbox_mm": [round(float(v), 2) for v in tight.bounds],
        "clearance_mm": a.clearance, "pocket_depth_mm": pocket_depth, "funnel_h_mm": a.funnel_h, "funnel_extra_mm": a.funnel_extra,
        "base_mm": a.base, "wall_mm": a.wall, "nest_outer_mm": [round(float(v), 2) for v in outer.bounds],
        "nest_total_height_mm": round(a.base + pocket_depth + a.funnel_h, 2),
        "exposed_height_mm": round(exposed, 2), "grip_width_exposed_xy_mm": [round(grip_x, 2), round(grip_y, 2)],
        "part_com_height_mm": round(com_z, 2),
        "drill_holes_in_nest_frame": holes_nest,
        "transform_part_to_nest": [[round(float(v), 6) for v in row] for row in T],
        "warnings": [],
    }
    if exposed < 10:
        spec["warnings"].append(f"노출 높이 {exposed:.1f}mm < 10 — 조우가 물 구간이 좁다. pocket_depth 를 줄일 것")
    if max(grip_x, grip_y) < GRIP_STOP_MM:
        spec["warnings"].append(f"노출 구간 폭 {grip_x:.1f}×{grip_y:.1f}mm 둘 다 < {GRIP_STOP_MM} — 9/9 실물 파지 설정위치(≈40) 때문에 GUI 재설정 전엔 못 문다")
    if com_z > pocket_depth:
        spec["warnings"].append(f"무게중심 높이 {com_z:.1f} > 포켓 깊이 {pocket_depth} — 기울면 넘어질 수 있다. 실물로 확인")
    (a.out / f"{stem}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"✅ {a.part} · 세운 축 {up}→Z · 부품 {spec['part_extents_standing_mm']} mm · 포켓 깊이 {pocket_depth} · 노출 {exposed:.1f}")
    print(f"   네스트 외형 {spec['nest_outer_mm']} · 총 높이 {spec['nest_total_height_mm']} · 노출 구간 폭 {grip_x:.1f}×{grip_y:.1f}")
    print(f"   드릴 홀(네스트 좌표) = {[h['xyz_nest_mm'] for h in holes_nest]}")
    for w in spec["warnings"]:
        print(f"   ⚠️ {w}")
    print(f"   → {a.out / (stem + '.stl')}  (+ _part_check.stl · .json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
