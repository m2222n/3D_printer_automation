"""
RealSense E2E 파이프라인 테스트
================================
RealSense 캡처 모듈 → depth_to_pointcloud() → L2 전처리 → L3 분할 → L4 매칭
카메라가 없으면 Redwood RGB-D 데이터로 CapturedFrames를 시뮬레이션.

실행 환경: Mac (Open3D + AVX2 필요) 또는 RealSense USB 연결된 PC
    cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/
    source .venv/binpick/bin/activate
    python bin_picking/tests/test_e2e_realsense.py

    # 카메라 연결 시 라이브 캡처 테스트:
    sudo .venv/binpick/bin/python bin_picking/tests/test_e2e_realsense.py --live

    # 라이브 캡처 + 프레임 영구 저장 (서버 로드 테스트용):
    sudo .venv/binpick/bin/python bin_picking/tests/test_e2e_realsense.py --live --save

    # 저장된 프레임으로 로드 테스트 (카메라 불필요):
    python bin_picking/tests/test_e2e_realsense.py --load

테스트 내용:
    1. RealSenseCapture 모듈 임포트 + CapturedFrames 생성
    2. CapturedFrames → depth_to_pointcloud() 변환
    3. 프레임 저장/로드 라운드트립 (--save: 영구 저장)
    4. L2 전처리 → L3 분할 → L4 매칭 (기존 파이프라인 연결)
    5. (--live) 실제 카메라 캡처 + 파이프라인 실행
    6. (--load) 저장된 D435 프레임 로드 + 파이프라인 실행
"""

import sys
import os
import time
import tempfile
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    import open3d as o3d
    print(f"[OK] Open3D {o3d.__version__}")
except ImportError:
    print("[ERROR] Open3D가 설치되지 않았습니다.")
    sys.exit(1)

from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud
from bin_picking.src.acquisition.realsense_capture import (
    RealSenseCapture,
    CapturedFrames,
    RSIntrinsics,
)

LIVE_MODE = "--live" in sys.argv
SAVE_MODE = "--save" in sys.argv
LOAD_MODE = "--load" in sys.argv

# 프레임 저장 경로 (서버 로드 테스트용)
FRAMES_DIR = os.path.join(PROJECT_ROOT, "bin_picking", "models", "d435_frames")


def make_simulated_frames() -> CapturedFrames:
    """Redwood RGB-D 데이터에서 CapturedFrames를 생성 (카메라 시뮬레이션)."""
    redwood = o3d.data.SampleRedwoodRGBDImages()
    depth_raw = np.asarray(o3d.io.read_image(redwood.depth_paths[0]))  # uint16, mm
    color_raw = np.asarray(o3d.io.read_image(redwood.color_paths[0]))  # RGB uint8

    # Open3D는 RGB로 읽으므로 BGR로 변환 (파이프라인 규격)
    color_bgr = color_raw[:, :, ::-1].copy()

    H, W = depth_raw.shape[:2]
    intrinsics = RSIntrinsics(
        width=W, height=H,
        fx=525.0, fy=525.0,
        cx=319.5, cy=239.5,
    )
    return CapturedFrames(
        depth_map=depth_raw,
        color_image=color_bgr,
        intrinsics=intrinsics,
        depth_scale=1000.0,
    )


def step1_capture_or_simulate():
    """1단계: 프레임 취득 (카메라 or 시뮬레이션)."""
    print("\n" + "=" * 60)
    print("Step 1: 프레임 취득")
    print("=" * 60)

    if LOAD_MODE:
        print(f"  모드: LOAD (저장된 D435 프레임: {FRAMES_DIR}/)")
        if not os.path.isdir(FRAMES_DIR):
            print(f"  [ERROR] 프레임 디렉토리 없음: {FRAMES_DIR}")
            print("  먼저 --live --save로 프레임을 저장하세요.")
            sys.exit(1)
        frames = RealSenseCapture.load_frames(FRAMES_DIR)
        print(f"  depth shape: {frames.depth_map.shape}")
        print(f"  color shape: {frames.color_image.shape}")
        print(f"  intrinsics: fx={frames.intrinsics.fx:.1f}, fy={frames.intrinsics.fy:.1f}")
        print(f"  depth_scale: {frames.depth_scale}")
    elif LIVE_MODE:
        print("  모드: LIVE (RealSense 카메라)")
        cap = RealSenseCapture(width=640, height=480, fps=30)
        cap.start()
        # 자동 노출 안정화 대기
        for _ in range(30):
            cap.capture()
        frames = cap.capture()
        cap.stop()
        print(f"  depth shape: {frames.depth_map.shape}")
        print(f"  color shape: {frames.color_image.shape}")
        print(f"  intrinsics: fx={frames.intrinsics.fx:.1f}, fy={frames.intrinsics.fy:.1f}")
        print(f"  depth_scale: {frames.depth_scale}")
    else:
        print("  모드: SIMULATED (Redwood RGB-D)")
        frames = make_simulated_frames()
        print(f"  depth shape: {frames.depth_map.shape}")
        print(f"  color shape: {frames.color_image.shape}")
        print(f"  intrinsics: fx={frames.intrinsics.fx:.1f}, fy={frames.intrinsics.fy:.1f}")

    valid_count = np.count_nonzero(frames.depth_map > 0)
    print(f"  유효 depth 픽셀: {valid_count:,}")
    print("  [PASS] Step 1")
    return frames


