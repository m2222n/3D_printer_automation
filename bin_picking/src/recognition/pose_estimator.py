"""
1:N 매칭 루프 — SizeFilter 후보에 대해 FPFH+RANSAC+ICP 실행
================================================================

SizeFilter로 30종 → 5~8 후보 축소 후,
각 후보 레퍼런스에 대해 FPFH+RANSAC → ICP Point-to-Plane(TukeyLoss)을
순차 실행하고 최적 매칭을 선택한다.

파이프라인: L4 인식/자세 추정
  - FPFH(33D) + RANSAC 초기 정합
  - ICP Point-to-Plane + Robust (TukeyLoss) 정밀 정합
  - 판정: fitness >= 0.3, RMSE <= 3mm

파라미터 (논문 리뷰 결정):
  - voxel_size: 2mm (0.002m)
  - FPFH radius: 10mm (5 x voxel)
  - RANSAC distance threshold: 3mm (1.5 x voxel)
  - ICP distance threshold: 1mm (0.5 x voxel)
  - ICP: Point-to-Plane + TukeyLoss

실행: source .venv/binpick/bin/activate && python bin_picking/src/pose_estimator.py --no-vis
"""

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

# SizeFilter 임포트 (패키지 또는 단독 실행 모두 지원)
try:
    from bin_picking.src.size_filter import SizeFilter, compute_bbox_features, _center_mesh
except ImportError:
    # 단독 실행 시 상대 경로 폴백
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from size_filter import SizeFilter, compute_bbox_features, _center_mesh


# ============================================================
# 0. 빈피킹 파라미터 (실제 SLA 부품 스케일)
# ============================================================
DEFAULT_VOXEL_SIZE = 0.002  # 2mm


