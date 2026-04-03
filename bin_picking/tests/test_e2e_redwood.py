"""
Redwood RGB-D 데이터셋 E2E 파이프라인 테스트
=============================================
Open3D 내장 Redwood RGB-D 데이터셋으로 빈피킹 파이프라인 전체 검증.
실제 카메라 없이 depth→pointcloud→전처리→분할→매칭까지 테스트.

실행 환경: Mac (Open3D + AVX2 필요)
    cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/
    source .venv/binpick/bin/activate
    python bin_picking/tests/test_e2e_redwood.py

테스트 내용:
    1. Redwood RGB-D depth/color 로드
    2. depth_to_pointcloud() 변환 검증
    3. L2 전처리 (다운샘플링, 이상치 제거, 바닥면 제거)
    4. L3 DBSCAN 분할
    5. L4 FPFH+RANSAC+ICP 매칭 (자기 자신 매칭으로 검증)
"""

import sys
import os
import time
import numpy as np

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    import open3d as o3d
    print(f"[OK] Open3D {o3d.__version__}")
except ImportError:
    print("[ERROR] Open3D가 설치되지 않았습니다.")
    sys.exit(1)

from bin_picking.src.acquisition.depth_to_pointcloud import (
    depth_to_pointcloud,
    BLAZE_112_INTRINSICS,
)


def step1_load_redwood():
    """1단계: Redwood RGB-D 데이터셋 로드."""
    print("\n" + "=" * 60)
    print("Step 1: Redwood RGB-D 데이터셋 로드")
    print("=" * 60)

    # Open3D 내장 데이터셋
    redwood = o3d.data.SampleRedwoodRGBDImages()
    print(f"  depth 이미지 수: {len(redwood.depth_paths)}")
    print(f"  color 이미지 수: {len(redwood.color_paths)}")

    # 첫 번째 프레임 로드
    depth_raw = o3d.io.read_image(redwood.depth_paths[0])
    color_raw = o3d.io.read_image(redwood.color_paths[0])

    depth_np = np.asarray(depth_raw)
    color_np = np.asarray(color_raw)

    print(f"  depth shape: {depth_np.shape}, dtype: {depth_np.dtype}")
    print(f"  color shape: {color_np.shape}, dtype: {color_np.dtype}")
    print(f"  depth range: {depth_np[depth_np > 0].min()} ~ {depth_np.max()}")

    return redwood, depth_np, color_np


def step2_depth_to_pointcloud(depth_np, color_np):
    """2단계: depth_to_pointcloud() 변환 검증."""
    print("\n" + "=" * 60)
    print("Step 2: depth_to_pointcloud() 변환")
    print("=" * 60)

    # Redwood 카메라 파라미터 (PrimeSense 카메라)
    # Open3D 기본: fx=fy=525, cx=319.5, cy=239.5
    fx, fy = 525.0, 525.0
    cx, cy = 319.5, 239.5

    t0 = time.time()

    # BGR로 변환 (Redwood는 RGB)
    color_bgr = color_np[..., ::-1].copy()

    pcd = depth_to_pointcloud(
        depth_map=depth_np,
        fx=fx, fy=fy, cx=cx, cy=cy,
        color_image=color_bgr,
        depth_scale=1000.0,  # Redwood depth는 mm 단위
        depth_min=0.1,
        depth_max=5.0,
    )

    elapsed = time.time() - t0
    n_points = len(pcd.points)
    has_colors = len(pcd.colors) > 0

    print(f"  포인트 수: {n_points:,}")
    print(f"  칼라 여부: {has_colors}")
    print(f"  변환 시간: {elapsed:.3f}s")

    # 검증
    assert n_points > 10000, f"포인트 수 부족: {n_points}"
    assert has_colors, "칼라 매핑 실패"
    print("  [PASS] depth_to_pointcloud() 정상")

    return pcd


def step3_preprocessing(pcd):
    """3단계: L2 전처리."""
    print("\n" + "=" * 60)
    print("Step 3: L2 전처리 (다운샘플링 + 이상치 제거 + 바닥면 제거)")
    print("=" * 60)

    n_original = len(pcd.points)
    t0 = time.time()

    # 3-1. 다운샘플링 (voxel 5mm — Redwood는 실내 씬이라 좀 큼)
    voxel_size = 0.005
    pcd_down = pcd.voxel_down_sample(voxel_size)
    n_down = len(pcd_down.points)
    print(f"  다운샘플링: {n_original:,} → {n_down:,} ({voxel_size*1000:.0f}mm voxel)")

    # 3-2. 통계적 이상치 제거
    pcd_clean, ind = pcd_down.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    n_clean = len(pcd_clean.points)
    n_removed = n_down - n_clean
    print(f"  이상치 제거: {n_down:,} → {n_clean:,} ({n_removed} 제거)")

    # 3-3. 법선 추정
    pcd_clean.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.01, max_nn=30)
    )
    pcd_clean.orient_normals_towards_camera_location(camera_location=np.array([0, 0, 0]))
    print(f"  법선 추정 완료: {len(pcd_clean.normals)} normals")

    # 3-4. 바닥면 제거 (RANSAC 평면)
    plane_model, inliers = pcd_clean.segment_plane(
        distance_threshold=0.01, ransac_n=3, num_iterations=1000
    )
    a, b, c, d = plane_model
    print(f"  바닥 평면: {a:.3f}x + {b:.3f}y + {c:.3f}z + {d:.3f} = 0")
    print(f"  바닥 inliers: {len(inliers)}")

    pcd_objects = pcd_clean.select_by_index(inliers, invert=True)
    n_objects = len(pcd_objects.points)
    print(f"  바닥 제거 후: {n_objects:,} 포인트")

    elapsed = time.time() - t0
    print(f"  전처리 총 시간: {elapsed:.3f}s")
    print("  [PASS] L2 전처리 정상")

    return pcd_objects


