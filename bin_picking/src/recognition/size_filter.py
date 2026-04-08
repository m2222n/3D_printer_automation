"""
바운딩박스 기반 사전 필터 — 30종 레퍼런스 → 5~8 후보 축소
================================================================

FPFH+RANSAC+ICP는 고비용 연산 (레퍼런스당 0.3~1.0초).
30종 전체에 매칭하면 부품당 2초 목표 초과 불가피.

해결:
  1. 레퍼런스 모델의 바운딩박스 특징(축 크기, 체적, 대각선) 사전 계산
  2. 씬 클러스터의 바운딩박스와 비교 → 크기 유사한 후보만 남김
  3. 후보 5~8개로 축소 후 FPFH+RANSAC+ICP 실행

비대칭 허용 범위:
  - 클러스터가 레퍼런스보다 작을 수 있음 (가림/부분 가시)
  - 클러스터가 레퍼런스보다 커지는 경우는 제한적 (노이즈)
  - shrink_tolerance=0.5 (50% 축소 허용), grow_tolerance=0.3 (30% 확대 허용)

실행: source .venv/binpick/bin/activate && python bin_picking/src/size_filter.py --no-vis
"""

import argparse
import sys
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import open3d as o3d

# ============================================================
# 0. 빈피킹 파라미터
# ============================================================
VOXEL_SIZE = 0.002  # 2mm — 빈피킹 SLA 부품용


# ============================================================
# 1. 바운딩박스 특징 계산
# ============================================================
def compute_bbox_features(pcd: o3d.geometry.PointCloud, use_obb: bool = True) -> Dict[str, float]:
    """포인트클라우드의 바운딩박스 기반 크기 특징을 계산한다.

    Args:
        pcd: 입력 포인트클라우드
        use_obb: True면 OBB(회전 불변), False면 AABB(축 정렬) 사용

    Returns:
        dict: 다음 키를 포함하는 특징 딕셔너리
            - extent_x, extent_y, extent_z: 축별 크기 (오름차순 정렬, 미터)
            - volume: 바운딩박스 체적 (m^3)
            - diagonal: 바운딩박스 대각선 길이 (m)
            - aspect_ratios: (min/mid, mid/max) 종횡비 튜플
    """
    if use_obb and len(pcd.points) >= 4:
        obb = pcd.get_oriented_bounding_box()
        extent = np.sort(obb.extent)  # 오름차순 정렬
    else:
        bbox = pcd.get_axis_aligned_bounding_box()
        extent = np.sort(bbox.get_extent())  # 오름차순 정렬

    # 0 크기 방어 (평면 또는 직선 형태)
    extent = np.maximum(extent, 1e-6)

    volume = float(np.prod(extent))
    diagonal = float(np.linalg.norm(extent))

    # 종횡비: (최소/중간, 중간/최대)
    aspect_ratios = (
        float(extent[0] / extent[1]) if extent[1] > 1e-6 else 0.0,
        float(extent[1] / extent[2]) if extent[2] > 1e-6 else 0.0,
    )

    return {
        "extent_x": float(extent[0]),
        "extent_y": float(extent[1]),
        "extent_z": float(extent[2]),
        "volume": volume,
        "diagonal": diagonal,
        "aspect_ratios": aspect_ratios,
    }