def step2_to_pointcloud(frames: CapturedFrames):
    """2단계: CapturedFrames → Open3D PointCloud."""
    print("\n" + "=" * 60)
    print("Step 2: depth_to_pointcloud() 변환")
    print("=" * 60)

    t0 = time.time()
    pcd = depth_to_pointcloud(
        depth_map=frames.depth_map,
        fx=frames.intrinsics.fx,
        fy=frames.intrinsics.fy,
        cx=frames.intrinsics.cx,
        cy=frames.intrinsics.cy,
        color_image=frames.color_image,
        depth_scale=frames.depth_scale,
        depth_min=0.1,
        depth_max=5.0,
    )
    elapsed = time.time() - t0

    n_points = len(pcd.points)
    has_colors = len(pcd.colors) > 0
    print(f"  포인트 수: {n_points:,}")
    print(f"  칼라: {'있음' if has_colors else '없음'}")
    print(f"  변환 시간: {elapsed:.3f}s")

    assert n_points > 0, "포인트가 0개입니다"
    assert has_colors, "칼라가 없습니다"
    print("  [PASS] Step 2")
    return pcd


def step3_save_load_roundtrip(frames: CapturedFrames):
    """3단계: 프레임 저장/로드 라운드트립 검증 + --save 시 영구 저장."""
    print("\n" + "=" * 60)
    print("Step 3: 프레임 저장/로드 라운드트립")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        frames.save(tmpdir)
        loaded = RealSenseCapture.load_frames(tmpdir)

        assert np.array_equal(frames.depth_map, loaded.depth_map), "depth 불일치"
        assert np.array_equal(frames.color_image, loaded.color_image), "color 불일치"
        assert frames.intrinsics.fx == loaded.intrinsics.fx, "fx 불일치"
        assert frames.intrinsics.fy == loaded.intrinsics.fy, "fy 불일치"
        assert frames.depth_scale == loaded.depth_scale, "depth_scale 불일치"

        print(f"  저장 경로: {tmpdir}/")
        print(f"  depth.npy: {frames.depth_map.nbytes / 1024:.0f} KB")
        print(f"  color.npy: {frames.color_image.nbytes / 1024:.0f} KB")
        print("  로드 후 일치: depth ✓ color ✓ intrinsics ✓")
    print("  [PASS] Step 3")

    # --save: 서버 로드 테스트용 영구 저장
    if SAVE_MODE:
        print(f"\n  [SAVE] 프레임 영구 저장 → {FRAMES_DIR}/")
        frames.save(FRAMES_DIR)

        # 저장 검증
        loaded = RealSenseCapture.load_frames(FRAMES_DIR)
        assert np.array_equal(frames.depth_map, loaded.depth_map), "영구 저장 depth 불일치"
        assert np.array_equal(frames.color_image, loaded.color_image), "영구 저장 color 불일치"

        depth_kb = os.path.getsize(os.path.join(FRAMES_DIR, "depth.npy")) / 1024
        color_kb = os.path.getsize(os.path.join(FRAMES_DIR, "color.npy")) / 1024
        meta_kb = os.path.getsize(os.path.join(FRAMES_DIR, "meta.json")) / 1024
        total_mb = (depth_kb + color_kb + meta_kb) / 1024
        print(f"  depth.npy: {depth_kb:.0f} KB")
        print(f"  color.npy: {color_kb:.0f} KB")
        print(f"  meta.json: {meta_kb:.1f} KB")
        print(f"  합계: {total_mb:.1f} MB")
        print("  저장 검증: depth ✓ color ✓")
        print("  [PASS] 영구 저장 완료")