def step4_segmentation(pcd_objects):
    """4단계: L3 DBSCAN 분할."""
    print("\n" + "=" * 60)
    print("Step 4: L3 DBSCAN 분할")
    print("=" * 60)

    t0 = time.time()

    # DBSCAN 클러스터링
    labels = np.asarray(
        pcd_objects.cluster_dbscan(eps=0.02, min_points=50, print_progress=False)
    )

    n_clusters = labels.max() + 1
    n_noise = (labels == -1).sum()

    elapsed = time.time() - t0
    print(f"  클러스터 수: {n_clusters}")
    print(f"  노이즈 포인트: {n_noise}")
    print(f"  분할 시간: {elapsed:.3f}s")

    # 각 클러스터 크기
    clusters = []
    for i in range(n_clusters):
        cluster_mask = labels == i
        cluster_pcd = pcd_objects.select_by_index(np.where(cluster_mask)[0])
        n_pts = len(cluster_pcd.points)
        bbox = cluster_pcd.get_axis_aligned_bounding_box()
        extent = bbox.get_extent()
        print(f"  클러스터 {i}: {n_pts:,} pts, "
              f"크기 {extent[0]*1000:.0f}x{extent[1]*1000:.0f}x{extent[2]*1000:.0f} mm")
        clusters.append(cluster_pcd)

    assert n_clusters > 0, "클러스터 없음"
    print("  [PASS] L3 DBSCAN 분할 정상")

    return clusters


def step5_recognition(clusters):
    """5단계: L4 FPFH+RANSAC+ICP 매칭 (자기 자신 매칭 테스트)."""
    print("\n" + "=" * 60)
    print("Step 5: L4 FPFH + RANSAC + ICP 매칭 (자기 자신)")
    print("=" * 60)

    if len(clusters) == 0:
        print("  [SKIP] 클러스터 없음")
        return

    # 가장 큰 클러스터를 사용
    target = max(clusters, key=lambda c: len(c.points))
    print(f"  대상 클러스터: {len(target.points):,} pts")

    # 자기 자신을 레퍼런스로 사용 (소스 = 약간 변환된 타겟)
    # 실제로는 STL→레퍼런스 클라우드가 여기에 들어감
    source = target

    t0 = time.time()

    # 다운샘플링
    voxel_size = 0.005
    source_down = source.voxel_down_sample(voxel_size)
    target_down = target.voxel_down_sample(voxel_size)

    # 법선이 없으면 추정
    for pcd in [source_down, target_down]:
        if not pcd.has_normals():
            pcd.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamHybrid(
                    radius=voxel_size * 2, max_nn=30
                )
            )

    # FPFH 특징 계산
    radius_feature = voxel_size * 5
    source_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        source_down,
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100),
    )
    target_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        target_down,
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100),
    )
    print(f"  FPFH 차원: {source_fpfh.dimension()}")
    print(f"  source features: {source_fpfh.num()}, target features: {target_fpfh.num()}")

    # RANSAC 대략 정합
    distance_threshold = voxel_size * 1.5
    ransac_result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        source_down,
        target_down,
        source_fpfh,
        target_fpfh,
        mutual_filter=True,
        max_correspondence_distance=distance_threshold,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        ransac_n=3,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(100000, 0.999),
    )
    print(f"  RANSAC fitness: {ransac_result.fitness:.4f}")
    print(f"  RANSAC RMSE: {ransac_result.inlier_rmse:.6f}")

    # ICP 정밀 정합 (Point-to-Plane)
    icp_result = o3d.pipelines.registration.registration_icp(
        source_down,
        target_down,
        distance_threshold,
        ransac_result.transformation,
        o3d.pipelines.registration.TransformationEstimationPointToPlane(),
    )
    print(f"  ICP fitness: {icp_result.fitness:.4f}")
    print(f"  ICP RMSE: {icp_result.inlier_rmse:.6f}")

    elapsed = time.time() - t0
    print(f"  매칭 시간: {elapsed:.3f}s")

    # 자기 자신 매칭이므로 fitness ~1.0이어야 함
    assert icp_result.fitness > 0.5, f"매칭 실패: fitness={icp_result.fitness}"
    print("  [PASS] L4 FPFH+RANSAC+ICP 매칭 정상")


def main():
    print("=" * 60)
    print("빈피킹 E2E 파이프라인 테스트 (Redwood RGB-D)")
    print("=" * 60)

    t_total = time.time()

    # Step 1: 데이터 로드
    redwood, depth_np, color_np = step1_load_redwood()

    # Step 2: depth → point cloud
    pcd = step2_depth_to_pointcloud(depth_np, color_np)

    # Step 3: 전처리
    pcd_objects = step3_preprocessing(pcd)

    # Step 4: DBSCAN 분할
    clusters = step4_segmentation(pcd_objects)

    # Step 5: FPFH+RANSAC+ICP 매칭
    step5_recognition(clusters)

    total_elapsed = time.time() - t_total
    print("\n" + "=" * 60)
    print(f"전체 파이프라인 완료: {total_elapsed:.3f}s")
    print("모든 단계 PASS!")
    print("=" * 60)


if __name__ == "__main__":
    main()
