"""
실제 STL 레퍼런스 기반 E2E 매칭 테스트
========================================

cad_library.py로 빌드한 실제 46종 레퍼런스 캐시를 로드하여,
합성 씬(STL에서 포인트 샘플링 + 랜덤 자세 + 노이즈)에 대해
L2→L3→L4 전체 파이프라인을 검증한다.

테스트 시나리오:
  1. CADLibrary에서 실제 레퍼런스 캐시 로드
  2. STL에서 5종 부품을 선택하여 합성 씬 생성
     - 랜덤 6DoF 자세 (회전 + 이동)
     - ToF 카메라 노이즈 (σ=0.3mm, Blaze-112 수준)
     - 부분 가시성 시뮬레이션 (70% 가시)
  3. L2 전처리 (CloudFilter)
  4. L3 분할 (DBSCANSegmenter)
  5. L4 인식+자세 (SizeFilter → PoseEstimator)
  6. 결과 검증: 인식률, 자세 정밀도, 처리 시간

성능 목표:
  - 인식률 >= 80% (5종 중 4종 이상 ACCEPT)
  - 부품당 매칭 시간 <= 2.0초
  - RMSE <= 3mm

실행 (Mac에서):
  source .venv/binpick/bin/activate
  python bin_picking/tests/test_e2e_cad_matching.py
  python bin_picking/tests/test_e2e_cad_matching.py --no-vis    # 시각화 없이
  python bin_picking/tests/test_e2e_cad_matching.py --parts 10  # 부품 수 변경
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

# 프로젝트 루트를 path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import open3d as o3d
import trimesh

from bin_picking.src.recognition.cad_library import CADLibrary
from bin_picking.src.recognition.pose_estimator import PoseEstimator
from bin_picking.src.recognition.size_filter import SizeFilter
from bin_picking.src.preprocessing.cloud_filter import CloudFilter
from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter


# ============================================================
# 파라미터
# ============================================================
VOXEL_SIZE = 0.002       # 2mm
NOISE_SIGMA = 0.0003     # 0.3mm (Blaze-112 ToF 수준)
SCENE_SPACING = 0.15     # 부품 간 간격 150mm (DBSCAN 분리 보장)
SAMPLE_POINTS = 5000     # 씬 부품당 포인트 수
FLOOR_POINTS = 10000     # 바닥면 포인트 (RANSAC이 확실히 잡도록)

# 난이도 프리셋: 단계별 검증
DIFFICULTY_PRESETS = {
    "easy": {
        "visibility": 1.0,       # 100% 가시 (가림 없음)
        "max_rotation_deg": 15,  # ±15도 (약간의 기울임)
        "description": "가림 없음 + 약간 회전",
    },
    "medium": {
        "visibility": 0.85,      # 85% 가시
        "max_rotation_deg": 30,  # ±30도
        "description": "약간 가림 + 중간 회전",
    },
    "hard": {
        "visibility": 0.70,      # 70% 가시
        "max_rotation_deg": 45,  # ±45도
        "description": "가림 + 큰 회전 (실전 시나리오)",
    },
}
DEFAULT_DIFFICULTY = "easy"  # 먼저 easy에서 PASS 확인

# 테스트에 사용할 부품 (다양한 크기/형상 선택)
DEFAULT_TEST_PARTS = [
    "01_sol_block_a",           # 55×11.5×45mm — 소형 블록
    "07_guide_paper_l",         # 69×116×25.5mm — 중형 가이드
    "17_mks_holder",            # 131×11×82.5mm — 길쭉한 홀더
    "bracket_sensor1",          # 15×26×42mm — 소형 브래킷
    "guide_paper_roll_cover_left",  # 28×48×59mm — 중형 커버
]


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def generate_synthetic_scene(
    cad_library: CADLibrary,
    part_names: List[str],
    noise_sigma: float = NOISE_SIGMA,
    visibility: float = 1.0,
    max_rotation_deg: float = 15,
) -> Tuple[o3d.geometry.PointCloud, List[Dict[str, Any]]]:
    """실제 STL에서 합성 빈피킹 씬을 생성한다.

    Args:
        cad_library: CADLibrary 인스턴스
        part_names: 씬에 배치할 부품 이름 리스트
        noise_sigma: 가우시안 노이즈 표준편차 (미터)
        visibility: 가시 비율 (0.0~1.0, 1.0=전체 가시)
        max_rotation_deg: 최대 회전 각도 (도)

    Returns:
        (scene_pcd, ground_truth): 합성 씬 포인트 클라우드, 부품별 정답 정보
    """
    np.random.seed(42)
    all_points = []
    ground_truth = []

    for i, name in enumerate(part_names):
        stl_path = cad_library.cad_dir / f"{name}.stl"
        if not stl_path.exists():
            print(f"  [경고] STL 없음: {name} → 건너뜀")
            continue

        # STL 로드
        mesh = trimesh.load(str(stl_path))
        if not isinstance(mesh, trimesh.Trimesh):
            print(f"  [경고] 유효하지 않은 메쉬: {name} → 건너뜀")
            continue

        # mm → m 변환
        if max(mesh.bounding_box.extents) > 1.0:
            mesh.apply_scale(0.001)

        # 표면 샘플링
        points, _ = trimesh.sample.sample_surface(mesh, SAMPLE_POINTS)

        # 부분 가시성: 상위 방향에서 보이는 점만 (z축 기준 상위 visibility%)
        if visibility < 1.0:
            z_vals = points[:, 2]
            z_threshold = np.percentile(z_vals, (1.0 - visibility) * 100)
            visible_mask = z_vals >= z_threshold
            points = points[visible_mask]

        # 랜덤 회전
        max_rad = np.radians(max_rotation_deg)
        euler = np.random.uniform(-max_rad, max_rad, 3)
        R = o3d.geometry.PointCloud()
        R_mat = R.get_rotation_matrix_from_xyz(euler)

        # 회전 적용 (원점 기준)
        center = points.mean(axis=0)
        points_centered = points - center
        points_rotated = (R_mat @ points_centered.T).T

        # 빈 내 배치: 격자 형태로 배치
        row = i // 3
        col = i % 3
        offset = np.array([
            col * SCENE_SPACING,
            row * SCENE_SPACING,
            0.06 + np.random.uniform(0, 0.01)  # 빈 바닥(z=0)에서 60mm 위
        ])
        points_placed = points_rotated + offset

        # ToF 노이즈 추가
        noise = np.random.normal(0, noise_sigma, size=points_placed.shape)
        points_noisy = points_placed + noise

        all_points.append(points_noisy)

        # 정답 정보
        T_gt = np.eye(4)
        T_gt[:3, :3] = R_mat
        T_gt[:3, 3] = offset

        ground_truth.append({
            "name": name,
            "transformation": T_gt,
            "offset": offset,
            "euler": euler,
            "n_points": len(points_noisy),
        })

        extent_mm = mesh.bounding_box.extents * 1000
        print(f"  [{i+1}] {name:>35}  "
              f"pts={len(points_noisy):>4}  "
              f"bbox=({extent_mm[0]:.0f}×{extent_mm[1]:.0f}×{extent_mm[2]:.0f})mm  "
              f"pos=({offset[0]*1000:.0f}, {offset[1]*1000:.0f}, {offset[2]*1000:.0f})mm")

    # 빈 바닥면 추가 (RANSAC 제거 테스트용)
    # 바닥 포인트를 부품보다 많게 → RANSAC이 바닥을 확실히 잡음
    n_floor = FLOOR_POINTS
    floor_x = np.random.uniform(-0.10, 0.50, n_floor)
    floor_y = np.random.uniform(-0.10, 0.40, n_floor)
    floor_z = np.random.normal(0.0, 0.0003, n_floor)  # z≈0 평면 + 미세 노이즈
    floor_points = np.column_stack([floor_x, floor_y, floor_z])
    all_points.append(floor_points)
    print(f"  [바닥] 평면 포인트 {n_floor}개 추가 (RANSAC 바닥 감지 보장)")

    # 합성 씬 생성
    scene_points = np.vstack(all_points)
    scene_pcd = o3d.geometry.PointCloud()
    scene_pcd.points = o3d.utility.Vector3dVector(scene_points)

    return scene_pcd, ground_truth


def run_pipeline(
    scene_pcd: o3d.geometry.PointCloud,
    reference_cache: Dict[str, Dict[str, Any]],
    size_filter: SizeFilter,
    estimator: PoseEstimator,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """L2→L3→L4 파이프라인을 실행한다.

    Returns:
        (results, timings): 클러스터별 매칭 결과, 단계별 소요 시간
    """
    timings = {}

    # ============================================================
    # L2: 전처리
    # ============================================================
    t0 = time.time()
    roi_min = np.array([-0.15, -0.15, -0.01])
    roi_max = np.array([0.50, 0.40, 0.20])
    cf = CloudFilter(
        voxel_size=VOXEL_SIZE,  # 2mm (부품 디테일 유지)
        sor_nb_neighbors=20,
        sor_std_ratio=2.0,
        plane_distance=0.003,  # 3mm (합성 씬 바닥 노이즈 σ=0.5mm → 3σ)
        roi_min=roi_min,
        roi_max=roi_max,
    )

    filtered = cf.process(scene_pcd)
    timings["L2_preprocess"] = time.time() - t0

    n_before = len(scene_pcd.points)
    n_after = len(filtered.points)
    print(f"  L2 전처리: {n_before:,} → {n_after:,} pts ({timings['L2_preprocess']:.3f}s)")
    cf.print_stats()

    # ============================================================
    # L3: 분할
    # ============================================================
    t0 = time.time()
    segmenter = DBSCANSegmenter(eps=0.010, min_points=30)  # eps=10mm, 최소 30점
    clusters = segmenter.segment(filtered)
    timings["L3_segment"] = time.time() - t0

    print(f"  L3 분할: {len(clusters)} 클러스터 ({timings['L3_segment']:.3f}s)")
    for j, c in enumerate(clusters):
        ext = c.extent_mm
        print(f"    클러스터 {j}: {c.n_points:>4} pts, "
              f"bbox=({ext[0]:.0f}×{ext[1]:.0f}×{ext[2]:.0f})mm")

    # ============================================================
    # L4: 인식 + 자세 추정
    # ============================================================
    results = []
    total_match_time = 0.0

    for j, cluster in enumerate(clusters):
        # L4a: SizeFilter
        t_filter = time.time()
        candidates = size_filter.filter_candidates(cluster.pcd)
        t_filter_elapsed = time.time() - t_filter

        if not candidates:
            candidates = list(reference_cache.keys())
            filter_note = f"fallback 전체 {len(candidates)}종"
        else:
            filter_note = f"{len(candidates)} 후보"

        # L4b: PoseEstimator
        t_match = time.time()
        match_results = estimator.match_against_references(
            cluster.pcd, reference_cache, candidate_names=candidates[:10]
        )
        t_match_elapsed = time.time() - t_match
        total_match_time += t_match_elapsed

        if match_results:
            best = match_results[0]
            decision = estimator.evaluate(best)
            pose = estimator.extract_pose(best["transformation"])

            results.append({
                "cluster_id": j,
                "matched_name": best["name"],
                "fitness": best["fitness"],
                "rmse": best["rmse"],
                "decision": decision,
                "pose": pose,
                "transformation": best["transformation"],
                "time_filter": t_filter_elapsed,
                "time_match": t_match_elapsed,
                "n_candidates": len(candidates),
                "n_cluster_pts": cluster.n_points,
                "cluster_extent_mm": cluster.extent_mm,
            })

            print(f"    클러스터 {j} → {best['name']:>35}  "
                  f"fitness={best['fitness']:.4f}  "
                  f"RMSE={best['rmse']*1000:.2f}mm  "
                  f"{decision}  "
                  f"({filter_note}, {t_match_elapsed:.2f}s)")
        else:
            results.append({
                "cluster_id": j,
                "matched_name": "---",
                "fitness": 0.0,
                "rmse": float("inf"),
                "decision": "REJECT",
                "pose": None,
                "transformation": None,
                "time_filter": t_filter_elapsed,
                "time_match": t_match_elapsed,
                "n_candidates": 0,
                "n_cluster_pts": cluster.n_points,
                "cluster_extent_mm": cluster.extent_mm,
            })
            print(f"    클러스터 {j} → 매칭 실패")

    timings["L4_total_match"] = total_match_time
    timings["L4_avg_match"] = total_match_time / len(clusters) if clusters else 0

    return results, timings


def evaluate_results(
    results: List[Dict[str, Any]],
    ground_truth: List[Dict[str, Any]],
    timings: Dict[str, float],
) -> Dict[str, Any]:
    """매칭 결과를 정답과 비교하여 평가한다."""

    gt_names = {gt["name"] for gt in ground_truth}
    matched_names = {r["matched_name"] for r in results if r["decision"] == "ACCEPT"}

    # 정답 부품이 ACCEPT된 매칭 결과에 포함되는지
    correct_matches = gt_names & matched_names
    n_gt = len(ground_truth)
    n_detected = len([r for r in results if r["decision"] == "ACCEPT"])
    n_correct = len(correct_matches)

    # 미검출 부품
    missed = gt_names - matched_names

    # 오검출 (ACCEPT인데 정답에 없는 매칭)
    false_positives = matched_names - gt_names

    # 시간 통계
    match_times = [r["time_match"] for r in results]
    avg_time = np.mean(match_times) if match_times else 0
    max_time = max(match_times) if match_times else 0

    # RMSE 통계
    rmse_values = [r["rmse"] * 1000 for r in results if r["decision"] == "ACCEPT"]
    avg_rmse = np.mean(rmse_values) if rmse_values else 0
    max_rmse = max(rmse_values) if rmse_values else 0

    return {
        "n_gt_parts": n_gt,
        "n_clusters": len(results),
        "n_detected": n_detected,
        "n_correct": n_correct,
        "recognition_rate": n_correct / n_gt * 100 if n_gt > 0 else 0,
        "missed": sorted(missed),
        "false_positives": sorted(false_positives),
        "avg_match_time": avg_time,
        "max_match_time": max_time,
        "avg_rmse_mm": avg_rmse,
        "max_rmse_mm": max_rmse,
        "timings": timings,
    }


# ============================================================
# main
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="실제 STL 레퍼런스 기반 E2E 매칭 테스트"
    )
    parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기")
    parser.add_argument("--parts", type=int, default=5, help="테스트 부품 수 (기본 5)")
    parser.add_argument("--all-parts", action="store_true", help="전체 46종에서 랜덤 선택")
    parser.add_argument("--difficulty", type=str, default=DEFAULT_DIFFICULTY,
                        choices=["easy", "medium", "hard"],
                        help="난이도 (기본: easy)")
    args = parser.parse_args()

    difficulty = DIFFICULTY_PRESETS[args.difficulty]
    print(f"  난이도: {args.difficulty} — {difficulty['description']}")

    # ============================================================
    # Step 1: CADLibrary 캐시 로드
    # ============================================================
    print_section("Step 1: CADLibrary 레퍼런스 캐시 로드")

    lib = CADLibrary()
    t0 = time.time()
    reference_cache = lib.load_all()
    load_time = time.time() - t0

    print(f"  로드: {len(reference_cache)}종, {load_time*1000:.0f}ms")

    if not reference_cache:
        print("  [오류] 레퍼런스 캐시가 비어있습니다.")
        print("  먼저 실행: python bin_picking/src/recognition/cad_library.py --build")
        sys.exit(1)

    # SizeFilter 구축
    size_filter = SizeFilter(tolerance=0.5)
    for name, data in reference_cache.items():
        size_filter.add_reference(name, data["bbox_features"])
    print(f"  SizeFilter: {size_filter.reference_count}종 등록")

    # PoseEstimator 생성
    estimator = PoseEstimator(voxel_size=VOXEL_SIZE)
    print(f"  PoseEstimator: voxel={VOXEL_SIZE*1000}mm, "
          f"FPFH radius={estimator.fpfh_radius*1000}mm, "
          f"ICP threshold={estimator.icp_distance*1000}mm")

    # ============================================================
    # Step 2: 테스트 부품 선택
    # ============================================================
    print_section("Step 2: 테스트 부품 선택")

    available = sorted(reference_cache.keys())

    if args.all_parts:
        np.random.seed(42)
        n = min(args.parts, len(available))
        test_parts = list(np.random.choice(available, n, replace=False))
    else:
        test_parts = [p for p in DEFAULT_TEST_PARTS[:args.parts] if p in available]
        if len(test_parts) < args.parts:
            remaining = [p for p in available if p not in test_parts]
            np.random.seed(42)
            extra = list(np.random.choice(
                remaining, min(args.parts - len(test_parts), len(remaining)), replace=False
            ))
            test_parts.extend(extra)

    print(f"  테스트 부품: {len(test_parts)}종")
    for p in test_parts:
        bb = reference_cache[p]["bbox_features"]
        print(f"    {p:>35}  "
              f"bbox=({bb['extent_x']*1000:.0f}×{bb['extent_y']*1000:.0f}×{bb['extent_z']*1000:.0f})mm")

    # ============================================================
    # Step 3: 합성 씬 생성
    # ============================================================
    print_section("Step 3: 합성 빈피킹 씬 생성")

    scene_pcd, ground_truth = generate_synthetic_scene(
        lib, test_parts,
        noise_sigma=NOISE_SIGMA,
        visibility=difficulty["visibility"],
        max_rotation_deg=difficulty["max_rotation_deg"],
    )

    print(f"\n  씬 총 포인트: {len(scene_pcd.points):,}")
    print(f"  부품 {len(ground_truth)}개 + 바닥면")

    # ============================================================
    # Step 4: L2→L3→L4 파이프라인 실행
    # ============================================================
    print_section("Step 4: L2→L3→L4 파이프라인 실행")

    t_pipeline = time.time()
    results, timings = run_pipeline(
        scene_pcd, reference_cache, size_filter, estimator
    )
    timings["total_pipeline"] = time.time() - t_pipeline

    # ============================================================
    # Step 5: 결과 평가
    # ============================================================
    print_section("Step 5: 결과 평가")

    eval_result = evaluate_results(results, ground_truth, timings)

    print(f"  정답 부품:       {eval_result['n_gt_parts']}개")
    print(f"  검출 클러스터:   {eval_result['n_clusters']}개")
    print(f"  ACCEPT:          {eval_result['n_detected']}개")
    print(f"  정답 일치:       {eval_result['n_correct']}/{eval_result['n_gt_parts']} "
          f"({eval_result['recognition_rate']:.0f}%)")

    if eval_result["missed"]:
        print(f"  미검출:          {', '.join(eval_result['missed'])}")
    if eval_result["false_positives"]:
        print(f"  오검출:          {', '.join(eval_result['false_positives'])}")

    print()
    print(f"  매칭 시간 (평균): {eval_result['avg_match_time']:.2f}s")
    print(f"  매칭 시간 (최대): {eval_result['max_match_time']:.2f}s")
    print(f"  RMSE (평균):      {eval_result['avg_rmse_mm']:.2f}mm")
    print(f"  RMSE (최대):      {eval_result['max_rmse_mm']:.2f}mm")

    # ============================================================
    # Step 6: 6DoF 자세 상세
    # ============================================================
    print_section("Step 6: 6DoF 자세 상세")

    print(f"  {'ID':>3} {'매칭 부품':>35} {'위치 (mm)':>30} "
          f"{'오일러 ZYX (deg)':>30} {'판정':>8}")
    print(f"  {'-'*115}")

    for r in results:
        if r["pose"] is None:
            print(f"  {r['cluster_id']:>3} {'REJECTED':>35}")
            continue

        t = r["pose"]["translation_mm"]
        e = r["pose"]["euler_deg"]
        pos_str = f"({t['x']:+7.1f}, {t['y']:+7.1f}, {t['z']:+7.1f})"
        euler_str = f"({e['rz']:+7.1f}, {e['ry']:+7.1f}, {e['rx']:+7.1f})"

        print(f"  {r['cluster_id']:>3} {r['matched_name']:>35} {pos_str:>30} "
              f"{euler_str:>30} {r['decision']:>8}")

    # ============================================================
    # Step 7: 성능 요약 + PASS/FAIL 판정
    # ============================================================
    print_section("Step 7: 성능 요약")

    print(f"  파이프라인 총 시간:  {timings['total_pipeline']:.2f}s")
    print(f"    L2 전처리:         {timings['L2_preprocess']:.3f}s")
    print(f"    L3 분할:           {timings['L3_segment']:.3f}s")
    print(f"    L4 매칭 (총):      {timings['L4_total_match']:.2f}s")
    print(f"    L4 매칭 (평균):    {timings['L4_avg_match']:.2f}s")
    print()

    # 목표 대비 판정
    rate = eval_result["recognition_rate"]
    avg_time = eval_result["avg_match_time"]
    avg_rmse = eval_result["avg_rmse_mm"]

    checks = [
        (rate >= 80, f"인식률 {rate:.0f}% >= 80%", f"인식률 {rate:.0f}% < 80%"),
        (avg_time <= 2.0, f"매칭 시간 {avg_time:.2f}s <= 2.0s", f"매칭 시간 {avg_time:.2f}s > 2.0s"),
        (avg_rmse <= 3.0 or avg_rmse == 0, f"RMSE {avg_rmse:.2f}mm <= 3.0mm", f"RMSE {avg_rmse:.2f}mm > 3.0mm"),
    ]

    all_pass = True
    for passed, pass_msg, fail_msg in checks:
        if passed:
            print(f"  [PASS] {pass_msg}")
        else:
            print(f"  [FAIL] {fail_msg}")
            all_pass = False

    print()
    if all_pass:
        print(f"  === E2E 테스트 PASS ===")
    else:
        print(f"  === E2E 테스트 FAIL — 위 항목 확인 필요 ===")

    # ============================================================
    # 시각화 (선택)
    # ============================================================
    if not args.no_vis:
        print_section("시각화")

        import copy

        vis_geometries = []
        colors = [
            [1, 0, 0], [0, 0.8, 0], [0, 0, 1],
            [1, 0.8, 0], [1, 0, 1], [0, 1, 1],
            [0.5, 0, 0], [0, 0.5, 0], [0, 0, 0.5],
            [0.8, 0.4, 0],
        ]

        # 씬 원본 (회색)
        scene_vis = copy.deepcopy(scene_pcd)
        scene_vis.paint_uniform_color([0.7, 0.7, 0.7])
        vis_geometries.append(scene_vis)

        # 매칭된 레퍼런스 (변환 적용, 색상)
        for i, r in enumerate(results):
            if r["decision"] == "REJECT" or r["matched_name"] not in reference_cache:
                continue

            ref_pcd = copy.deepcopy(reference_cache[r["matched_name"]]["pcd_down"])
            ref_pcd.transform(r["transformation"])
            ref_pcd.paint_uniform_color(colors[i % len(colors)])
            vis_geometries.append(ref_pcd)

        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.03)
        vis_geometries.append(coord)

        o3d.visualization.draw_geometries(
            vis_geometries,
            window_name="E2E CAD Matching: Scene + Matched References",
            width=1280, height=960,
        )
    else:
        print("\n  --no-vis 모드: 시각화 건너뜀")

    print(f"\n{'='*70}")
    print("  E2E CAD 매칭 테스트 완료!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
