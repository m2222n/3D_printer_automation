"""
Open3D Multi-Scale ICP 튜토리얼 — 빈피킹 Coarse-to-Fine 정합
=============================================================

단일 스케일 ICP의 한계:
  - 초기 위치가 멀면 로컬 최적해에 빠짐 (수렴 실패)
  - 빈피킹에서 부품은 임의 자세 → 초기 정합 후에도 오차가 클 수 있음
  - 세밀한 threshold로 바로 시작하면 대응점을 못 찾아 발산

Multi-Scale (Coarse-to-Fine) ICP:
  1. Coarse (4×voxel): 큰 threshold, 거친 다운샘플 → 대략적 정렬
  2. Medium (2×voxel): 중간 threshold → 중간 수준 정렬
  3. Fine   (1×voxel): 작은 threshold, 원본에 가까운 밀도 → 정밀 정합

장점:
  - 수렴 영역이 넓어 초기 오차에 강건
  - 각 단계에서 점진적으로 정밀도 향상
  - 빈피킹에서 RANSAC/FGR 초기 정합이 부정확해도 복구 가능

논문 리뷰 결정 파라미터:
  - voxel_size: 2mm (0.002m) — 실제 SLA 부품
  - ICP: Point-to-Plane + TukeyLoss (Robust kernel)
  - 데모에서는 voxel 5cm (실내 스캔 데이터)

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/05_multiscale_icp.py --no-vis
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser(description="Multi-Scale ICP 튜토리얼")
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 파라미터 설정
# ============================================================
# === 실제 빈피킹 (30종 SLA 부품) ===
# BASE_VOXEL = 0.002  # 2mm
# === 데모 데이터 (실내 스캔) ===
BASE_VOXEL = 0.05  # 5cm

# Multi-Scale 설정: 3단계 (coarse → medium → fine)
# 각 단계의 voxel 배수와 ICP max_correspondence_distance 배수
SCALES = [
    {"name": "Coarse", "voxel_mult": 4.0, "icp_dist_mult": 3.0, "max_iter": 50},
    {"name": "Medium", "voxel_mult": 2.0, "icp_dist_mult": 1.5, "max_iter": 30},
    {"name": "Fine",   "voxel_mult": 1.0, "icp_dist_mult": 0.5, "max_iter": 20},
]

NORMAL_RADIUS_MULT = 4.0  # 법선 추정 반경 = voxel × 4
NORMAL_MAX_NN = 30


def print_section(title: str):
    """섹션 제목 출력 헬퍼"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 샘플 데이터 로드
# ============================================================
print_section("Step 1: 샘플 데이터 로드")

demo_data = o3d.data.DemoICPPointClouds()
source_raw = o3d.io.read_point_cloud(demo_data.paths[0])
target_raw = o3d.io.read_point_cloud(demo_data.paths[1])

print(f"  Source: {len(source_raw.points):,} points")
print(f"  Target: {len(target_raw.points):,} points")
print(f"  Base voxel: {BASE_VOXEL*1000:.0f}mm (데모용)")


# ============================================================
# 2. 초기 정합 (RANSAC) — ICP의 시작점 확보
# ============================================================
print_section("Step 2: RANSAC 초기 정합 (ICP 시작점)")

# 전처리: 가장 거친 스케일로 다운샘플 + FPFH
coarse_voxel = BASE_VOXEL * SCALES[0]["voxel_mult"]
fpfh_radius = coarse_voxel * 5

source_init = source_raw.voxel_down_sample(coarse_voxel)
target_init = target_raw.voxel_down_sample(coarse_voxel)

source_init.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=coarse_voxel * NORMAL_RADIUS_MULT, max_nn=NORMAL_MAX_NN
    )
)
source_init.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

target_init.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=coarse_voxel * NORMAL_RADIUS_MULT, max_nn=NORMAL_MAX_NN
    )
)
target_init.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

source_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    source_init,
    o3d.geometry.KDTreeSearchParamHybrid(radius=fpfh_radius, max_nn=100),
)
target_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    target_init,
    o3d.geometry.KDTreeSearchParamHybrid(radius=fpfh_radius, max_nn=100),
)

print(f"  초기 전처리: voxel={coarse_voxel*1000:.0f}mm")
print(f"  Source: {len(source_init.points):,} pts, Target: {len(target_init.points):,} pts")