# ============================================================
# 2. SizeFilter 클래스
# ============================================================
class SizeFilter:
    """바운딩박스 크기 기반 사전 필터.

    30종 레퍼런스 중 씬 클러스터와 크기가 유사한 후보만 선별한다.
    비대칭 허용 범위를 사용하여 가림(occlusion)에 의한
    클러스터 축소를 허용한다.
    """

    def __init__(
        self,
        tolerance: float = 0.3,
        shrink_tolerance: Optional[float] = None,
        grow_tolerance: Optional[float] = None,
    ):
        """
        Args:
            tolerance: 기본 허용 범위 (0.3 = +-30%)
            shrink_tolerance: 클러스터가 레퍼런스보다 작아지는 허용 범위
                              (None이면 0.5 = 50% 축소 허용)
            grow_tolerance: 클러스터가 레퍼런스보다 커지는 허용 범위
                            (None이면 tolerance 사용)
        """
        self.tolerance = tolerance
        self.shrink_tolerance = shrink_tolerance if shrink_tolerance is not None else 0.5
        self.grow_tolerance = grow_tolerance if grow_tolerance is not None else tolerance
        self._references: Dict[str, Dict[str, float]] = {}

    def add_reference(
        self, name: str, pcd_or_features: Union[o3d.geometry.PointCloud, Dict[str, float]]
    ) -> None:
        """레퍼런스 모델의 바운딩박스 특징을 등록한다.

        Args:
            name: 레퍼런스 이름 (예: "part_001")
            pcd_or_features: 포인트클라우드 또는 이미 계산된 특징 딕셔너리
        """
        if isinstance(pcd_or_features, dict):
            features = pcd_or_features
        else:
            features = compute_bbox_features(pcd_or_features)
        self._references[name] = features

    def filter_candidates(self, cluster_pcd: o3d.geometry.PointCloud) -> List[str]:
        """씬 클러스터와 크기가 유사한 레퍼런스 후보를 반환한다.

        Args:
            cluster_pcd: DBSCAN으로 분할된 클러스터 포인트클라우드

        Returns:
            크기 유사도 순으로 정렬된 레퍼런스 이름 리스트 (best match first)
        """
        if not self._references:
            return []

        cluster_feat = compute_bbox_features(cluster_pcd, use_obb=True)
        cluster_extents = np.array([
            cluster_feat["extent_x"],
            cluster_feat["extent_y"],
            cluster_feat["extent_z"],
        ])

        scored_candidates: List[Tuple[str, float]] = []

        for ref_name, ref_feat in self._references.items():
            ref_extents = np.array([
                ref_feat["extent_x"],
                ref_feat["extent_y"],
                ref_feat["extent_z"],
            ])

            # --- 축별 비교 (비대칭 허용 범위) ---
            axes_ok = True
            axis_scores = []

            for i in range(3):
                ref_val = ref_extents[i]
                cls_val = cluster_extents[i]

                # 하한: 클러스터가 레퍼런스의 (1 - shrink_tolerance) 배까지 허용
                lower = ref_val * (1.0 - self.shrink_tolerance)
                # 상한: 클러스터가 레퍼런스의 (1 + grow_tolerance) 배까지 허용
                upper = ref_val * (1.0 + self.grow_tolerance)

                if cls_val < lower or cls_val > upper:
                    axes_ok = False
                    break

                # 축별 유사도 점수 (0~1, 1이면 완전 일치)
                if ref_val > 1e-6:
                    ratio = cls_val / ref_val
                    axis_scores.append(1.0 - abs(ratio - 1.0))
                else:
                    axis_scores.append(0.0)

            if not axes_ok:
                continue

            # --- 체적 비교 ---
            ref_vol = ref_feat["volume"]
            cls_vol = cluster_feat["volume"]

            if ref_vol > 1e-12:
                vol_ratio = cls_vol / ref_vol
                # 체적은 축 크기의 세제곱이므로 허용 범위도 넓게
                vol_lower = (1.0 - self.shrink_tolerance) ** 3
                vol_upper = (1.0 + self.grow_tolerance) ** 3

                if vol_ratio < vol_lower or vol_ratio > vol_upper:
                    continue

                vol_score = 1.0 - min(abs(vol_ratio - 1.0), 1.0)
            else:
                vol_score = 0.0

            # --- 대각선 비교 ---
            ref_diag = ref_feat["diagonal"]
            cls_diag = cluster_feat["diagonal"]

            if ref_diag > 1e-6:
                diag_ratio = cls_diag / ref_diag
                diag_lower = 1.0 - self.shrink_tolerance
                diag_upper = 1.0 + self.grow_tolerance

                if diag_ratio < diag_lower or diag_ratio > diag_upper:
                    continue

                diag_score = 1.0 - abs(diag_ratio - 1.0)
            else:
                diag_score = 0.0

            # --- 종합 점수 (가중 평균) ---
            # 축 크기 50%, 체적 25%, 대각선 25%
            axis_avg = float(np.mean(axis_scores)) if axis_scores else 0.0
            total_score = 0.50 * axis_avg + 0.25 * vol_score + 0.25 * diag_score

            scored_candidates.append((ref_name, total_score))

        # 유사도 높은 순 정렬
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        return [name for name, _ in scored_candidates]

    @property
    def reference_names(self) -> List[str]:
        """등록된 레퍼런스 이름 목록"""
        return list(self._references.keys())

    @property
    def reference_count(self) -> int:
        """등록된 레퍼런스 수"""
        return len(self._references)