def step4_pipeline(pcd):
    """4단계: L2 전처리 → L3 분할 → L4 매칭."""
    print("\n" + "=" * 60)
    print("Step 4: L2→L3→L4 파이프라인")
    print("=" * 60)

    t0 = time.time()

    # --- L2: 전처리 (간소화 — CloudFilter 없이 직접) ---
    print("\n  [L2] 전처리")
    voxel_size = 0.005
    pcd_down = pcd.voxel_down_sample(voxel_size)
    print(f"    Voxel 다운샘플({voxel_size}m): {len(pcd.points):,} → {len(pcd_down.points):,}")

    cl, idx = pcd_down.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    pcd_clean = pcd_down.select_by_index(idx)
    print(f"    SOR 이상치 제거: {len(pcd_down.points):,} → {len(pcd_clean.points):,}")

    # RANSAC 바닥면 제거
    if len(pcd_clean.points) > 100:
        plane_model, inliers = pcd_clean.segment_plane(
            distance_threshold=0.01, ransac_n=3, num_iterations=1000
        )
        pcd_objects = pcd_clean.select_by_index(inliers, invert=True)
        print(f"    RANSAC 바닥면 제거: 바닥 {len(inliers):,}점, 나머지 {len(pcd_objects.points):,}점")
    else:
        pcd_objects = pcd_clean

    pcd_objects.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.02, max_nn=30)
    )

    # --- L3: DBSCAN 분할 ---
    print("\n  [L3] DBSCAN 분할")
    if len(pcd_objects.points) > 50:
        labels = np.array(
            pcd_objects.cluster_dbscan(eps=0.02, min_points=50, print_progress=False)
        )
        n_clusters = labels.max() + 1 if len(labels) > 0 else 0
        noise_count = np.sum(labels == -1)
        print(f"    클러스터 수: {n_clusters}")
        print(f"    노이즈 포인트: {noise_count:,}")

        if n_clusters > 0:
            largest_idx = np.where(labels == 0)[0]
            cluster0 = pcd_objects.select_by_index(largest_idx)
            print(f"    최대 클러스터: {len(cluster0.points):,}점")
        else:
            cluster0 = pcd_objects
    else:
        print("    포인트 부족 → 분할 생략")
        cluster0 = pcd_objects
        n_clusters = 0

    # --- L4: FPFH + RANSAC + ICP (자기 자신 매칭) ---
    print("\n  [L4] FPFH + RANSAC + ICP 매칭")
    if len(cluster0.points) < 50:
        print("    포인트 부족 → 매칭 생략")
        elapsed = time.time() - t0
        print(f"\n  전체 파이프라인 시간: {elapsed:.2f}s")
        print("  [PASS] Step 4 (분할까지)")
        return

    radius_feature = 0.05
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        cluster0,
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius_feature, max_nn=100),
    )
    print(f"    FPFH 특징: {fpfh.data.shape}")

    # 자기 자신 매칭 (source == target)
    result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        cluster0, cluster0, fpfh, fpfh,
        mutual_filter=True,
        max_correspondence_distance=0.05,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        ransac_n=3,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(0.05),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(100000, 0.999),
    )
    print(f"    RANSAC fitness: {result_ransac.fitness:.4f}")

    result_icp = o3d.pipelines.registration.registration_icp(
        cluster0, cluster0,
        max_correspondence_distance=0.01,
        init=result_ransac.transformation,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
    )
    print(f"    ICP fitness: {result_icp.fitness:.4f}")
    print(f"    ICP RMSE: {result_icp.inlier_rmse:.6f}")

    elapsed = time.time() - t0
    print(f"\n  전체 파이프라인 시간: {elapsed:.2f}s")

    assert result_icp.fitness > 0.8, f"ICP fitness {result_icp.fitness:.4f} < 0.8"
    print("  [PASS] Step 4")
    return n_clusters


def main():
    print("=" * 60)
    print("RealSense E2E 파이프라인 테스트")
    if LOAD_MODE:
        mode_str = "LOAD (저장된 D435 프레임)"
    elif LIVE_MODE:
        mode_str = f"LIVE{' + SAVE' if SAVE_MODE else ''}"
    else:
        mode_str = "SIMULATED (Redwood)"
    print(f"모드: {mode_str}")
    print("=" * 60)

    t_total = time.time()

    # Step 1: 프레임 취득
    frames = step1_capture_or_simulate()

    # Step 2: PointCloud 변환
    pcd = step2_to_pointcloud(frames)

    # Step 3: 저장/로드 라운드트립
    step3_save_load_roundtrip(frames)

    # Step 4: L2→L3→L4 파이프라인
    step4_pipeline(pcd)

    elapsed_total = time.time() - t_total
    print("\n" + "=" * 60)
    print(f"전체 테스트 완료: {elapsed_total:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
