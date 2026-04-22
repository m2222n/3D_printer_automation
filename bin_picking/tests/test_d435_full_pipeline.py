"""
D435 실데이터 Full Pipeline 테스트 — L1→L2→L3→L4→L5→L6
=========================================================
D435로 촬영한 실데이터에서 전체 파이프라인을 실행하여:
  - CAD에 없는 물체가 REJECT 되는지 확인
  - L4 매칭 결과 (fitness, RMSE, decision) 분석
  - L5 그래스프 계획 + L6 통신 준비 상태 검증

기존 test_d435_realworld.py는 L1~L3만 테스트했으나,
이 스크립트는 L4(CAD 매칭) + L5 + L6까지 full pipeline 실행.

실행 (Mac, D435 연결):
    cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/
    source .venv/binpick/bin/activate

    # D435 라이브 촬영 + full pipeline:
    sudo .venv/binpick/bin/python bin_picking/tests/test_d435_full_pipeline.py --live --no-vis

    # 저장된 프레임으로 (카메라 불필요):
    python bin_picking/tests/test_d435_full_pipeline.py --load --no-vis

    # 저장된 프레임 경로 지정:
    python bin_picking/tests/test_d435_full_pipeline.py --load --frame-dir path/to/frames --no-vis

    # 프레임 저장 + full pipeline:
    sudo .venv/binpick/bin/python bin_picking/tests/test_d435_full_pipeline.py --live --save --no-vis
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

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
from bin_picking.src.recognition.cad_library import CADLibrary
from bin_picking.src.recognition.pose_estimator import PoseEstimator
from bin_picking.src.recognition.size_filter import SizeFilter
from bin_picking.src.preprocessing.cloud_filter import CloudFilter
from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter
from bin_picking.src.grasping.grasp_planner import GraspPlanner


DEFAULT_FRAME_DIR = os.path.join(PROJECT_ROOT, "bin_picking", "models", "d435_frames")


def parse_args():
    parser = argparse.ArgumentParser(description="D435 실데이터 Full Pipeline 테스트 (L1~L6)")
    parser.add_argument("--live", action="store_true", help="D435 라이브 캡처")
    parser.add_argument("--load", action="store_true", help="저장된 프레임 로드")
    parser.add_argument("--save", action="store_true", help="라이브 프레임 저장 (--live와 함께)")
    parser.add_argument(
        "--frame-dir", default=DEFAULT_FRAME_DIR,
        help=f"프레임 저장/로드 경로 (기본: {DEFAULT_FRAME_DIR})",
    )
    parser.add_argument("--depth-min", type=float, default=0.15, help="최소 depth (m)")
    parser.add_argument("--depth-max", type=float, default=1.5, help="최대 depth (m)")
    parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기")
    parser.add_argument("--top-k", type=int, default=1, help="클러스터별 상위 K개 매칭 (기본 1)")
    parser.add_argument(
        "--only", default=None,
        help="특정 키워드로 후보 제한 (쉼표 구분). 예: --only bracket,brkt "
             "설정 시 SizeFilter 우회하고 매칭된 레퍼런스만 후보로 사용.",
    )
    return parser.parse_args()


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ── L1: 영상 취득 ─────────────────────────────────────────────────

def step_l1(args) -> CapturedFrames:
    """L1: D435 캡처 또는 저장된 프레임 로드."""
    print_section("L1: 영상 취득")

    if args.load:
        print(f"  모드: LOAD ({args.frame_dir}/)")
        if not os.path.isdir(args.frame_dir):
            print(f"  [ERROR] 프레임 디렉토리 없음: {args.frame_dir}")
            print(f"  먼저 --live --save 로 프레임을 저장하세요.")
            sys.exit(1)
        frames = RealSenseCapture.load_frames(args.frame_dir)
    elif args.live:
        print("  모드: LIVE (RealSense D435)")
        cap = RealSenseCapture(
            width=640, height=480, fps=30,
            depth_min=args.depth_min, depth_max=args.depth_max,
        )
        cap.start()
        print("  자동 노출 안정화 (30프레임)...")
        for _ in range(30):
            cap.capture()
        frames = cap.capture()
        cap.stop()

        if args.save:
            print(f"  프레임 저장 → {args.frame_dir}/")
            frames.save(args.frame_dir)
    else:
        print("  [ERROR] --live 또는 --load를 지정하세요.")
        sys.exit(1)

    valid = np.count_nonzero(frames.depth_map > 0)
    total = frames.depth_map.shape[0] * frames.depth_map.shape[1]
    print(f"  depth: {frames.depth_map.shape}, 유효 {valid:,}/{total:,} ({valid/total*100:.0f}%)")
    print(f"  color: {frames.color_image.shape}")
    print(f"  intrinsics: fx={frames.intrinsics.fx:.1f}, fy={frames.intrinsics.fy:.1f}")

    nonzero = frames.depth_map[frames.depth_map > 0]
    if nonzero.size > 0:
        depth_m = nonzero.astype(float) / frames.depth_scale
        print(f"  depth 범위: min={depth_m.min():.2f}m  "
              f"median={np.median(depth_m):.2f}m  max={depth_m.max():.2f}m")
        in_range = ((depth_m >= args.depth_min) & (depth_m <= args.depth_max)).sum()
        print(f"  범위 내({args.depth_min}~{args.depth_max}m): {in_range:,} pts "
              f"({in_range/depth_m.size*100:.0f}%)")
    return frames


def frames_to_pointcloud(frames: CapturedFrames, args) -> o3d.geometry.PointCloud:
    """CapturedFrames → Open3D PointCloud."""
    t0 = time.time()
    pcd = depth_to_pointcloud(
        depth_map=frames.depth_map,
        fx=frames.intrinsics.fx, fy=frames.intrinsics.fy,
        cx=frames.intrinsics.cx, cy=frames.intrinsics.cy,
        color_image=frames.color_image,
        depth_scale=frames.depth_scale,
        depth_min=args.depth_min, depth_max=args.depth_max,
    )
    elapsed = time.time() - t0
    print(f"  PointCloud: {len(pcd.points):,} pts ({elapsed:.3f}s)")
    return pcd


# ── ROI 자동 계산 ─────────────────────────────────────────────────

def compute_auto_roi(pcd: o3d.geometry.PointCloud, margin: float = 0.02):
    """포인트 클라우드 범위에서 ROI를 자동 계산한다.

    카메라 좌표계(z=카메라로부터의 거리) 기준 — 가까운 물체가 z 최소.
    ROI는 xyz 전체 범위를 margin만큼만 확장 (바닥 휴리스틱 없음 —
    바닥 제거는 RANSAC이 담당).
    """
    pts = np.asarray(pcd.points)
    roi_min = pts.min(axis=0) - margin
    roi_max = pts.max(axis=0) + margin

    return {
        "min": roi_min.tolist(),
        "max": roi_max.tolist(),
    }


# ── Full Pipeline 실행 ────────────────────────────────────────────

def run_full_pipeline(pcd: o3d.geometry.PointCloud, args):
    """L2→L3→L4→L5 full pipeline."""

    timings = {}
    t_total = time.time()

    # --- 레퍼런스 캐시 로드 ---
    print_section("레퍼런스 캐시 로드")
    t0 = time.time()
    cad_library = CADLibrary()
    reference_cache = cad_library.load_all()
    if not reference_cache:
        print("  [ERROR] 레퍼런스 캐시 없음. 먼저 cad_library.py --build 실행")
        sys.exit(1)
    print(f"  {len(reference_cache)}종 로드 ({(time.time()-t0)*1000:.0f}ms)")

    # SizeFilter
    size_filter = SizeFilter(tolerance=0.5)
    for name, data in reference_cache.items():
        size_filter.add_reference(name, data["bbox_features"])

    # PoseEstimator
    estimator = PoseEstimator(voxel_size=0.002)

    # GraspPlanner
    grasp_planner = GraspPlanner()
    print(f"  그래스프 DB: {grasp_planner.part_count}종")

    # --- ROI 자동 계산 ---
    auto_roi = compute_auto_roi(pcd)
    print(f"\n  자동 ROI: x=[{auto_roi['min'][0]:.3f}, {auto_roi['max'][0]:.3f}], "
          f"y=[{auto_roi['min'][1]:.3f}, {auto_roi['max'][1]:.3f}], "
          f"z=[{auto_roi['min'][2]:.3f}, {auto_roi['max'][2]:.3f}]")

    # --- L2: 전처리 ---
    print_section("L2: 전처리")
    t0 = time.time()
    cloud_filter = CloudFilter(
        voxel_size=0.003,           # 3mm (D435 실데이터 노이즈 감안)
        sor_nb_neighbors=20,
        sor_std_ratio=2.0,
        normal_radius=0.01,
        normal_max_nn=30,
        plane_distance=0.01,        # 10mm
        plane_iterations=2000,
        roi_min=np.array(auto_roi["min"]),
        roi_max=np.array(auto_roi["max"]),
    )
    filtered = cloud_filter.process(pcd)
    timings["L2"] = time.time() - t0
    cloud_filter.print_stats()
    print(f"  L2 시간: {timings['L2']:.3f}s")

    if len(filtered.points) < 100:
        print("  [WARN] 전처리 후 포인트 부족 (<100). 파이프라인 중단.")
        return None

    # --- L3: 분할 ---
    print_section("L3: DBSCAN 분할")
    t0 = time.time()
    segmenter = DBSCANSegmenter(
        eps=0.015,              # 15mm
        min_points=50,
        min_cluster_points=30,
        max_cluster_points=500000,
        min_size_mm=10.0,
        max_size_mm=500.0,
    )
    clusters = segmenter.segment(filtered)
    timings["L3"] = time.time() - t0
    segmenter.print_stats()
    segmenter.print_clusters(clusters)
    print(f"  L3 시간: {timings['L3']:.3f}s")

    if not clusters:
        print("  [WARN] 클러스터 0개. 파이프라인 중단.")
        return None

    # --- L4: 인식 + 자세 추정 ---
    print_section("L4: CAD 매칭 (FPFH + FGR/RANSAC + ICP)")
    t0 = time.time()
    parts = []

    # --only 키워드 처리
    only_keywords = None
    if args.only:
        only_keywords = [k.strip().lower() for k in args.only.split(",") if k.strip()]
        forced = [
            name for name in reference_cache.keys()
            if any(kw in name.lower() for kw in only_keywords)
        ]
        print(f"  --only {only_keywords} → 후보 {len(forced)}종 강제:")
        for name in forced:
            print(f"    - {name}")

    for i, cluster in enumerate(clusters):
        if only_keywords is not None:
            # SizeFilter 우회
            candidates = forced
        else:
            candidates = size_filter.filter_candidates(cluster.pcd)
            if not candidates:
                candidates = list(reference_cache.keys())

        n_candidates = min(len(candidates), max(10, len(candidates)))

        # PoseEstimator: 1:N 매칭
        match_results = estimator.match_against_references(
            cluster.pcd,
            reference_cache,
            candidate_names=candidates[:n_candidates],
        )

        for rank, mr in enumerate(match_results[:args.top_k]):
            decision = estimator.evaluate(mr)
            pose = estimator.extract_pose(mr["transformation"])

            parts.append({
                "name": mr["name"],
                "pose": pose,
                "fitness": mr["fitness"],
                "rmse": mr["rmse"],
                "decision": decision,
                "transformation": mr["transformation"],
                "cluster_id": i,
                "n_points": cluster.n_points,
                "extent_mm": cluster.extent_mm,
                "rank": rank,
                "n_candidates": n_candidates,
            })

    timings["L4"] = time.time() - t0
    n_accepted = sum(1 for p in parts if p["decision"] == "ACCEPT" and p["rank"] == 0)
    n_rejected = sum(1 for p in parts if p["decision"] == "REJECT" and p["rank"] == 0)
    n_warn = sum(1 for p in parts if p["decision"] == "WARN" and p["rank"] == 0)

    print(f"\n  클러스터 {len(clusters)}개 → 매칭 {len(parts)}건")
    print(f"  ACCEPT: {n_accepted}, WARN: {n_warn}, REJECT: {n_rejected}")
    print(f"  L4 시간: {timings['L4']:.2f}s ({timings['L4']/len(clusters):.2f}s/클러스터)")

    # 상세 결과 (클러스터별 top-K 전체)
    print(f"\n  {'ID':>3} {'Rank':>4} {'부품명':>35} {'Fitness':>8} {'RMSE(mm)':>9} "
          f"{'판정':>8} {'후보':>4} {'포인트':>7}")
    print(f"  {'-'*92}")
    for p in parts:
        marker = "★" if p["rank"] == 0 else " "
        print(f"  {p['cluster_id']:>3} {marker}{p['rank']+1:>3} {p['name']:>35} "
              f"{p['fitness']:>8.4f} {p['rmse']*1000:>9.2f} "
              f"{p['decision']:>8} {p['n_candidates']:>4} {p['n_points']:>7}")

    # --- L5: 그래스프 계획 ---
    print_section("L5: 그래스프 계획")
    t0 = time.time()
    picks = grasp_planner.plan_picks(parts)
    timings["L5"] = time.time() - t0

    if picks:
        print(f"  피킹 계획: {len(picks)}개 (z 높은 순)")
        for i, pick in enumerate(picks):
            pos = pick["position_mm"]
            safe_str = "✅" if pick.get("safe", True) else "⚠️"
            defined = "DB" if pick["defined"] else "기본값"
            print(f"  [{i+1}] {pick['part_name']:>30}  "
                  f"pos=({pos['x']:+7.1f}, {pos['y']:+7.1f}, {pos['z']:+7.1f})mm  "
                  f"grip={pick['gripper_width_mm']}mm/{pick['gripper_force_N']}N  "
                  f"{defined}  {safe_str}")
            warnings = pick.get("warnings", [])
            for w in warnings:
                print(f"       ⚠️ {w}")
    else:
        print("  피킹 대상 없음 (ACCEPT 0건)")

    print(f"  L5 시간: {timings['L5']*1000:.1f}ms")

    # --- 전체 요약 ---
    timings["total"] = time.time() - t_total
    print_section("파이프라인 요약")
    print(f"  입력: {len(pcd.points):,} pts")
    print(f"  L2 전처리: {len(filtered.points):,} pts ({timings['L2']:.3f}s)")
    print(f"  L3 분할: {len(clusters)} 클러스터 ({timings['L3']:.3f}s)")
    print(f"  L4 매칭: ACCEPT {n_accepted} / WARN {n_warn} / REJECT {n_rejected} ({timings['L4']:.2f}s)")
    print(f"  L5 피킹: {len(picks)}건 ({timings['L5']*1000:.1f}ms)")
    print(f"  총 시간: {timings['total']:.2f}s (레퍼런스 로드 제외)")

    # CAD에 없는 물체 분석
    print_section("분석: CAD 미등록 물체 대응")
    for p in parts:
        if p["rank"] > 0:
            continue
        if p["decision"] == "REJECT":
            print(f"  ✅ 클러스터 {p['cluster_id']}: REJECT (fitness={p['fitness']:.4f}, "
                  f"RMSE={p['rmse']*1000:.2f}mm) — 미등록 물체 정상 거부")
        elif p["decision"] == "WARN":
            print(f"  ⚠️ 클러스터 {p['cluster_id']}: WARN (fitness={p['fitness']:.4f}) — "
                  f"모호한 매칭 ({p['name']})")
        else:
            print(f"  📌 클러스터 {p['cluster_id']}: ACCEPT {p['name']} "
                  f"(fitness={p['fitness']:.4f}, RMSE={p['rmse']*1000:.2f}mm)")

    if n_rejected == len(clusters):
        print(f"\n  👍 전체 {len(clusters)}개 클러스터 모두 REJECT — "
              f"CAD 미등록 물체 거부 정상 동작!")
    elif n_accepted > 0:
        print(f"\n  📌 ACCEPT {n_accepted}건 발생 — 일반 사물이 CAD 부품과 우연히 매칭. "
              f"실물 부품 테스트에서 재검증 필요")

    return {
        "parts": parts,
        "picks": picks,
        "clusters": clusters,
        "filtered": filtered,
        "timings": timings,
        "reference_cache": reference_cache,
    }


# ── 시각화 ────────────────────────────────────────────────────────

def visualize(pcd_raw, result, args):
    """매칭 결과 시각화."""
    if args.no_vis or result is None:
        return

    import copy

    print_section("시각화")
    vis = []

    # 씬 (회색)
    scene_vis = copy.deepcopy(pcd_raw)
    scene_vis.paint_uniform_color([0.7, 0.7, 0.7])
    vis.append(scene_vis)

    # 매칭된 레퍼런스 오버레이
    colors = [[1,0,0],[0,0.8,0],[0,0,1],[1,0.8,0],[1,0,1],[0,1,1]]
    ref_cache = result["reference_cache"]
    for i, p in enumerate(result["parts"]):
        if p["rank"] > 0 or p["name"] not in ref_cache:
            continue
        ref = copy.deepcopy(ref_cache[p["name"]]["pcd_down"])
        ref.transform(p["transformation"])
        if p["decision"] == "ACCEPT":
            ref.paint_uniform_color([0, 0.8, 0])   # 초록
        elif p["decision"] == "WARN":
            ref.paint_uniform_color([1, 0.8, 0])   # 노랑
        else:
            ref.paint_uniform_color([1, 0, 0])      # 빨강
        vis.append(ref)

    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.03)
    vis.append(coord)

    o3d.visualization.draw_geometries(
        vis, window_name="D435 Full Pipeline Result",
        width=1280, height=960,
    )


# ── main ──────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not args.live and not args.load:
        print("[ERROR] --live 또는 --load를 지정하세요.")
        print("  예: sudo .venv/binpick/bin/python bin_picking/tests/test_d435_full_pipeline.py --live --no-vis")
        sys.exit(1)

    print("=" * 70)
    print("  D435 실데이터 Full Pipeline 테스트 (L1→L2→L3→L4→L5)")
    print(f"  모드: {'LIVE' if args.live else 'LOAD'}, depth {args.depth_min}~{args.depth_max}m")
    print("=" * 70)

    # L1: 영상 취득
    frames = step_l1(args)

    # PointCloud 변환
    pcd = frames_to_pointcloud(frames, args)

    if len(pcd.points) == 0:
        print("\n[ERROR] PointCloud 0 pts — depth 범위 밖.")
        print(f"  현재 범위: {args.depth_min}~{args.depth_max}m")
        print(f"  위의 'depth 범위' 줄을 확인해서 --depth-min/--depth-max를 맞추거나")
        print(f"  부품 위치를 지정 범위 안으로 조정하세요.")
        sys.exit(1)

    # Full Pipeline (L2~L5)
    result = run_full_pipeline(pcd, args)

    # 시각화
    visualize(pcd, result, args)

    print(f"\n{'='*70}")
    print("  Full Pipeline 테스트 완료!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