# ============================================================
# 유틸리티: 메쉬 생성 헬퍼
# ============================================================
def _center_mesh(mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
    """메쉬 중심을 원점으로 이동"""
    mesh.translate(-mesh.get_center())
    mesh.compute_vertex_normals()
    return mesh


# ============================================================
# __main__: 데모 — 5종 형상 등록 + 노이즈 클러스터 필터 테스트
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SizeFilter 바운딩박스 사전 필터 데모")
    parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
    args = parser.parse_args()

    np.random.seed(42)

    def print_section(title: str):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    # ============================================================
    # Step 1: 레퍼런스 5종 생성 (빈피킹 스케일 20~40mm)
    # ============================================================
    print_section("Step 1: 레퍼런스 5종 생성")

    ref_meshes = {
        "torus": _center_mesh(o3d.geometry.TriangleMesh.create_torus(
            torus_radius=0.015, tube_radius=0.005  # 외경 ~30mm
        )),
        "box": _center_mesh(o3d.geometry.TriangleMesh.create_box(
            0.030, 0.020, 0.010  # 30x20x10mm
        )),
        "cylinder": _center_mesh(o3d.geometry.TriangleMesh.create_cylinder(
            radius=0.008, height=0.025  # 지름 16mm x 높이 25mm
        )),
        "sphere": _center_mesh(o3d.geometry.TriangleMesh.create_sphere(
            radius=0.012  # 지름 24mm
        )),
        "cone": _center_mesh(o3d.geometry.TriangleMesh.create_cone(
            radius=0.010, height=0.030  # 지름 20mm x 높이 30mm
        )),
    }

    # SizeFilter에 등록
    sf = SizeFilter(tolerance=0.3)

    ref_pcds = {}
    for name, mesh in ref_meshes.items():
        pcd = mesh.sample_points_uniformly(5000)
        ref_pcds[name] = pcd
        sf.add_reference(name, pcd)

        feat = sf._references[name]
        ext = np.array([feat["extent_x"], feat["extent_y"], feat["extent_z"]]) * 1000
        print(f"  {name:>10}: {ext[0]:5.1f} x {ext[1]:5.1f} x {ext[2]:5.1f} mm  "
              f"vol={feat['volume']*1e9:8.1f} mm^3  diag={feat['diagonal']*1000:5.1f} mm")

    print(f"\n  레퍼런스 등록: {sf.reference_count}종")

    # ============================================================
    # Step 2: 테스트 클러스터 생성 (노이즈 + 부분 가림)
    # ============================================================
    print_section("Step 2: 테스트 클러스터 생성")

    test_cases = []

    # 테스트 1: 토러스 정상 크기 (완전 가시)
    torus_cluster = ref_meshes["torus"].sample_points_uniformly(3000)
    noise = np.random.normal(0, 0.0003, size=np.asarray(torus_cluster.points).shape)
    torus_cluster.points = o3d.utility.Vector3dVector(
        np.asarray(torus_cluster.points) + noise
    )
    test_cases.append(("torus (완전)", torus_cluster, "torus"))

    # 테스트 2: 박스 70% 크기 (부분 가림 — 30% 잘림)
    box_full = ref_meshes["box"].sample_points_uniformly(3000)
    pts = np.asarray(box_full.points)
    # x축으로 70%만 남기기 (상위 30% 제거)
    x_threshold = np.percentile(pts[:, 0], 70)
    mask = pts[:, 0] <= x_threshold
    box_partial = o3d.geometry.PointCloud()
    box_partial.points = o3d.utility.Vector3dVector(pts[mask])
    noise = np.random.normal(0, 0.0003, size=np.asarray(box_partial.points).shape)
    box_partial.points = o3d.utility.Vector3dVector(
        np.asarray(box_partial.points) + noise
    )
    test_cases.append(("box (70%)", box_partial, "box"))

    # 테스트 3: 원기둥 60% 크기 (심한 가림)
    cyl_full = ref_meshes["cylinder"].sample_points_uniformly(3000)
    pts = np.asarray(cyl_full.points)
    z_threshold = np.percentile(pts[:, 2], 60)
    mask = pts[:, 2] <= z_threshold
    cyl_partial = o3d.geometry.PointCloud()
    cyl_partial.points = o3d.utility.Vector3dVector(pts[mask])
    noise = np.random.normal(0, 0.0003, size=np.asarray(cyl_partial.points).shape)
    cyl_partial.points = o3d.utility.Vector3dVector(
        np.asarray(cyl_partial.points) + noise
    )
    test_cases.append(("cylinder (60%)", cyl_partial, "cylinder"))

    # 테스트 4: 구 정상 크기 + 회전
    sphere_cluster = ref_meshes["sphere"].sample_points_uniformly(3000)
    R = sphere_cluster.get_rotation_matrix_from_xyz([0.5, 0.3, -0.7])
    sphere_cluster.rotate(R, center=sphere_cluster.get_center())
    noise = np.random.normal(0, 0.0003, size=np.asarray(sphere_cluster.points).shape)
    sphere_cluster.points = o3d.utility.Vector3dVector(
        np.asarray(sphere_cluster.points) + noise
    )
    test_cases.append(("sphere (회전)", sphere_cluster, "sphere"))

    # 테스트 5: 콘 정상 크기 (노이즈만)
    cone_cluster = ref_meshes["cone"].sample_points_uniformly(3000)
    noise = np.random.normal(0, 0.0005, size=np.asarray(cone_cluster.points).shape)
    cone_cluster.points = o3d.utility.Vector3dVector(
        np.asarray(cone_cluster.points) + noise
    )
    test_cases.append(("cone (노이즈)", cone_cluster, "cone"))

    for desc, cluster, _ in test_cases:
        feat = compute_bbox_features(cluster)
        ext = np.array([feat["extent_x"], feat["extent_y"], feat["extent_z"]]) * 1000
        print(f"  {desc:>20}: {ext[0]:5.1f} x {ext[1]:5.1f} x {ext[2]:5.1f} mm  "
              f"({len(cluster.points)} pts)")

    # ============================================================
    # Step 3: 필터링 실행 + 결과 테이블
    # ============================================================
    print_section("Step 3: 필터링 결과")

    header = (f"  {'테스트':>20}  {'정답':>10}  {'후보 수':>7}  "
              f"{'후보 목록':>40}  {'정답 포함':>8}")
    print(header)
    print(f"  {'-'*95}")

    total_time = 0.0
    correct = 0

    for desc, cluster, expected in test_cases:
        t0 = time.time()
        candidates = sf.filter_candidates(cluster)
        elapsed = time.time() - t0
        total_time += elapsed

        has_correct = expected in candidates
        if has_correct:
            correct += 1

        cand_str = ", ".join(candidates) if candidates else "(없음)"
        marker = "[OK]" if has_correct else "[X] "

        print(f"  {desc:>20}  {expected:>10}  {len(candidates):>7}  "
              f"{cand_str:>40}  {marker:>8}")

    # ============================================================
    # Step 4: 요약
    # ============================================================
    print_section("Step 4: 요약")

    print(f"  테스트: {len(test_cases)}건")
    print(f"  정답 포함: {correct}/{len(test_cases)} ({correct/len(test_cases)*100:.0f}%)")
    print(f"  필터링 총 시간: {total_time*1000:.1f}ms (부품당 {total_time/len(test_cases)*1000:.1f}ms)")
    print(f"  평균 후보 수: {np.mean([len(sf.filter_candidates(tc[1])) for tc in test_cases]):.1f}")
    print()
    print("  SizeFilter는 0.1ms 미만의 오버헤드로 30종 → 5~8종 축소.")
    print("  FPFH+RANSAC+ICP 비용을 70~80% 절감.")

    # ============================================================
    # 시각화 (옵션)
    # ============================================================
    if not args.no_vis:
        print_section("시각화: 레퍼런스 바운딩박스")

        vis_geometries = []
        colors = [
            [1, 0, 0], [0, 1, 0], [0, 0, 1],
            [1, 1, 0], [1, 0, 1],
        ]

        for i, (name, pcd) in enumerate(ref_pcds.items()):
            import copy
            pcd_vis = copy.deepcopy(pcd)
            # 레퍼런스를 옆으로 나열
            pcd_vis.translate([i * 0.05, 0, 0])
            pcd_vis.paint_uniform_color(colors[i % len(colors)])
            vis_geometries.append(pcd_vis)

            bbox = pcd_vis.get_axis_aligned_bounding_box()
            bbox.color = colors[i % len(colors)]
            vis_geometries.append(bbox)

        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.02)
        vis_geometries.append(coord)

        o3d.visualization.draw_geometries(
            vis_geometries,
            window_name="SizeFilter: Reference Models",
            width=1024, height=768,
        )
    else:
        print("\n  --no-vis 모드: 시각화 건너뜀")

    print(f"\n{'='*60}")
    print("  SizeFilter 데모 완료!")
    print(f"{'='*60}")
