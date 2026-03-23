"""
Open3D Fast Global Registration (FGR) 튜토리얼 — 빈피킹 Plan B
================================================================

RANSAC이 느리거나 수렴 실패 시 대안: FGR (Fast Global Registration)
- Zhou et al., "Fast Global Registration" (ECCV 2016)
- FPFH 특징 기반이지만 RANSAC 없이 최적화로 직접 변환 추정
- 빈피킹에서 RANSAC 대비 10~100배 빠름 (부품당 2초 목표 달성에 유리)

파이프라인 비교:
  RANSAC: FPFH 매칭 → 랜덤 샘플링 → inlier 투표 → 최적 변환 (확률적)
  FGR:    FPFH 매칭 → Geman-McClure 로버스트 최적화 → 변환 (결정적)

Plan B 순서 (인식률 85% 미달 시):
  1차: FGR (이 튜토리얼) — RANSAC보다 빠르고 안정적
  2차: PPF (Point Pair Features) — 법선 의존도 낮음
  3차: 딥러닝 (PointNetLK 등) — 학습 데이터 필요

논문 리뷰 결정 파라미터:
  - voxel_size: 2mm (0.002m) — 실제 SLA 부품용
  - FPFH radius: 5 × voxel
  - RANSAC threshold: 1.5 × voxel
  - ICP threshold: 0.5 × voxel

⚠️ 데모에서는 Open3D DemoICPPointClouds (실내 스캔) 사용 → voxel 5cm.
   실제 빈피킹에서는 voxel 2mm로 변경.

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/04_fgr_fast_global_registration.py --no-vis
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser(description="FGR vs RANSAC 비교 튜토리얼")
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 빈피킹 파라미터 (전역 설정)
# ============================================================
# === 실제 빈피킹 파라미터 (30종 SLA 부품용) ===
# VOXEL_SIZE = 0.002  # 2mm
# === 데모 데이터용 (실내 스캔, 수 미터 규모) ===
VOXEL_SIZE = 0.05  # 5cm — 데모 데이터 스케일에 맞춤

FPFH_RADIUS = VOXEL_SIZE * 5       # FPFH 특징 계산 반경
FPFH_MAX_NN = 100                   # FPFH 이웃 포인트 수
NORMAL_RADIUS = VOXEL_SIZE * 4      # 법선 추정 반경
NORMAL_MAX_NN = 30                  # 법선 추정 이웃 수
RANSAC_DISTANCE = VOXEL_SIZE * 1.5  # RANSAC 대응점 거리 임계값
ICP_DISTANCE = VOXEL_SIZE * 0.5     # ICP 정밀 정합 거리 임계값


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
print(f"  Voxel size: {VOXEL_SIZE*1000:.0f}mm (데모용)")


# ============================================================
# 2. 전처리 (공통 함수)
# ============================================================
print_section("Step 2: 전처리 (다운샘플링 + 법선 + FPFH)")


def preprocess_point_cloud(pcd: o3d.geometry.PointCloud, voxel_size: float):
    """
    전처리 파이프라인 — RANSAC과 FGR 모두 동일한 전처리 사용:
    1. Voxel 다운샘플링
    2. 법선 추정 + 카메라 방향 정렬
    3. FPFH 특징 계산 (33D)
    """
    # 다운샘플링
    pcd_down = pcd.voxel_down_sample(voxel_size)

    # 법선 추정
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN
        )
    )

    # 법선 방향 일관성 — 카메라 위치 기준 (빈피킹 핵심!)
    pcd_down.orient_normals_towards_camera_location(
        camera_location=np.array([0.0, 0.0, 0.0])
    )

    # FPFH 특징
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        pcd_down,
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN
        ),
    )

    print(f"  {len(pcd.points):,} → {len(pcd_down.points):,} points, "
          f"FPFH {fpfh.dimension()}D × {fpfh.num()}")

    return pcd_down, fpfh


print("\n[Source 전처리]")
source_down, source_fpfh = preprocess_point_cloud(source_raw, VOXEL_SIZE)

print("\n[Target 전처리]")
target_down, target_fpfh = preprocess_point_cloud(target_raw, VOXEL_SIZE)


# ============================================================
# 3. RANSAC Global Registration (기준선)
# ============================================================
print_section("Step 3: RANSAC Global Registration (기준선)")

t0 = time.time()

result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
    source_down,
    target_down,
    source_fpfh,
    target_fpfh,
    mutual_filter=True,  # 양방향 매칭 (오대응 감소)
    max_correspondence_distance=RANSAC_DISTANCE,
    estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(
        with_scaling=False  # SLA 부품은 스케일 동일
    ),
    ransac_n=3,
    checkers=[
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(RANSAC_DISTANCE),
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
    ],
    criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
        max_iteration=100000,
        confidence=0.999,
    ),
)

time_ransac = time.time() - t0
print(f"  소요 시간: {time_ransac:.3f}초")
print(f"  Fitness: {result_ransac.fitness:.4f}")
print(f"  RMSE: {result_ransac.inlier_rmse*1000:.2f}mm")
print(f"  대응점 수: {len(result_ransac.correspondence_set):,}")


# ============================================================
# 4. FGR (Fast Global Registration) — Plan B
# ============================================================
print_section("Step 4: Fast Global Registration (FGR)")

# FGR 핵심 개념:
# - RANSAC처럼 랜덤 샘플링하지 않음 → 결정적 알고리즘
# - Geman-McClure 로버스트 비용 함수로 아웃라이어 자동 제거
# - 모든 FPFH 대응점을 동시에 최적화 → 수렴이 빠름
# - 단점: 로컬 최적해에 빠질 수 있음 (FPFH 매칭 품질에 의존)

print(f"  FGR 파라미터:")
print(f"    max_correspondence_distance: {RANSAC_DISTANCE*1000:.1f}mm")
print(f"    (RANSAC과 동일한 FPFH 특징 사용)")

t0 = time.time()

# FGR 옵션 설정
fgr_option = o3d.pipelines.registration.FastGlobalRegistrationOption(
    # 최대 대응점 거리 — RANSAC threshold와 동일하게 설정
    maximum_correspondence_distance=RANSAC_DISTANCE,
    # 반복 횟수 (기본 64, 복잡한 씬에서는 증가)
    iteration_number=64,
    # 최대 튜플 수 (FPFH 매칭에서 검증할 튜플 수)
    maximum_tuple_count=1000,
)

result_fgr = o3d.pipelines.registration.registration_fgr_based_on_feature_matching(
    source_down,
    target_down,
    source_fpfh,
    target_fpfh,
    fgr_option,
)

time_fgr = time.time() - t0
print(f"\n  소요 시간: {time_fgr:.3f}초")
print(f"  Fitness: {result_fgr.fitness:.4f}")
print(f"  RMSE: {result_fgr.inlier_rmse*1000:.2f}mm")
print(f"  대응점 수: {len(result_fgr.correspondence_set):,}")
print(f"\n  변환 행렬 (4×4):\n{result_fgr.transformation}")

# 속도 비교
if time_ransac > 0 and time_fgr > 0:
    speedup = time_ransac / time_fgr
    print(f"\n  ⚡ FGR 속도: RANSAC 대비 {speedup:.1f}배 빠름")


# ============================================================
# 5. ICP 정밀 정합 (FGR 초기값 사용)
# ============================================================
print_section("Step 5: ICP 정밀 정합 (FGR 결과를 초기값으로)")

# FGR도 RANSAC처럼 '초기 정합' — ICP로 정밀 보정 필수
# Point-to-Plane + TukeyLoss (아웃라이어 강건)

loss = o3d.pipelines.registration.TukeyLoss(k=ICP_DISTANCE)
estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)

# --- FGR → ICP ---
t0 = time.time()
result_fgr_icp = o3d.pipelines.registration.registration_icp(
    source_down,
    target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,
    init=result_fgr.transformation,  # FGR 결과를 초기 변환으로
    estimation_method=estimation,
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=50,
    ),
)
time_fgr_icp = time.time() - t0

print(f"  [FGR → ICP]")
print(f"    소요 시간: {time_fgr_icp:.3f}초")
print(f"    Fitness: {result_fgr_icp.fitness:.4f}")
print(f"    RMSE: {result_fgr_icp.inlier_rmse*1000:.2f}mm")

# --- RANSAC → ICP (비교용) ---
t0 = time.time()
result_ransac_icp = o3d.pipelines.registration.registration_icp(
    source_down,
    target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,
    init=result_ransac.transformation,  # RANSAC 결과를 초기 변환으로
    estimation_method=estimation,
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=50,
    ),
)
time_ransac_icp = time.time() - t0

print(f"\n  [RANSAC → ICP] (비교용)")
print(f"    소요 시간: {time_ransac_icp:.3f}초")
print(f"    Fitness: {result_ransac_icp.fitness:.4f}")
print(f"    RMSE: {result_ransac_icp.inlier_rmse*1000:.2f}mm")


# ============================================================
# 6. 전체 비교 테이블
# ============================================================
print_section("Step 6: 전체 비교 테이블")

# 전체 파이프라인 시간 (초기 정합 + ICP)
total_ransac = time_ransac + time_ransac_icp
total_fgr = time_fgr + time_fgr_icp

header = f"{'':>24} {'RANSAC':>10} {'FGR':>10} {'RANSAC+ICP':>12} {'FGR+ICP':>12}"
sep = "-" * len(header)

print(header)
print(sep)
print(f"{'초기정합 시간 (초)':>24} {time_ransac:>10.3f} {time_fgr:>10.3f} {'':>12} {'':>12}")
print(f"{'ICP 시간 (초)':>24} {'':>10} {'':>10} {time_ransac_icp:>12.3f} {time_fgr_icp:>12.3f}")
print(f"{'전체 시간 (초)':>24} {'':>10} {'':>10} {total_ransac:>12.3f} {total_fgr:>12.3f}")
print(sep)
print(f"{'Fitness':>24} {result_ransac.fitness:>10.4f} {result_fgr.fitness:>10.4f} "
      f"{result_ransac_icp.fitness:>12.4f} {result_fgr_icp.fitness:>12.4f}")
print(f"{'RMSE (mm)':>24} {result_ransac.inlier_rmse*1000:>10.2f} {result_fgr.inlier_rmse*1000:>10.2f} "
      f"{result_ransac_icp.inlier_rmse*1000:>12.2f} {result_fgr_icp.inlier_rmse*1000:>12.2f}")
print(f"{'대응점 수':>24} {len(result_ransac.correspondence_set):>10,} {len(result_fgr.correspondence_set):>10,} "
      f"{len(result_ransac_icp.correspondence_set):>12,} {len(result_fgr_icp.correspondence_set):>12,}")
print(sep)

if total_fgr > 0:
    print(f"\n  ⚡ FGR+ICP 총 시간: {total_fgr:.3f}초 (RANSAC+ICP: {total_ransac:.3f}초)")
    if total_ransac > total_fgr:
        print(f"  → FGR 파이프라인이 {total_ransac/total_fgr:.1f}배 빠름")


# ============================================================
# 7. 최종 변환 행렬 분해 (6DoF)
# ============================================================
print_section("Step 7: FGR+ICP 최종 변환 → 6DoF 자세")

T = result_fgr_icp.transformation
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
# 8. 시각화
# ============================================================
print_section("Step 8: 시각화")


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
    draw_registration(source_down, target_down,
                      np.eye(4), "Before Registration (초기 상태)")
    draw_registration(source_down, target_down,
                      result_fgr.transformation, "After FGR (초기 정합)")
    draw_registration(source_down, target_down,
                      result_fgr_icp.transformation, "After FGR + ICP (최종)")
    draw_registration(source_down, target_down,
                      result_ransac_icp.transformation, "After RANSAC + ICP (비교)")
else:
    print("  --no-vis 모드: 시각화 건너뜀")


# ============================================================
# 9. 빈피킹에서 FGR vs RANSAC 선택 가이드
# ============================================================
print_section("Step 9: 빈피킹 FGR vs RANSAC 선택 가이드")

print("""
  ┌─────────────────┬──────────────────┬──────────────────┐
  │     상황         │    RANSAC 추천    │    FGR 추천       │
  ├─────────────────┼──────────────────┼──────────────────┤
  │ 부품 종류 적음   │ ✅ 충분히 빠름    │ ○ 가능           │
  │ 30종 이상 매칭   │ ✗ 느림 (누적)    │ ✅ 빠르게 전수    │
  │ 실시간 2초 목표  │ △ 파라미터 조정   │ ✅ 유리           │
  │ 노이즈 많은 씬   │ ✅ 확률적 강건    │ △ 로컬 최적해     │
  │ 대칭형 부품      │ △ 다중 해 존재   │ △ 동일 문제       │
  │ FPFH 매칭 불량   │ ✅ 다수 시도      │ ✗ 수렴 실패 가능  │
  └─────────────────┴──────────────────┴──────────────────┘

  빈피킹 권장 전략:
  1. 기본: RANSAC + ICP (안정성 우선, 01_registration_pipeline.py)
  2. 속도 필요 시: FGR + ICP (이 튜토리얼)
  3. 둘 다 실패 시: PPF → 딥러닝 순서로 시도

  FGR 사용 팁:
  - FPFH 특징 품질이 좋을수록 FGR 성능 ↑
  - 법선 추정 품질 = 전체 파이프라인 품질 (L2 전처리가 핵심)
  - iteration_number: 64(기본) → 128(복잡한 씬)
  - maximum_tuple_count: 1000(기본) → 5000(대형 포인트클라우드)
""")

print("\n✅ FGR 튜토리얼 완료!")