ransac_dist = coarse_voxel * 1.5
result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
    source_init, target_init,
    source_fpfh, target_fpfh,
    mutual_filter=True,
    max_correspondence_distance=ransac_dist,
    estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
    ransac_n=3,
    checkers=[
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(ransac_dist),
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
    ],
    criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(100000, 0.999),
)

print(f"\n  RANSAC 결과:")
print(f"    Fitness: {result_ransac.fitness:.4f}")
print(f"    RMSE: {result_ransac.inlier_rmse*1000:.2f}mm")
print(f"    대응점: {len(result_ransac.correspondence_set):,}")

init_transformation = result_ransac.transformation


# ============================================================
# 3. 단일 스케일 ICP (비교 기준선)
# ============================================================
print_section("Step 3: 단일 스케일 ICP (비교 기준선)")

# 단일 스케일: Fine 스케일(1×voxel)로 한 번만 ICP
single_voxel = BASE_VOXEL * 1.0  # Fine 스케일
single_icp_dist = BASE_VOXEL * 0.5

# 다운샘플 + 법선
source_single = source_raw.voxel_down_sample(single_voxel)
target_single = target_raw.voxel_down_sample(single_voxel)

source_single.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=single_voxel * NORMAL_RADIUS_MULT, max_nn=NORMAL_MAX_NN
    )
)
source_single.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

target_single.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=single_voxel * NORMAL_RADIUS_MULT, max_nn=NORMAL_MAX_NN
    )
)
target_single.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

print(f"  단일 스케일: voxel={single_voxel*1000:.0f}mm, "
      f"ICP dist={single_icp_dist*1000:.1f}mm")
print(f"  Source: {len(source_single.points):,} pts, "
      f"Target: {len(target_single.points):,} pts")

loss_single = o3d.pipelines.registration.TukeyLoss(k=single_icp_dist)
estimation_single = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss_single)

t0 = time.time()
result_single = o3d.pipelines.registration.registration_icp(
    source_single,
    target_single,
    max_correspondence_distance=single_icp_dist * 3,
    init=init_transformation,
    estimation_method=estimation_single,
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=100,  # 단일 스케일이므로 충분한 반복
    ),
)
time_single = time.time() - t0

print(f"\n  단일 스케일 ICP 결과:")
print(f"    소요 시간: {time_single:.3f}초")
print(f"    Fitness: {result_single.fitness:.4f}")
print(f"    RMSE: {result_single.inlier_rmse*1000:.2f}mm")
print(f"    대응점: {len(result_single.correspondence_set):,}")


# ============================================================
# 4. Multi-Scale ICP (Coarse-to-Fine)
# ============================================================
print_section("Step 4: Multi-Scale ICP (Coarse → Medium → Fine)")

print(f"\n  {'단계':<8} {'Voxel (mm)':<12} {'ICP dist (mm)':<14} {'Max iter':<10}")
print(f"  {'-'*44}")
for s in SCALES:
    v = BASE_VOXEL * s["voxel_mult"]
    d = BASE_VOXEL * s["icp_dist_mult"]
    print(f"  {s['name']:<8} {v*1000:<12.0f} {d*1000:<14.1f} {s['max_iter']:<10}")

current_transformation = init_transformation.copy()
multi_results = []  # 각 스케일별 결과 저장

t0_multi = time.time()