# ============================================================
# 1. PoseEstimator 클래스
# ============================================================
class PoseEstimator:
    """1:N 매칭 + 6DoF 자세 추정기.

    FPFH+RANSAC 초기정합 → ICP Point-to-Plane(TukeyLoss) 정밀정합으로
    씬 클러스터를 레퍼런스 모델과 매칭한다.
    """

    def __init__(self, voxel_size: float = DEFAULT_VOXEL_SIZE):
        """
        Args:
            voxel_size: 다운샘플링 복셀 크기 (미터). 기본 2mm.
        """
        self.voxel_size = voxel_size

        # 파생 파라미터 (논문 리뷰 결정)
        self.fpfh_radius = voxel_size * 5        # 10mm
        self.fpfh_max_nn = 100
        self.normal_radius = voxel_size * 4      # 8mm
        self.normal_max_nn = 30
        self.ransac_distance = voxel_size * 1.5  # 3mm
        self.ransac_max_iter = 100_000
        self.ransac_confidence = 0.999
        self.icp_distance = voxel_size * 0.5     # 1mm

        # 판정 임계값
        self.fitness_threshold = 0.3    # 이 이상이면 매칭 수락
        self.rmse_threshold = 0.003     # 3mm 초과하면 거부

        # 카메라 위치 (법선 방향 정렬용 — 위에서 내려다보는 구도)
        self.camera_location = np.array([0.0, 0.0, 0.5])

    # ============================================================
    # 전처리: 다운샘플링 → 법선 → FPFH
    # ============================================================
    def preprocess(
        self, pcd: o3d.geometry.PointCloud
    ) -> Tuple[o3d.geometry.PointCloud, o3d.pipelines.registration.Feature]:
        """포인트클라우드를 다운샘플링하고 법선 + FPFH를 계산한다.

        Args:
            pcd: 입력 포인트클라우드

        Returns:
            (pcd_down, fpfh): 다운샘플링된 클라우드 + FPFH 특징
        """
        pcd_down = pcd.voxel_down_sample(self.voxel_size)

        pcd_down.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.normal_radius, max_nn=self.normal_max_nn
            )
        )
        pcd_down.orient_normals_towards_camera_location(
            camera_location=self.camera_location
        )

        fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            pcd_down,
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.fpfh_radius, max_nn=self.fpfh_max_nn
            ),
        )

        return pcd_down, fpfh

    # ============================================================
    # 등록: FPFH+RANSAC → ICP Point-to-Plane (TukeyLoss)
    # ============================================================
    def register(
        self,
        source_down: o3d.geometry.PointCloud,
        source_fpfh: o3d.pipelines.registration.Feature,
        target_down: o3d.geometry.PointCloud,
        target_fpfh: o3d.pipelines.registration.Feature,
    ) -> Tuple[o3d.pipelines.registration.RegistrationResult, float]:
        """RANSAC 초기 정합 + ICP 정밀 정합을 실행한다.

        Args:
            source_down: 레퍼런스 (다운샘플링됨)
            source_fpfh: 레퍼런스 FPFH
            target_down: 씬 클러스터 (다운샘플링됨)
            target_fpfh: 씬 클러스터 FPFH

        Returns:
            (RegistrationResult, elapsed_seconds): ICP 결과 + 소요 시간
        """
        t0 = time.time()

        # RANSAC — 초기 정합
        result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
            source_down, target_down, source_fpfh, target_fpfh,
            mutual_filter=True,
            max_correspondence_distance=self.ransac_distance,
            estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(
                with_scaling=False
            ),
            ransac_n=3,
            checkers=[
                o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(
                    self.ransac_distance
                ),
                o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            ],
            criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
                max_iteration=self.ransac_max_iter,
                confidence=self.ransac_confidence,
            ),
        )

        # ICP Point-to-Plane + TukeyLoss — 정밀 정합
        loss = o3d.pipelines.registration.TukeyLoss(k=self.icp_distance)
        estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)

        result_icp = o3d.pipelines.registration.registration_icp(
            source_down, target_down,
            max_correspondence_distance=self.icp_distance * 3,
            init=result_ransac.transformation,
            estimation_method=estimation,
            criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
                relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=50
            ),
        )

        elapsed = time.time() - t0
        return result_icp, elapsed

    # ============================================================
    # 1:N 매칭 루프
    # ============================================================
    def match_against_references(
        self,
        cluster_pcd: o3d.geometry.PointCloud,
        reference_cache: Dict[str, Dict[str, Any]],
        candidate_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """클러스터를 여러 레퍼런스에 매칭하고 결과를 반환한다.

        Args:
            cluster_pcd: 씬 클러스터 포인트클라우드
            reference_cache: {name: {"pcd_down": ..., "fpfh": ...}} 딕셔너리
            candidate_names: SizeFilter로 필터링된 후보 이름 리스트.
                             None이면 전체 레퍼런스에 매칭.

        Returns:
            fitness 높은 순 정렬된 매칭 결과 리스트:
            [{"name", "fitness", "rmse", "transformation", "time"}, ...]
        """
        # 클러스터 전처리
        cluster_down, cluster_fpfh = self.preprocess(cluster_pcd)

        # 매칭 대상 결정
        if candidate_names is not None:
            names_to_try = [n for n in candidate_names if n in reference_cache]
        else:
            names_to_try = list(reference_cache.keys())

        results = []

        for ref_name in names_to_try:
            ref_data = reference_cache[ref_name]
            ref_down = ref_data["pcd_down"]
            ref_fpfh = ref_data["fpfh"]

            result, elapsed = self.register(
                ref_down, ref_fpfh, cluster_down, cluster_fpfh
            )

            results.append({
                "name": ref_name,
                "fitness": result.fitness,
                "rmse": result.inlier_rmse,
                "transformation": np.array(result.transformation),
                "time": elapsed,
                "correspondences": len(result.correspondence_set),
            })

        # fitness 높은 순 정렬 (동점 시 RMSE 낮은 순)
        results.sort(key=lambda x: (-x["fitness"], x["rmse"]))

        return results

    # ============================================================
    # 판정: ACCEPT / WARN / REJECT
    # ============================================================
    def evaluate(self, result: Dict[str, Any]) -> str:
        """매칭 결과의 품질을 판정한다.

        Args:
            result: match_against_references() 반환 딕셔너리 1개

        Returns:
            "ACCEPT": fitness >= threshold, RMSE <= threshold
            "WARN":   fitness >= threshold * 0.7 또는 RMSE 약간 초과
            "REJECT": 기준 미달
        """
        fitness = result["fitness"]
        rmse = result["rmse"]

        if fitness >= self.fitness_threshold and rmse <= self.rmse_threshold:
            return "ACCEPT"
        elif fitness >= self.fitness_threshold * 0.7:
            return "WARN"
        else:
            return "REJECT"

    # ============================================================
    # 6DoF 자세 추출
    # ============================================================
    def extract_pose(self, transformation: np.ndarray) -> Dict[str, Any]:
        """4x4 변환 행렬에서 6DoF 자세를 추출한다.

        Args:
            transformation: 4x4 동차 변환 행렬 (레퍼런스 → 씬)

        Returns:
            dict:
                - translation_mm: (x, y, z) 위치 [mm]
                - euler_deg: (rz, ry, rx) ZYX 오일러 각도 [deg]
                - approach_vector: 접근 벡터 (3D 단위 벡터)
        """
        R_mat = transformation[:3, :3]
        t_vec = transformation[:3, 3]

        # 오일러 각도 (ZYX — 로봇 관절 표현)
        euler_zyx = Rotation.from_matrix(R_mat).as_euler("ZYX", degrees=True)

        # 접근 벡터: 변환된 Z축 방향 (위에서 내려잡기 기준 -Z)
        approach = R_mat @ np.array([0.0, 0.0, -1.0])
        approach = approach / (np.linalg.norm(approach) + 1e-8)

        return {
            "translation_mm": {
                "x": float(t_vec[0] * 1000),
                "y": float(t_vec[1] * 1000),
                "z": float(t_vec[2] * 1000),
            },
            "euler_deg": {
                "rz": float(euler_zyx[0]),
                "ry": float(euler_zyx[1]),
                "rx": float(euler_zyx[2]),
            },
            "approach_vector": approach.tolist(),
        }


# ============================================================
# 유틸리티
# ============================================================
def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# __main__: 데모 — 5종 레퍼런스 + 3부품 씬 매칭 테스트
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PoseEstimator 1:N 매칭 데모")
    parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
    args = parser.parse_args()

    np.random.seed(42)

    VOXEL_SIZE = DEFAULT_VOXEL_SIZE

    # ============================================================
    # Step 1: 레퍼런스 5종 생성 + 캐시 빌드
    # ============================================================
    print_section("Step 1: 레퍼런스 5종 + FPFH 캐시 빌드")

    ref_meshes = {
        "torus": _center_mesh(o3d.geometry.TriangleMesh.create_torus(
            torus_radius=0.015, tube_radius=0.005
        )),
        "box": _center_mesh(o3d.geometry.TriangleMesh.create_box(
            0.030, 0.020, 0.010
        )),
        "cylinder": _center_mesh(o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.008, height=0.025
        )),
        "sphere": _center_mesh(o3d.geometry.TriangleMesh.create_sphere(
            radius=0.012
        )),
        "cone": _center_mesh(o3d.geometry.TriangleMesh.create_cone(
            radius=0.010, height=0.030
        )),
    }

    estimator = PoseEstimator(voxel_size=VOXEL_SIZE)
    size_filter = SizeFilter(tolerance=0.5)  # 빈피킹: 노이즈+자세 변환으로 bbox 변동 큼

    reference_cache: Dict[str, Dict[str, Any]] = {}
    ref_pcds: Dict[str, o3d.geometry.PointCloud] = {}

    t_cache_start = time.time()
    for name, mesh in ref_meshes.items():
        t0 = time.time()
        pcd = mesh.sample_points_uniformly(5000)
        ref_pcds[name] = pcd

        pcd_down, fpfh = estimator.preprocess(pcd)
        reference_cache[name] = {"pcd_down": pcd_down, "fpfh": fpfh}

        size_filter.add_reference(name, pcd)

        elapsed = time.time() - t0
        print(f"  {name:>10}: {len(pcd_down.points):>4} pts, "
              f"FPFH {fpfh.dimension()}D x {fpfh.num()}, {elapsed:.2f}s")

    t_cache_total = time.time() - t_cache_start
    print(f"\n  캐시 빌드 총: {t_cache_total:.2f}s ({len(reference_cache)}종)")

    # ============================================================
    # Step 2: 테스트 씬 생성 (3개 부품, 랜덤 자세 + 노이즈)
    # ============================================================
    print_section("Step 2: 테스트 씬 — 3개 부품 (랜덤 자세)")

    # 씬에 배치할 부품 (알려진 정답)
    scene_parts = [
        ("torus", np.array([0.03, 0.01, 0.015])),
        ("box",   np.array([-0.02, 0.03, 0.010])),
        ("cone",  np.array([0.00, -0.03, 0.020])),
    ]

    scene_clusters = []  # (이름, 클러스터 pcd, ground_truth_T) 저장
    ground_truth = []

    for part_name, offset in scene_parts:
        mesh = ref_meshes[part_name]
        pcd = mesh.sample_points_uniformly(3000)

        # 랜덤 회전
        euler = np.random.uniform(-np.pi, np.pi, 3)
        R = pcd.get_rotation_matrix_from_xyz(euler)
        pcd.rotate(R, center=pcd.get_center())
        pcd.translate(offset)

        # ToF 카메라 노이즈 (Blaze-112: ~0.3mm)
        noise = np.random.normal(0, 0.0003, size=np.asarray(pcd.points).shape)
        pcd.points = o3d.utility.Vector3dVector(
            np.asarray(pcd.points) + noise
        )

        T_gt = np.eye(4)
        T_gt[:3, :3] = R
        T_gt[:3, 3] = offset

        scene_clusters.append((part_name, pcd))
        ground_truth.append(T_gt)

        print(f"  부품: {part_name:>10}, 위치=({offset[0]*1000:+5.0f}, "
              f"{offset[1]*1000:+5.0f}, {offset[2]*1000:+5.0f})mm")

    # ============================================================
    # Step 3: SizeFilter → PoseEstimator 매칭
    # ============================================================
    print_section("Step 3: SizeFilter + PoseEstimator 매칭")

    all_results = []
    total_match_time = 0.0

    for i, (gt_name, cluster_pcd) in enumerate(scene_clusters):
        print(f"\n  --- 클러스터 {i}: 정답={gt_name} ({len(cluster_pcd.points)} pts) ---")

        # SizeFilter (후보 0이면 전체 레퍼런스 fallback)
        t_filter = time.time()
        candidates = size_filter.filter_candidates(cluster_pcd)
        t_filter_elapsed = time.time() - t_filter
        if not candidates:
            candidates = list(reference_cache.keys())
            print(f"    SizeFilter: 0 후보 → fallback 전체 {len(candidates)}종 ({t_filter_elapsed*1000:.1f}ms)")
        else:
            print(f"    SizeFilter: {len(candidates)} 후보 ({t_filter_elapsed*1000:.1f}ms)")
        print(f"    후보: {', '.join(candidates)}")

        # PoseEstimator
        t_match = time.time()
        match_results = estimator.match_against_references(
            cluster_pcd, reference_cache, candidate_names=candidates
        )
        t_match_elapsed = time.time() - t_match
        total_match_time += t_match_elapsed

        # 각 후보 결과 출력
        for mr in match_results:
            decision = estimator.evaluate(mr)
            print(f"    vs {mr['name']:>10}: fitness={mr['fitness']:.4f}, "
                  f"RMSE={mr['rmse']*1000:.2f}mm, "
                  f"corr={mr['correspondences']}, {decision}")

        # 최적 매칭
        if match_results:
            best = match_results[0]
            decision = estimator.evaluate(best)
            pose = estimator.extract_pose(best["transformation"])

            all_results.append({
                "cluster_id": i,
                "gt_name": gt_name,
                "matched_name": best["name"],
                "fitness": best["fitness"],
                "rmse": best["rmse"],
                "time": t_match_elapsed,
                "decision": decision,
                "pose": pose,
                "n_candidates": len(candidates),
            })

            correct = best["name"] == gt_name
            marker = "[OK]" if correct else "[X] "
            print(f"    => {marker} Best: {best['name']}, "
                  f"소요: {t_match_elapsed:.2f}s "
                  f"({len(candidates)} 후보, 전체 대비 {len(candidates)/len(reference_cache)*100:.0f}%)")
        else:
            all_results.append({
                "cluster_id": i,
                "gt_name": gt_name,
                "matched_name": "---",
                "fitness": 0.0,
                "rmse": float("inf"),
                "time": t_match_elapsed,
                "decision": "REJECT",
                "pose": None,
                "n_candidates": 0,
            })
            print(f"    => [X]  매칭 실패 (후보 없음)")

    # ============================================================
    # Step 4: 결과 테이블
    # ============================================================
    print_section("Step 4: 결과 테이블")

    header = (f"  {'ID':>3} {'정답':>10} {'매칭':>10} {'Fitness':>8} "
              f"{'RMSE(mm)':>9} {'후보':>4} {'시간(s)':>7} {'판정':>8} "
              f"{'위치 (mm)':>30}")
    print(header)
    print(f"  {'-'*100}")

    for r in all_results:
        if r["pose"]:
            t = r["pose"]["translation_mm"]
            pos_str = f"({t['x']:+6.1f}, {t['y']:+6.1f}, {t['z']:+6.1f})"
        else:
            pos_str = "---"

        correct_marker = "[OK]" if r["matched_name"] == r["gt_name"] else "[X] "
        decision_str = f"{r['decision']}"

        print(f"  {r['cluster_id']:>3} {r['gt_name']:>10} {r['matched_name']:>10} "
              f"{r['fitness']:>8.4f} {r['rmse']*1000:>9.2f} "
              f"{r['n_candidates']:>4} {r['time']:>7.2f} {decision_str:>8} "
              f"{pos_str:>30} {correct_marker}")

    # ============================================================
    # Step 5: 6DoF 자세 상세
    # ============================================================
    print_section("Step 5: 6DoF 자세 상세")

    print(f"  {'ID':>3} {'Part':>10} {'Position (mm)':>30} "
          f"{'Euler ZYX (deg)':>30} {'Approach':>25}")
    print(f"  {'-'*105}")

    for r in all_results:
        if r["decision"] == "REJECT" or r["pose"] is None:
            print(f"  {r['cluster_id']:>3} {'REJECTED':>10}")
            continue

        t = r["pose"]["translation_mm"]
        e = r["pose"]["euler_deg"]
        a = r["pose"]["approach_vector"]

        pos_str = f"({t['x']:+7.1f}, {t['y']:+7.1f}, {t['z']:+7.1f})"
        euler_str = f"({e['rz']:+7.1f}, {e['ry']:+7.1f}, {e['rx']:+7.1f})"
        approach_str = f"({a[0]:+.3f}, {a[1]:+.3f}, {a[2]:+.3f})"

        print(f"  {r['cluster_id']:>3} {r['matched_name']:>10} {pos_str:>30} "
              f"{euler_str:>30} {approach_str:>25}")

    # ============================================================
    # Step 6: 성능 요약
    # ============================================================
    print_section("Step 6: 성능 요약")

    n_parts = len(all_results)
    n_correct = sum(1 for r in all_results if r["matched_name"] == r["gt_name"])
    n_accepted = sum(1 for r in all_results if r["decision"] == "ACCEPT")

    match_times = [r["time"] for r in all_results]
    avg_time = np.mean(match_times) if match_times else 0
    max_time = np.max(match_times) if match_times else 0

    avg_candidates = np.mean([r["n_candidates"] for r in all_results])
    total_refs = len(reference_cache)

    print(f"  부품 수:         {n_parts}")
    print(f"  정답 일치:       {n_correct}/{n_parts} ({n_correct/n_parts*100:.0f}%)")
    print(f"  수락(ACCEPT):    {n_accepted}/{n_parts}")
    print()
    print(f"  매칭 총 시간:    {total_match_time:.2f}s")
    print(f"  부품당 평균:     {avg_time:.2f}s (목표: 2.0s)")
    print(f"  부품당 최대:     {max_time:.2f}s")
    print()
    print(f"  SizeFilter 효과:")
    print(f"    레퍼런스:      {total_refs}종 → 평균 {avg_candidates:.1f}종 ({avg_candidates/total_refs*100:.0f}%)")
    print(f"    비용 절감:     ~{(1 - avg_candidates/total_refs)*100:.0f}%")

    # 목표 판정
    time_ok = avg_time <= 2.0
    rate_ok = n_correct / n_parts >= 0.85 if n_parts > 0 else False

    print()
    if time_ok:
        print(f"  [PASS] 부품당 시간 {avg_time:.2f}s <= 2.0s")
    else:
        print(f"  [FAIL] 부품당 시간 {avg_time:.2f}s > 2.0s")

    if rate_ok:
        print(f"  [PASS] 인식률 {n_correct/n_parts*100:.0f}% >= 85%")
    else:
        print(f"  [FAIL] 인식률 {n_correct/n_parts*100:.0f}% < 85%")

    # ============================================================
    # 시각화 (옵션)
    # ============================================================
    if not args.no_vis:
        import copy

        print_section("시각화: 클러스터 + 매칭 결과")

        vis_geometries = []
        colors = [
            [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [1, 1, 0], [1, 0, 1],
        ]

        for i, (gt_name, cluster_pcd) in enumerate(scene_clusters):
            cluster_vis = copy.deepcopy(cluster_pcd)
            cluster_vis.paint_uniform_color(colors[i % len(colors)])
            vis_geometries.append(cluster_vis)

            bbox = cluster_pcd.get_axis_aligned_bounding_box()
            bbox.color = colors[i % len(colors)]
            vis_geometries.append(bbox)

            # 매칭된 레퍼런스를 변환 적용하여 표시
            r = all_results[i]
            if r["decision"] != "REJECT" and r["matched_name"] in ref_pcds:
                ref_vis = copy.deepcopy(ref_pcds[r["matched_name"]])
                ref_vis.transform(r.get("transformation", np.eye(4))
                                  if "transformation" in r else np.eye(4))
                ref_vis.paint_uniform_color([c * 0.5 for c in colors[i % len(colors)]])
                vis_geometries.append(ref_vis)

        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.02)
        vis_geometries.append(coord)

        o3d.visualization.draw_geometries(
            vis_geometries,
            window_name="PoseEstimator: Matching Results",
            width=1024, height=768,
        )
    else:
        print("\n  --no-vis 모드: 시각화 건너뜀")

    print(f"\n{'='*60}")
    print("  PoseEstimator 1:N 매칭 데모 완료!")
    print(f"{'='*60}")
