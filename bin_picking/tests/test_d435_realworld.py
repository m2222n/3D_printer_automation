"""
D435 실데이터 테스트 — 일반 사물로 L1→L2→L3 파이프라인 검증
=============================================================
D435로 책상 위 사물을 촬영하고, 실제 depth 데이터에서
전처리(L2) → 분할(L3)이 정상 동작하는지 확인.

L4(CAD 매칭)는 실물 부품+STL 쌍이 필요하므로 별도 테스트.

실행 (Mac, D435 연결):
    cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/
    source .venv/binpick/bin/activate

    # 라이브 촬영 + 테스트 + 프레임 저장:
    sudo .venv/binpick/bin/python bin_picking/tests/test_d435_realworld.py --live

    # 저장된 프레임으로 재테스트 (카메라 불필요):
    python bin_picking/tests/test_d435_realworld.py --load

    # 저장된 프레임 경로 직접 지정:
    python bin_picking/tests/test_d435_realworld.py --load --frame-dir path/to/frames

옵션:
    --live          D435 라이브 캡처
    --load          저장된 프레임 로드
    --frame-dir DIR 프레임 저장/로드 경로 (기본: bin_picking/models/d435_realworld/)
    --depth-min M   최소 depth (m, 기본 0.15)
    --depth-max M   최대 depth (m, 기본 1.5)
    --no-viz        시각화 건너뛰기 (헤드리스 환경)
"""

import sys
import os
import time
import argparse
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
)
from bin_picking.src.preprocessing.cloud_filter import CloudFilter
from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter


def parse_args():
    parser = argparse.ArgumentParser(description="D435 실데이터 L1~L3 테스트")
    parser.add_argument("--live", action="store_true", help="D435 라이브 캡처")
    parser.add_argument("--load", action="store_true", help="저장된 프레임 로드")
    parser.add_argument(
        "--frame-dir",
        default=os.path.join(PROJECT_ROOT, "bin_picking", "models", "d435_realworld"),
        help="프레임 저장/로드 경로",
    )
    parser.add_argument("--depth-min", type=float, default=0.15, help="최소 depth (m)")
    parser.add_argument("--depth-max", type=float, default=1.5, help="최대 depth (m)")
    parser.add_argument("--no-viz", action="store_true", help="시각화 건너뛰기")
    return parser.parse_args()


# ── L1: 영상 취득 ──────────────────────────────────────────────

def step_l1_capture(args) -> CapturedFrames:
    """L1: D435 캡처 또는 저장된 프레임 로드."""
    print("\n" + "=" * 60)
    print("[L1] 영상 취득")
    print("=" * 60)

    if args.load:
        print(f"  모드: LOAD ({args.frame_dir}/)")
        if not os.path.isdir(args.frame_dir):
            print(f"  [ERROR] 프레임 디렉토리 없음: {args.frame_dir}")
            print("  먼저 --live로 프레임을 저장하세요.")
            sys.exit(1)
        frames = RealSenseCapture.load_frames(args.frame_dir)
    elif args.live:
        print("  모드: LIVE (RealSense D435)")
        cap = RealSenseCapture(
            width=640, height=480, fps=30,
            depth_min=args.depth_min, depth_max=args.depth_max,
        )
        cap.start()
        # 자동 노출 안정화 (30프레임)
        print("  자동 노출 안정화 (30프레임)...")
        for _ in range(30):
            cap.capture()
        frames = cap.capture()
        cap.stop()

        # 프레임 저장
        print(f"  프레임 저장 → {args.frame_dir}/")
        frames.save(args.frame_dir)
    else:
        print("  [ERROR] --live 또는 --load를 지정하세요.")
        sys.exit(1)

    # 기본 정보 출력
    valid = np.count_nonzero(frames.depth_map > 0)
    total = frames.depth_map.shape[0] * frames.depth_map.shape[1]
    depth_valid = frames.depth_map[frames.depth_map > 0]

    print(f"  depth: {frames.depth_map.shape} ({frames.depth_map.dtype})")
    print(f"  color: {frames.color_image.shape} ({frames.color_image.dtype})")
    print(f"  intrinsics: fx={frames.intrinsics.fx:.1f}, fy={frames.intrinsics.fy:.1f}")
    print(f"  유효 depth: {valid:,}/{total:,} ({valid/total*100:.0f}%)")
    if len(depth_valid) > 0:
        print(f"  depth range: {depth_valid.min()}~{depth_valid.max()} mm")
    print("  [PASS] L1")
    return frames


# ── depth 품질 분석 ────────────────────────────────────────────