for i, scale in enumerate(SCALES):
    voxel = BASE_VOXEL * scale["voxel_mult"]
    icp_dist = BASE_VOXEL * scale["icp_dist_mult"]
    max_iter = scale["max_iter"]

    print(f"\n  --- {scale['name']} 단계 (voxel={voxel*1000:.0f}mm) ---")

    # 각 스케일에 맞게 다운샘플링
    source_scale = source_raw.voxel_down_sample(voxel)
    target_scale = target_raw.voxel_down_sample(voxel)

    # 법선 추정 (스케일에 맞는 반경)
    normal_radius = voxel * NORMAL_RADIUS_MULT
    source_scale.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=normal_radius, max_nn=NORMAL_MAX_NN
        )
    )
    source_scale.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

    target_scale.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=normal_radius, max_nn=NORMAL_MAX_NN
        )
    )
    target_scale.orient_normals_towards_camera_location(np.array([0.0, 0.0, 0.0]))

    print(f"    Source: {len(source_scale.points):,} pts, "
          f"Target: {len(target_scale.points):,} pts")

    # ICP Point-to-Plane + TukeyLoss (각 스케일별 threshold 조정)
    loss = o3d.pipelines.registration.TukeyLoss(k=icp_dist)
    estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)

    t_scale = time.time()
    result = o3d.pipelines.registration.registration_icp(
        source_scale,
        target_scale,
        max_correspondence_distance=icp_dist * 3,  # 탐색 범위는 threshold의 3배
        init=current_transformation,  # 이전 단계 결과를 초기값으로
        estimation_method=estimation,
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
            relative_fitness=1e-6,
            relative_rmse=1e-6,
            max_iteration=max_iter,
        ),
    )
    t_scale = time.time() - t_scale

    print(f"    Fitness: {result.fitness:.4f}")
    print(f"    RMSE: {result.inlier_rmse*1000:.2f}mm")
    print(f"    대응점: {len(result.correspondence_set):,}")
    print(f"    소요 시간: {t_scale:.3f}초")

    # 핵심: 이 단계의 결과를 다음 단계의 초기값으로 전달
    current_transformation = result.transformation.copy()

    multi_results.append({
        "name": scale["name"],
        "fitness": result.fitness,
        "rmse": result.inlier_rmse,
        "correspondences": len(result.correspondence_set),
        "time": t_scale,
        "transformation": result.transformation.copy(),
    })

time_multi = time.time() - t0_multi

print(f"\n  Multi-Scale 전체 소요 시간: {time_multi:.3f}초")


# ============================================================
# 5. 수렴 과정 비교 테이블
# ============================================================
print_section("Step 5: Multi-Scale 수렴 과정")

print(f"  {'단계':<10} {'Fitness':>10} {'RMSE (mm)':>12} {'대응점':>10} {'시간 (초)':>10}")
print(f"  {'-'*52}")

# 초기 상태 (RANSAC)
print(f"  {'RANSAC':<10} {result_ransac.fitness:>10.4f} "
      f"{result_ransac.inlier_rmse*1000:>12.2f} "
      f"{len(result_ransac.correspondence_set):>10,} {'':>10}")

# 각 Multi-Scale 단계
for r in multi_results:
    print(f"  {r['name']:<10} {r['fitness']:>10.4f} "
          f"{r['rmse']*1000:>12.2f} "
          f"{r['correspondences']:>10,} {r['time']:>10.3f}")

print(f"  {'-'*52}")

# 최종 비교: Multi-Scale vs Single-Scale
print(f"\n  {'방법':<20} {'Fitness':>10} {'RMSE (mm)':>12} {'시간 (초)':>10}")
print(f"  {'-'*52}")
print(f"  {'Single-Scale ICP':<20} {result_single.fitness:>10.4f} "
      f"{result_single.inlier_rmse*1000:>12.2f} {time_single:>10.3f}")
print(f"  {'Multi-Scale ICP':<20} {multi_results[-1]['fitness']:>10.4f} "
      f"{multi_results[-1]['rmse']*1000:>12.2f} {time_multi:>10.3f}")

# 정확도 비교
rmse_single = result_single.inlier_rmse * 1000
rmse_multi = multi_results[-1]["rmse"] * 1000
fit_single = result_single.fitness
fit_multi = multi_results[-1]["fitness"]

if rmse_multi < rmse_single:
    improvement = (rmse_single - rmse_multi) / rmse_single * 100
    print(f"\n  ✅ Multi-Scale이 RMSE {improvement:.1f}% 개선 ({rmse_single:.2f}mm → {rmse_multi:.2f}mm)")
elif rmse_multi > rmse_single:
    print(f"\n  ℹ️ 이 데이터에서는 단일 스케일도 충분히 수렴")
    print(f"     (초기 정합이 좋으면 Multi-Scale 이점 줄어듦)")
else:
    print(f"\n  ℹ️ 두 방법의 RMSE 동일 ({rmse_multi:.2f}mm)")

if fit_multi > fit_single:
    print(f"  ✅ Multi-Scale Fitness 향상: {fit_single:.4f} → {fit_multi:.4f}")


# ============================================================
# 6. 최종 변환 행렬 분해 (6DoF)
# ============================================================
print_section("Step 6: Multi-Scale ICP 최종 변환 → 6DoF 자세")

T = current_transformation
R = T[:3, :3]
t = T[:3, 3]

