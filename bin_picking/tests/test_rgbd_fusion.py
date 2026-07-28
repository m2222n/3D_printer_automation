"""
rgbd_fusion 정합 테스트 — 카메라 없이 기하 검증
=================================================

핵심 검증 방식: **정답을 아는 합성 장면**을 만들어 왕복시킨다.
  알려진 3D 점 → Blaze 픽셀에 depth로 심음 → align_depth_to_ace2
  → ACE2 픽셀에서 되읽음 → 원래 점과 일치하는가?

이렇게 하면 실카메라 없이도 부호 실수·역변환 방향 반대·단위 혼동 같은
"조용히 틀리는" 결함을 잡을 수 있다. (7/27 Blaze intrinsic 사례처럼
에러 없이 틀린 값이 나오는 게 가장 위험)

    python bin_picking/tests/test_rgbd_fusion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from bin_picking.src.acquisition.extrinsic_io import Extrinsic  # noqa: E402
from bin_picking.src.acquisition.rgbd_fusion import (  # noqa: E402
    NO_DEPTH,
    FusionError,
    Intrinsics,
    align_depth_to_ace2,
    coverage_report,
    depth_to_points_mm,
    project_points,
    transform_points,
)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))


# 실제 값에 가깝게: Blaze 848×480 저해상 광각 / ACE2 5MP 협각(8mm, 실측 캘리브값)
BLAZE = Intrinsics(fx=420.0, fy=420.0, cx=424.0, cy=240.0, width=848, height=480)
ACE2 = Intrinsics(fx=2929.6, fy=2929.6, cx=1233.7, cy=1024.0, width=2464, height=2056)


def make_extrinsic(tx_mm=32.0, ty_mm=0.0, tz_mm=0.0, yaw_deg=0.0) -> Extrinsic:
    """ACE2→Blaze 변환. 기본은 x축 32mm 옆에 나란히(실제 브래킷과 유사)."""
    th = np.deg2rad(yaw_deg)
    R = np.array([[np.cos(th), 0, np.sin(th)], [0, 1, 0], [-np.sin(th), 0, np.cos(th)]])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [tx_mm / 1000.0, ty_mm / 1000.0, tz_mm / 1000.0]  # m
    return Extrinsic(T_m=T, baseline_mm=float(np.linalg.norm([tx_mm, ty_mm, tz_mm])),
                     spread_mm=1.0, n_frames=6, source=Path("<test>"))


def blaze_depth_with_point(p_blaze_mm: np.ndarray) -> np.ndarray:
    """Blaze 좌표계 3D 점 하나를 Blaze depth 이미지에 심는다."""
    uv, z = project_points(p_blaze_mm[None, :], BLAZE)
    assert uv.shape[0] == 1, "테스트 점이 카메라 뒤에 있음"
    u, v = int(round(uv[0, 0])), int(round(uv[0, 1]))
    depth = np.zeros((BLAZE.height, BLAZE.width), dtype=np.uint16)
    depth[v, u] = int(round(z[0]))
    return depth


print("=" * 60)
print("rgbd_fusion 정합 테스트")
print("=" * 60)

# ---------------------------------------------------------------
print("\n[역투영/투영 왕복]")
pts = np.array([[10.0, -20.0, 700.0], [0.0, 0.0, 500.0], [-50.0, 30.0, 900.0]])
uv, z = project_points(pts, BLAZE)
back = np.stack([(uv[:, 0] - BLAZE.cx) * z / BLAZE.fx,
                 (uv[:, 1] - BLAZE.cy) * z / BLAZE.fy, z], axis=1)
err = float(np.abs(back - pts).max())
check("투영→역투영 왕복 일치", err < 1e-9, f"오차 {err:.1e} mm")

# ---------------------------------------------------------------
print("\n[정렬: 알려진 점이 ACE2의 옳은 픽셀에 오는가]")
# ACE2 좌표계에서 정면 700mm 앞의 점
p_ace2 = np.array([0.0, 0.0, 700.0])
ext = make_extrinsic(tx_mm=32.0)
# ACE2→Blaze로 옮겨 Blaze depth에 심는다
p_blaze = transform_points(p_ace2[None, :], ext.T_mm)[0]
depth = blaze_depth_with_point(p_blaze)

aligned = align_depth_to_ace2(
    depth, (ACE2.height, ACE2.width),
    extrinsic=ext, ace2_intr=ACE2, blaze_intr=BLAZE, dilate=0,
)
vs, us = np.nonzero(aligned > NO_DEPTH)
check("정렬 결과에 점이 1개 남음", len(vs) == 1, f"{len(vs)}개")
if len(vs) == 1:
    # 기대 픽셀 = ACE2 intrinsic으로 직접 투영한 위치
    uv_exp, z_exp = project_points(p_ace2[None, :], ACE2)
    du = abs(us[0] - uv_exp[0, 0])
    dv = abs(vs[0] - uv_exp[0, 1])
    # ⭐ 허용오차 2px의 근거(실측 아님, 기하 계산):
    #   테스트가 점을 Blaze **정수 픽셀**에 심으므로 최대 0.5px 양자화가 생기고,
    #   ACE2 초점거리가 Blaze의 약 7배(2929.6/420)라 그 오차가 ACE2 격자에서
    #   ~3.5px까지 증폭될 수 있다. 여기선 실제 0.2px→1.4px.
    #   ⚠️ 이건 코드 결함이 아니라 **Blaze 저해상도가 만드는 물리적 정밀도 한계**다.
    #   현장 함의: 정합 정밀도는 Blaze 해상도에 묶이며, 부품 중심 z를 뽑을 때
    #   단일 픽셀이 아니라 영역 median을 써야 하는 이유이기도 하다.
    check("정렬 픽셀 위치 정확(양자화 허용 2px)", du <= 2.0 and dv <= 2.0,
          f"오차 ({du:.2f}, {dv:.2f}) px")
    dz = abs(float(aligned[vs[0], us[0]]) - z_exp[0])
    check("정렬 z값 정확", dz < 1.0, f"오차 {dz:.3f} mm ({aligned[vs[0], us[0]]:.1f} vs {z_exp[0]:.1f})")

# ---------------------------------------------------------------
print("\n[역변환 방향이 반대면 잡히는가 — 회귀 방지]")
# extrinsic을 일부러 뒤집어 쓰면 결과가 달라져야 한다(= 방향이 의미를 가짐).
ext_big = make_extrinsic(tx_mm=300.0)  # 크게 벌려 차이를 뚜렷하게
p_b = transform_points(p_ace2[None, :], ext_big.T_mm)[0]
d_big = blaze_depth_with_point(p_b)
a_ok = align_depth_to_ace2(d_big, (ACE2.height, ACE2.width),
                           extrinsic=ext_big, ace2_intr=ACE2, blaze_intr=BLAZE, dilate=0)
# 방향을 뒤집은 가짜 extrinsic
T_flip = np.eye(4)
T_flip[:3, 3] = -ext_big.T_m[:3, 3]
ext_flip = Extrinsic(T_m=T_flip, baseline_mm=ext_big.baseline_mm, spread_mm=1.0,
                     n_frames=6, source=Path("<flip>"))
a_flip = align_depth_to_ace2(d_big, (ACE2.height, ACE2.width),
                             extrinsic=ext_flip, ace2_intr=ACE2, blaze_intr=BLAZE, dilate=0)
v1, u1 = np.nonzero(a_ok > NO_DEPTH)
v2, u2 = np.nonzero(a_flip > NO_DEPTH)
differs = (len(v1) != len(v2)) or (len(v1) == 1 and len(v2) == 1 and abs(int(u1[0]) - int(u2[0])) > 10)
check("extrinsic 방향이 결과에 실제로 반영됨", differs,
      "뒤집으면 위치가 달라짐" if differs else "🚨 방향 무시됨 = 변환 미적용 의심")

# ---------------------------------------------------------------
print("\n[z-buffer: 앞 물체가 뒤 물체를 가리는가]")
# ⚠️ 주의: "ACE2 같은 광선 위 두 점"으로는 z-buffer를 시험할 수 없다.
#   baseline 32mm 때문에 두 점이 Blaze에서는 **서로 다른 픽셀**로 보이고(시차),
#   되투영하면 ACE2에서도 양자화 탓에 2px쯤 어긋나 충돌이 안 난다.
#   → 충돌을 확실히 만들려면 **Blaze에서 같은 방향**에 놓아야 한다.
#   (extrinsic을 항등으로 두면 두 좌표계가 일치해 광선이 공유된다)
ext_id = make_extrinsic(tx_mm=0.0)
near, far = np.array([0.0, 0.0, 400.0]), np.array([0.0, 0.0, 900.0])
d2 = np.zeros((BLAZE.height, BLAZE.width), dtype=np.uint16)
for p in (near, far):
    uvb, zb = project_points(p[None, :], BLAZE)
    d2[int(round(uvb[0, 1])), int(round(uvb[0, 0]))] = int(round(zb[0]))
# 같은 Blaze 픽셀에 둘 다 심으면 하나만 남으므로, 서로 다른 픽셀에 심되
# ACE2 투영 시 같은 픽셀로 모이도록 배치한다.
d2[:] = 0
uv_n, z_n = project_points(near[None, :], BLAZE)
un_b, vn_b = int(round(uv_n[0, 0])), int(round(uv_n[0, 1]))
d2[vn_b, un_b] = 400
# 이웃 픽셀에 먼 점을 심고, 그 점이 ACE2에서 같은 픽셀로 가도록 z를 맞춘다.
# 이웃 픽셀 방향 (u+1)에서 z=900이면 ACE2 투영 위치가 near와 겹치는지 계산으로 확인.
d2[vn_b, un_b + 1] = 900
a2 = align_depth_to_ace2(d2, (ACE2.height, ACE2.width),
                         extrinsic=ext_id, ace2_intr=ACE2, blaze_intr=BLAZE, dilate=0)
vs2, us2 = np.nonzero(a2 > NO_DEPTH)
zvals = a2[vs2, us2]
# 핵심 성질: 결과 어디에도 "가까운 점이 있던 자리"가 먼 값으로 바뀌면 안 된다.
uv_ne, _ = project_points(near[None, :], ACE2)
un_a, vn_a = int(round(uv_ne[0, 0])), int(round(uv_ne[0, 1]))
z_at_near = float(a2[vn_a, un_a])
check("가까운 점 자리가 먼 값으로 덮이지 않음", abs(z_at_near - 400.0) < 1.0,
      f"z={z_at_near:.1f} mm (기대 400)")

# z-buffer 자체를 직접 검증: 같은 픽셀에 강제로 여러 점을 모아 최솟값이 남는지
same = np.zeros((BLAZE.height, BLAZE.width), dtype=np.uint16)
cu, cv = int(BLAZE.cx), int(BLAZE.cy)
# 중심 주변 3×3에 먼 값들, 정중앙에 가까운 값 → ACE2에선 거의 한 점으로 모임
for dy in (-1, 0, 1):
    for dx in (-1, 0, 1):
        same[cv + dy, cu + dx] = 900
same[cv, cu] = 400
a5 = align_depth_to_ace2(same, (ACE2.height, ACE2.width), extrinsic=ext_id,
                         ace2_intr=ACE2, blaze_intr=BLAZE, dilate=0)
zs5 = a5[a5 > NO_DEPTH]
uv_c, _ = project_points(np.array([[0.0, 0.0, 400.0]]), ACE2)
zc = float(a5[int(round(uv_c[0, 1])), int(round(uv_c[0, 0]))])
check("중앙 픽셀에 가까운 값(400) 유지", abs(zc - 400.0) < 1.0, f"z={zc:.1f} mm")

# ---------------------------------------------------------------
print("\n[구멍 메우기가 가까운 값을 쓰는가]")
# 부품(가까움) 옆에 배경(멂)이 있을 때, 구멍이 배경값으로 번지면 안 됨
small = np.zeros((5, 5), dtype=np.float32)
small[2, 1] = 400.0   # 부품
small[2, 3] = 900.0   # 배경
from bin_picking.src.acquisition.rgbd_fusion import _fill_holes_nearest  # noqa: E402
filled = _fill_holes_nearest(small, radius=1)
check("구멍은 가까운(작은) 값으로 채워짐", filled[2, 2] == 400.0,
      f"중간 픽셀 {filled[2, 2]:.0f} mm (400=부품쪽 / 900=배경쪽)")
check("원래 유효값은 안 덮어씀", filled[2, 3] == 900.0, f"{filled[2, 3]:.0f} mm")

# ---------------------------------------------------------------
print("\n[해상도 불일치 차단]")
try:
    align_depth_to_ace2(depth, (480, 640), extrinsic=ext, ace2_intr=ACE2, blaze_intr=BLAZE)
    check("intrinsic-격자 불일치 차단", False, "예외 없이 통과함")
except FusionError as e:
    check("intrinsic-격자 불일치 차단", "scaled" in str(e), "scaled() 안내 포함")

# scaled()로 맞추면 통과해야
half = ACE2.scaled(0.5, 0.5)
try:
    a3 = align_depth_to_ace2(depth, (half.height, half.width), extrinsic=ext,
                             ace2_intr=half, blaze_intr=BLAZE, dilate=0)
    check("scaled()로 맞추면 정상 동작", a3.shape == (half.height, half.width),
          f"shape {a3.shape}")
except Exception as e:
    check("scaled()로 맞추면 정상 동작", False, f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------
print("\n[비정상 intrinsic 거부 — 7/27 Blaze 사례]")
import json, tempfile  # noqa: E402
from bin_picking.src.acquisition.rgbd_fusion import _load_intrinsics_json  # noqa: E402
with tempfile.TemporaryDirectory() as td:
    bad = Path(td) / "bad.json"
    bad.write_text(json.dumps({"camera_matrix": [[553, 0, 424], [0, 188, 240], [0, 0, 1]],
                               "dist_coeffs": [0, 0, 0, 0, 0]}))
    try:
        _load_intrinsics_json(bad, "Blaze")
        check("fx/fy 비율 이상 거부", False, "통과해버림")
    except FusionError as e:
        check("fx/fy 비율 이상 거부", "2.94" in str(e), "비율 2.94 지적")

# ---------------------------------------------------------------
print("\n[빈 입력·전부 무효 depth]")
empty = np.zeros((BLAZE.height, BLAZE.width), dtype=np.uint16)
a4 = align_depth_to_ace2(empty, (ACE2.height, ACE2.width), extrinsic=ext,
                         ace2_intr=ACE2, blaze_intr=BLAZE)
check("전부 0인 depth → 빈 결과, 예외 없음", a4.shape == (ACE2.height, ACE2.width)
      and not (a4 > NO_DEPTH).any())

noise = np.full((BLAZE.height, BLAZE.width), 60000, dtype=np.uint16)  # 범위 밖
pts_n = depth_to_points_mm(noise, BLAZE)
check("유효범위 밖 depth는 버려짐", pts_n.shape[0] == 0, f"{pts_n.shape[0]}개 남음")

# ---------------------------------------------------------------
print("\n[커버리지 리포트]")
rep = coverage_report(a4)
check("빈 결과에 경고 표시", "⚠️" in rep, rep.splitlines()[0])

print("\n" + "=" * 60)
if FAIL:
    print(f"❌ 실패 {len(FAIL)}건: {', '.join(FAIL)}")
    sys.exit(1)
print(f"✅ 전부 통과 ({len(PASS)}/{len(PASS)})")
