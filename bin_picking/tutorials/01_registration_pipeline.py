"""
Open3D Registration 튜토리얼 — 빈피킹 파라미터 맞춤 실습
==========================================================

파이프라인: L2 전처리 → L4 FPFH+RANSAC 초기정합 → ICP Point-to-Plane 정밀정합

논문 리뷰 결정 파라미터:
  - voxel_size: 2mm (0.002m)
  - FPFH radius: 10mm (5 × voxel)
  - RANSAC distance threshold: 3mm (1.5 × voxel)
  - ICP distance threshold: 1mm (0.5 × voxel)
  - ICP: Point-to-Plane + Robust (TukeyLoss) kernel

⚠️ 주의: Open3D DemoICPPointClouds는 실내 스캔 데이터 (수 미터 규모).
   빈피킹 SLA 부품은 수십 mm 규모이므로 voxel_size 스케일이 다름.
   → 데모에서는 voxel 5cm 사용, 실제 빈피킹에서는 2mm 사용.
   → 코드 하단 DEMO_SCALE 참고.

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/01_registration_pipeline.py
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d

parser = argparse.ArgumentParser()
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 빈피킹 파라미터 (전역 설정)
# ============================================================
# === 실제 빈피킹 파라미터 (30종 SLA 부품용) ===
# VOXEL_SIZE = 0.002  # 2mm
# === 데모 데이터용 (실내 스캔, 수 미터 규모) ===
VOXEL_SIZE = 0.05  # 5cm — 데모 데이터 스케일에 맞춤
# STL 파일로 실습할 때는 위의 0.002로 변경!
FPFH_RADIUS = VOXEL_SIZE * 5  # 10mm
FPFH_MAX_NN = 100  # FPFH 이웃 포인트 수
NORMAL_RADIUS = VOXEL_SIZE * 4  # 8mm — 법선 추정 반경
NORMAL_MAX_NN = 30  # 법선 추정 이웃 수
RANSAC_DISTANCE = VOXEL_SIZE * 1.5  # 3mm
RANSAC_MAX_ITERATION = 100000
RANSAC_CONFIDENCE = 0.999
ICP_DISTANCE = VOXEL_SIZE * 0.5  # 1mm


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 샘플 데이터 준비 (STL 없으므로 Open3D 내장 데이터 사용)
# ============================================================
print_section("Step 1: 샘플 데이터 로드")

# Open3D 데모 데이터 — 두 개의 포인트 클라우드 (부분 겹침)
demo_data = o3d.data.DemoICPPointClouds()
source_raw = o3d.io.read_point_cloud(demo_data.paths[0])
target_raw = o3d.io.read_point_cloud(demo_data.paths[1])

print(f"Source: {len(source_raw.points):,} points")
print(f"Target: {len(target_raw.points):,} points")

# 실제 빈피킹에서는:
# - source = STL에서 샘플링한 레퍼런스 클라우드 (CAD 모델)
# - target = Basler Blaze-112 ToF 카메라에서 취득한 씬 클라우드


# ============================================================
# 2. 전처리 (L2): 다운샘플링 + 법선 추정 + FPFH 특징 계산
# ============================================================
print_section("Step 2: 전처리 (다운샘플링 + 법선 + FPFH)")


def preprocess_point_cloud(pcd: o3d.geometry.PointCloud, voxel_size: float):
    """
    전처리 파이프라인:
    1. Voxel 다운샘플링 (균일한 밀도)
    2. 법선 추정 (Point-to-Plane ICP와 FPFH에 필수)
    3. 카메라 방향으로 법선 정렬 (⚠️ 빈피킹 핵심!)
    4. FPFH 특징 계산 (33차원 히스토그램)
    """
    # 2-1. Voxel 다운샘플링
    pcd_down = pcd.voxel_down_sample(voxel_size)
    print(f"  다운샘플링: {len(pcd.points):,} → {len(pcd_down.points):,} points")

    # 2-2. 법선 추정 (KNN + Radius hybrid)
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=NORMAL_RADIUS,
            max_nn=NORMAL_MAX_NN,
        )
    )

    # 2-3. 법선 방향 일관성 — 카메라 위치 기준 (⚠️ 매우 중요!)
    # 빈피킹에서는 카메라 위치(0,0,0)를 기준으로 법선이 카메라를 향하도록 정렬
    # 이렇게 안 하면 FPFH 특징이 뒤집혀서 매칭 실패함
    pcd_down.orient_normals_towards_camera_location(
        camera_location=np.array([0.0, 0.0, 0.0])
    )
    print(f"  법선 추정 완료 (radius={NORMAL_RADIUS*1000:.0f}mm, "
          f"카메라 방향 정렬)")

    # 2-4. FPFH (Fast Point Feature Histogram) 특징 계산
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        pcd_down,
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=FPFH_RADIUS,
            max_nn=FPFH_MAX_NN,
        ),
    )
    print(f"  FPFH 특징: {fpfh.dimension()}D × {fpfh.num()} points")

    return pcd_down, fpfh


print("\n[Source 전처리]")
source_down, source_fpfh = preprocess_point_cloud(source_raw, VOXEL_SIZE)

print("\n[Target 전처리]")
target_down, target_fpfh = preprocess_point_cloud(target_raw, VOXEL_SIZE)


# ============================================================
# 3. RANSAC 기반 Global Registration (초기 정합)
# ============================================================
print_section("Step 3: RANSAC Global Registration (초기 정합)")

t0 = time.time()

# RANSAC: 랜덤 대응점 선택 → 변환 추정 → inlier 검증
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
    ransac_n=3,  # 최소 3점으로 변환 추정
    checkers=[
        # 거리 체크: 대응점 간 거리가 threshold 이내
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(
            RANSAC_DISTANCE
        ),
        # 엣지 길이 체크: 대응점 쌍의 엣지 비율 유사 (0.9 = 90% 유사)
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
    ],
    criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
        max_iteration=RANSAC_MAX_ITERATION,
        confidence=RANSAC_CONFIDENCE,
    ),
)

elapsed_ransac = time.time() - t0
print(f"  소요 시간: {elapsed_ransac:.2f}초")
print(f"  Fitness: {result_ransac.fitness:.4f} "
      f"(inlier 비율, 1.0에 가까울수록 좋음)")
print(f"  RMSE: {result_ransac.inlier_rmse:.6f}m "
      f"({result_ransac.inlier_rmse*1000:.2f}mm)")
print(f"  대응점 수: {len(result_ransac.correspondence_set):,}")
print(f"\n  변환 행렬 (4×4):\n{result_ransac.transformation}")

# RANSAC 결과 검증
if result_ransac.fitness < 0.3:
    print("  ⚠️ Fitness가 낮음 — 파라미터 조정 또는 데이터 확인 필요")


# ============================================================
# 4. ICP Point-to-Plane 정밀 정합 (Robust Kernel)
# ============================================================
print_section("Step 4: ICP Point-to-Plane 정밀 정합 (Robust Kernel)")

t0 = time.time()

# Robust kernel: 아웃라이어에 강건한 Tukey loss
# sigma = ICP_DISTANCE (아웃라이어 판단 기준)
loss = o3d.pipelines.registration.TukeyLoss(k=ICP_DISTANCE)
print(f"  Robust kernel: TukeyLoss(k={ICP_DISTANCE*1000:.1f}mm)")

# Point-to-Plane: 법선 정보 활용 → Point-to-Point보다 수렴 빠르고 정확
estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)

# ICP 실행 — RANSAC 결과를 초기값으로 사용
result_icp = o3d.pipelines.registration.registration_icp(
    source_down,
    target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,  # 초기엔 넓게, 수렴하면서 좁아짐
    init=result_ransac.transformation,  # RANSAC 결과를 초기 변환으로
    estimation_method=estimation,
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,   # fitness 변화가 이보다 작으면 수렴
        relative_rmse=1e-6,      # RMSE 변화가 이보다 작으면 수렴
        max_iteration=50,        # 최대 반복
    ),
)

elapsed_icp = time.time() - t0
print(f"  소요 시간: {elapsed_icp:.3f}초")
print(f"  Fitness: {result_icp.fitness:.4f}")
print(f"  RMSE: {result_icp.inlier_rmse:.6f}m "
      f"({result_icp.inlier_rmse*1000:.2f}mm)")
print(f"  대응점 수: {len(result_icp.correspondence_set):,}")
print(f"\n  최종 변환 행렬 (4×4):\n{result_icp.transformation}")


# ============================================================
# 5. 결과 비교 (RANSAC vs ICP)
# ============================================================
print_section("Step 5: 결과 비교")

print(f"{'':>20} {'RANSAC':>12} {'ICP':>12}")
print(f"{'Fitness':>20} {result_ransac.fitness:>12.4f} {result_icp.fitness:>12.4f}")
print(f"{'RMSE (mm)':>20} {result_ransac.inlier_rmse*1000:>12.2f} {result_icp.inlier_rmse*1000:>12.2f}")
print(f"{'대응점 수':>20} {len(result_ransac.correspondence_set):>12,} {len(result_icp.correspondence_set):>12,}")
print(f"{'소요 시간 (초)':>20} {elapsed_ransac:>12.2f} {elapsed_icp:>12.3f}")


# ============================================================
# 6. 변환 행렬 → 회전/이동 분해
# ============================================================
print_section("Step 6: 변환 행렬 분해 (6DoF 자세)")

T = result_icp.transformation
R = T[:3, :3]  # 3×3 회전 행렬
t = T[:3, 3]   # 3×1 이동 벡터

# 회전 행렬 → 오일러 각도 (ZYX 순서, 로봇 관절에 흔히 사용)
from scipy.spatial.transform import Rotation
euler = Rotation.from_matrix(R).as_euler('ZYX', degrees=True)

print(f"  이동 (Translation):")
print(f"    X: {t[0]*1000:+.2f} mm")
print(f"    Y: {t[1]*1000:+.2f} mm")
print(f"    Z: {t[2]*1000:+.2f} mm")
print(f"\n  회전 (Euler ZYX):")
print(f"    Rz: {euler[0]:+.2f}°")
print(f"    Ry: {euler[1]:+.2f}°")
print(f"    Rx: {euler[2]:+.2f}°")


# ============================================================
# 7. 시각화
# ============================================================
print_section("Step 7: 시각화")


def draw_registration(source, target, transformation, title="Registration"):
    """정합 결과를 시각화 (source=빨강, target=파랑)"""
    source_vis = copy.deepcopy(source)
    source_vis.paint_uniform_color([1, 0, 0])  # 빨강 = source (CAD)
    source_vis.transform(transformation)

    target_vis = copy.deepcopy(target)
    target_vis.paint_uniform_color([0, 0, 1])  # 파랑 = target (씬)

    # 좌표축 표시 (크기 = 50mm)
    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.05)

    print(f"  [{title}] 빨강=Source(CAD), 파랑=Target(씬)")
    print("  창을 닫으면 다음 단계로 진행합니다.")
    o3d.visualization.draw_geometries(
        [source_vis, target_vis, coord],
        window_name=title,
        width=1024,
        height=768,
    )


if not args.no_vis:
    # 7-1. 초기 상태 (정합 전)
    draw_registration(source_down, target_down,
                      np.eye(4), "Before Registration (초기 상태)")

    # 7-2. RANSAC 결과
    draw_registration(source_down, target_down,
                      result_ransac.transformation, "After RANSAC (초기 정합)")

    # 7-3. ICP 결과 (최종)
    draw_registration(source_down, target_down,
                      result_icp.transformation, "After ICP (정밀 정합)")
else:
    print("  --no-vis 모드: 시각화 건너뜀 (GUI 없는 환경)")


# ============================================================
# 8. 빈피킹 실전 적용 시 고려사항
# ============================================================
print_section("Step 8: 빈피킹 실전 적용 메모")

print("""
  1. STL → 레퍼런스 클라우드 생성:
     mesh = o3d.io.read_triangle_mesh("part.stl")
     pcd = mesh.sample_points_uniformly(number_of_points=10000)
     → FPFH 사전 계산 + pickle 캐싱

  2. 카메라 데이터 → 씬 클라우드:
     Basler Blaze-112 depth → open3d.geometry.PointCloud
     → 배경 제거 (passthrough filter) → DBSCAN 개별 부품 분할

  3. 법선 품질이 파이프라인 전체 성패 결정:
     - estimate_normals() 파라미터 신중히 조정
     - orient_normals_towards_camera_location() 필수
     - 법선 시각화로 반드시 검증: pcd_down.normals

  4. 인식률 85% 미달 시 플랜B:
     FGR (Fast Global Registration) → PPF → 딥러닝 순서

  5. 성능 목표: 부품당 2초 이내
     - FPFH 사전 계산으로 런타임 절약
     - RANSAC max_iteration 줄이되 confidence 유지
""")

print("\n✅ 튜토리얼 완료!")