euler = Rotation.from_matrix(R).as_euler('ZYX', degrees=True)

print(f"  이동 (Translation):")
print(f"    X: {t[0]*1000:+.2f}mm")
print(f"    Y: {t[1]*1000:+.2f}mm")
print(f"    Z: {t[2]*1000:+.2f}mm")
print(f"\n  회전 (Euler ZYX):")
print(f"    Rz: {euler[0]:+.2f}°")
print(f"    Ry: {euler[1]:+.2f}°")
print(f"    Rx: {euler[2]:+.2f}°")


# ============================================================
# 7. 시각화
# ============================================================
print_section("Step 7: 시각화")


def draw_registration(source, target, transformation, title="Registration"):
    """정합 결과 시각화 (source=빨강, target=파랑)"""
    source_vis = copy.deepcopy(source)
    source_vis.paint_uniform_color([1, 0, 0])
    source_vis.transform(transformation)

    target_vis = copy.deepcopy(target)
    target_vis.paint_uniform_color([0, 0, 1])

    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.05)

    print(f"  [{title}] 빨강=Source, 파랑=Target")
    o3d.visualization.draw_geometries(
        [source_vis, target_vis, coord],
        window_name=title,
        width=1024, height=768,
    )


if not args.no_vis:
    # 사용할 포인트클라우드 (Fine 스케일)
    vis_source = source_raw.voxel_down_sample(BASE_VOXEL)
    vis_target = target_raw.voxel_down_sample(BASE_VOXEL)

    draw_registration(vis_source, vis_target,
                      np.eye(4), "Before Registration (초기 상태)")
    draw_registration(vis_source, vis_target,
                      init_transformation, "After RANSAC (초기 정합)")
    # 각 스케일별 결과
    for r in multi_results:
        draw_registration(vis_source, vis_target,
                          r["transformation"],
                          f"After {r['name']} ICP")
    draw_registration(vis_source, vis_target,
                      result_single.transformation, "Single-Scale ICP (비교)")
else:
    print("  --no-vis 모드: 시각화 건너뜀")


# ============================================================
# 8. 빈피킹 Multi-Scale ICP 적용 가이드
# ============================================================
print_section("Step 8: 빈피킹 Multi-Scale ICP 적용 가이드")

print("""
  왜 Multi-Scale인가?
  ─────────────────
  빈피킹에서 부품은 박스 안에서 임의의 자세로 놓여 있음.
  RANSAC/FGR 초기 정합이 완벽하지 않으면 (fitness < 0.7),
  단일 스케일 ICP는 로컬 최적해에 빠져 수렴 실패할 수 있음.

  Multi-Scale은 큰 → 작은 threshold로 점진적으로 정밀화:
  - Coarse: "대략 이 방향" (큰 오차 허용, 넓은 탐색)
  - Medium: "거의 맞음" (중간 정밀도)
  - Fine:   "정확히 여기" (서브밀리미터 정합)

  실제 빈피킹 파라미터 (BASE_VOXEL = 0.002m = 2mm):
  ┌──────────┬──────────────┬───────────────┬───────────┐
  │ 단계     │ Voxel (mm)   │ ICP dist (mm) │ Max iter  │
  ├──────────┼──────────────┼───────────────┼───────────┤
  │ Coarse   │ 8.0 (4×2)    │ 6.0 (3×2)     │ 50        │
  │ Medium   │ 4.0 (2×2)    │ 3.0 (1.5×2)   │ 30        │
  │ Fine     │ 2.0 (1×2)    │ 1.0 (0.5×2)   │ 20        │
  └──────────┴──────────────┴───────────────┴───────────┘

  Multi-Scale vs Single-Scale 선택 기준:
  - 초기 정합 fitness > 0.8 → 단일 스케일로 충분
  - 초기 정합 fitness < 0.6 → Multi-Scale 필수
  - 부품 크기 < 20mm → 2단계로 줄여도 됨 (Coarse+Fine)
  - 부품 크기 > 100mm → 4단계로 늘려도 좋음

  성능 목표: 부품당 2초
  - Multi-Scale ICP 자체는 매우 빠름 (보통 < 0.5초)
  - 병목은 RANSAC/FGR 초기 정합 + FPFH 계산
  - FPFH를 CAD에서 사전 계산(pickle)하면 런타임 절약
""")

print("\n✅ Multi-Scale ICP 튜토리얼 완료!")