def analyze_depth_quality(frames: CapturedFrames):
    """depth 품질 상세 분석."""
    print("\n" + "=" * 60)
    print("[분석] Depth 품질")
    print("=" * 60)

    d = frames.depth_map.astype(np.float64)
    valid_mask = d > 0
    d_valid = d[valid_mask]

    if len(d_valid) == 0:
        print("  [ERROR] 유효 depth 없음")
        return

    total = d.shape[0] * d.shape[1]

    # 기본 통계
    print(f"  해상도: {d.shape[1]}x{d.shape[0]}")
    print(f"  유효 픽셀: {len(d_valid):,}/{total:,} ({len(d_valid)/total*100:.1f}%)")
    print(f"  무효 픽셀: {total - len(d_valid):,} ({(total - len(d_valid))/total*100:.1f}%)")

    # depth 분포
    print(f"\n  Depth 분포 (mm):")
    print(f"    min:    {d_valid.min():.0f}")
    print(f"    max:    {d_valid.max():.0f}")
    print(f"    mean:   {d_valid.mean():.0f}")
    print(f"    median: {np.median(d_valid):.0f}")
    print(f"    std:    {d_valid.std():.1f}")

    # 거리 대역별 분포
    print(f"\n  거리 대역별:")
    bands = [(0, 300), (300, 500), (500, 800), (800, 1200), (1200, 2000), (2000, 5000)]
    for lo, hi in bands:
        count = np.sum((d_valid >= lo) & (d_valid < hi))
        pct = count / len(d_valid) * 100
        if count > 0:
            print(f"    {lo:>5}~{hi:<5}mm: {count:>7,} ({pct:5.1f}%)")

    # 무효 영역 분석 (depth=0인 부분)
    invalid_mask = ~valid_mask
    invalid_count = invalid_mask.sum()
    if invalid_count > 0:
        # 무효 픽셀의 공간 분포 (상/하/좌/우 사분면)
        H, W = d.shape
        quadrants = {
            "상단": invalid_mask[:H//2, :].sum(),
            "하단": invalid_mask[H//2:, :].sum(),
            "좌측": invalid_mask[:, :W//2].sum(),
            "우측": invalid_mask[:, W//2:].sum(),
        }
        print(f"\n  무효 픽셀 분포:")
        for name, cnt in quadrants.items():
            print(f"    {name}: {cnt:,} ({cnt/invalid_count*100:.0f}%)")

    print("  [PASS] 품질 분석 완료")


# ── L1→PointCloud 변환 ────────────────────────────────────────

def step_l1_to_pointcloud(frames: CapturedFrames, args) -> "o3d.geometry.PointCloud":
    """CapturedFrames → Open3D PointCloud."""
    print("\n" + "=" * 60)
    print("[L1→PC] PointCloud 변환")
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
        depth_min=args.depth_min,
        depth_max=args.depth_max,
    )
    elapsed = time.time() - t0

    n_pts = len(pcd.points)
    has_color = len(pcd.colors) > 0
    print(f"  포인트 수: {n_pts:,}")
    print(f"  컬러: {'있음' if has_color else '없음'}")
    print(f"  변환 시간: {elapsed:.3f}s")

    if n_pts > 0:
        pts = np.asarray(pcd.points)
        print(f"  X range: {pts[:,0].min():.3f} ~ {pts[:,0].max():.3f} m")
        print(f"  Y range: {pts[:,1].min():.3f} ~ {pts[:,1].max():.3f} m")
        print(f"  Z range: {pts[:,2].min():.3f} ~ {pts[:,2].max():.3f} m")

    assert n_pts > 0, "포인트가 0개입니다"
    print("  [PASS] PointCloud 변환")
    return pcd


# ── L2: 전처리 ────────────────────────────────────────────────

def step_l2_preprocess(pcd: "o3d.geometry.PointCloud") -> "o3d.geometry.PointCloud":
    """L2: 전처리 (이상치 제거 → 다운샘플 → 바닥면 제거 → 법선 추정)."""
    print("\n" + "=" * 60)
    print("[L2] 전처리")
    print("=" * 60)

    t0 = time.time()

    # D435 실데이터용 파라미터 (Blaze-112 프리셋보다 약간 관대하게)
    cf = CloudFilter(
        voxel_size=0.003,           # 3mm (실데이터 노이즈 감안)
        sor_nb_neighbors=20,
        sor_std_ratio=2.0,
        normal_radius=0.01,         # 10mm
        normal_max_nn=30,
        plane_distance=0.01,        # 10mm (D435 depth 노이즈 감안)
        plane_iterations=2000,
    )
    pcd_objects = cf.process(pcd)

    elapsed = time.time() - t0

    cf.print_stats()
    print(f"  처리 시간: {elapsed:.3f}s")
    print("  [PASS] L2 전처리")
    return pcd_objects


# ── L3: 분할 ──────────────────────────────────────────────────

def step_l3_segment(pcd: "o3d.geometry.PointCloud") -> list:
    """L3: DBSCAN 클러스터링."""
    print("\n" + "=" * 60)
    print("[L3] DBSCAN 분할")
    print("=" * 60)

    t0 = time.time()

    # 일반 사물 테스트용 파라미터 (부품보다 크기 범위 넓게)
    seg = DBSCANSegmenter(
        eps=0.015,                  # 15mm (사물 간격이 부품보다 넓을 수 있음)
        min_points=50,
        min_cluster_points=30,
        max_cluster_points=500000,
        min_size_mm=10.0,           # 10mm 이상
        max_size_mm=500.0,          # 500mm 이하
    )
    clusters = seg.segment(pcd)

    elapsed = time.time() - t0

    seg.print_stats()
    print(f"\n  클러스터 목록:")
    seg.print_clusters(clusters)
    print(f"\n  분할 시간: {elapsed:.3f}s")

    if len(clusters) > 0:
        print("  [PASS] L3 분할")
    else:
        print("  [WARN] 유효 클러스터 0개 — 사물이 카메라 시야에 있는지 확인")
    return clusters


# ── 시각화 ────────────────────────────────────────────────────

def visualize_results(pcd_raw, pcd_processed, clusters, args):
    """결과 시각화 (Open3D viewer)."""
    if args.no_viz:
        print("\n  [SKIP] 시각화 건너뛰기 (--no-viz)")
        return

    print("\n" + "=" * 60)
    print("[VIZ] 시각화")
    print("=" * 60)

    # 1. 원본 포인트 클라우드
    print("  1/3: 원본 PointCloud (창 닫으면 다음 진행)")
    o3d.visualization.draw_geometries(
        [pcd_raw], window_name="L1: Raw PointCloud",
        width=1024, height=768,
    )

    # 2. 전처리 후
    print("  2/3: 전처리 후 (바닥 제거)")
    o3d.visualization.draw_geometries(
        [pcd_processed], window_name="L2: After Preprocessing",
        width=1024, height=768,
    )

    # 3. 클러스터별 색상
    if len(clusters) > 0:
        print(f"  3/3: 클러스터 {len(clusters)}개 (색상 구분)")
        colors = [
            [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [1, 1, 0], [1, 0, 1], [0, 1, 1],
            [0.5, 0, 0], [0, 0.5, 0], [0, 0, 0.5],
            [1, 0.5, 0], [0.5, 0, 1], [0, 1, 0.5],
        ]
        geometries = []
        for i, cluster in enumerate(clusters):
            pcd_c = cluster.pcd
            color = colors[i % len(colors)]
            pcd_c.paint_uniform_color(color)
            geometries.append(pcd_c)
        o3d.visualization.draw_geometries(
            geometries, window_name="L3: Clusters",
            width=1024, height=768,
        )
    else:
        print("  3/3: 클러스터 없음 — 시각화 건너뛰기")


# ── main ──────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not args.live and not args.load:
        print("[ERROR] --live 또는 --load를 지정하세요.")
        print("  예: sudo .venv/binpick/bin/python bin_picking/tests/test_d435_realworld.py --live")
        sys.exit(1)

    print("=" * 60)
    print("D435 실데이터 테스트 (L1→L2→L3)")
    print(f"모드: {'LIVE' if args.live else 'LOAD'}")
    print(f"depth 범위: {args.depth_min}~{args.depth_max}m")
    print("=" * 60)

    t_total = time.time()

    # L1: 영상 취득
    frames = step_l1_capture(args)

    # Depth 품질 분석
    analyze_depth_quality(frames)

    # L1→PC: PointCloud 변환
    pcd_raw = step_l1_to_pointcloud(frames, args)

    # L2: 전처리
    pcd_processed = step_l2_preprocess(pcd_raw)

    # L3: 분할
    clusters = step_l3_segment(pcd_processed)

    elapsed = time.time() - t_total
    print("\n" + "=" * 60)
    print(f"전체 테스트 완료: {elapsed:.2f}s")
    print(f"  L1 프레임: {frames.depth_map.shape}")
    print(f"  L1→PC: {len(pcd_raw.points):,} pts")
    print(f"  L2 전처리 후: {len(pcd_processed.points):,} pts")
    print(f"  L3 클러스터: {len(clusters)}개")
    for c in clusters:
        print(f"    {c}")
    print("=" * 60)

    # 시각화
    visualize_results(pcd_raw, pcd_processed, clusters, args)


if __name__ == "__main__":
    main()
