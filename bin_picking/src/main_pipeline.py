"""
빈피킹 메인 파이프라인 — L1→L2→L3→L4→L5→L6
=================================================

카메라 입력(또는 저장된 프레임)에서 부품 인식 + 피킹 자세 계산 +
로봇 통신까지 전체 파이프라인을 실행한다.

파이프라인:
  L1: 영상 취득     — 카메라 캡처 또는 저장된 depth/color 로드
  L2: 전처리        — ROI, SOR, 다운샘플, RANSAC 바닥 제거, 법선
  L3: 분할          — DBSCAN 클러스터링
  L4: 인식+자세     — FPFH+RANSAC+ICP 매칭
  L5: 그래스프 계획 — grasp_database.yaml 기반 피킹 자세 계산
  L6: 로봇 통신     — Modbus TCP 서버 → HCR-10L

사용법:
  # 저장된 프레임으로 실행 (카메라 없이)
  python bin_picking/src/main_pipeline.py --input /path/to/saved_frames/

  # RealSense D435 라이브
  python bin_picking/src/main_pipeline.py --realsense

  # 합성 테스트 씬 (개발/검증용)
  python bin_picking/src/main_pipeline.py --synthetic

실행 환경: source .venv/binpick/bin/activate
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import open3d as o3d

from bin_picking.src.recognition.cad_library import CADLibrary
from bin_picking.src.recognition.pose_estimator import PoseEstimator
from bin_picking.src.recognition.size_filter import SizeFilter, compute_bbox_features
from bin_picking.src.preprocessing.cloud_filter import CloudFilter
from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter
from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud
from bin_picking.src.grasping.grasp_planner import GraspPlanner
from bin_picking.src.communication.modbus_server import PickingModbusServer


# ============================================================
# 파라미터
# ============================================================
VOXEL_SIZE = 0.002       # 2mm

# ROI: 빈(부품 박스) 영역 (미터) — 카메라 캘리브레이션 후 조정
# Why: Basler Blaze-112 오버헤드(40~80cm) + depth_to_pointcloud 기본 depth_min(0.3m) +
#      SyntheticSource depth(0.55~0.80m) 세 값이 한 세팅에서 일관되게 동작해야 함.
#      D435 20cm 근접 테스트는 --roi-z-min/--roi-z-max CLI 오버라이드로 대응.
DEFAULT_ROI = {
    "min": [-0.30, -0.30, 0.30],    # Basler 작동 거리 하한
    "max": [0.30, 0.30, 1.00],      # 빈 상부까지 포함
}


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================
# BinPickingPipeline
# ============================================================
class BinPickingPipeline:
    """빈피킹 메인 파이프라인.

    초기화 시 레퍼런스 캐시를 로드하고,
    run() 호출 시 L1~L4 파이프라인을 실행한다.
    """

    def __init__(
        self,
        voxel_size: float = VOXEL_SIZE,
        roi: Optional[Dict[str, List[float]]] = None,
        size_filter_tolerance: float = 0.5,
        max_candidates: int = 10,
        resin: Optional[str] = None,
    ):
        # 레진 프리셋 해석 (voxel_size는 프리셋 값으로 덮어씀)
        self._preset = None
        if resin is not None:
            from bin_picking.config.resin_presets import get_preset
            self._preset = get_preset(resin)
            voxel_size = self._preset.voxel_size
            print(f"  레진 프리셋: {self._preset.name} (voxel={voxel_size*1000:.1f}mm)")

        self.voxel_size = voxel_size
        self.roi = roi or DEFAULT_ROI
        self.max_candidates = max_candidates

        # L4: 레퍼런스 캐시 로드
        print("  레퍼런스 캐시 로딩...")
        t0 = time.time()
        self.cad_library = CADLibrary()
        self.reference_cache = self.cad_library.load_all()
        load_time = time.time() - t0

        if not self.reference_cache:
            raise RuntimeError(
                "레퍼런스 캐시가 비어있습니다. "
                "먼저 실행: python bin_picking/src/recognition/cad_library.py --build"
            )

        print(f"  로드 완료: {len(self.reference_cache)}종, {load_time*1000:.0f}ms")

        # SizeFilter 구축
        self.size_filter = SizeFilter(tolerance=size_filter_tolerance)
        for name, data in self.reference_cache.items():
            self.size_filter.add_reference(name, data["bbox_features"])

        # PoseEstimator — 레진 프리셋이 설정되어 있으면 인스턴스 재생성
        if hasattr(self, "_preset") and self._preset is not None:
            self.estimator = PoseEstimator.from_resin(self._preset.name)
        else:
            self.estimator = PoseEstimator(voxel_size=voxel_size)

        # L2: 전처리 — 레진 프리셋이 설정되어 있으면 해당 파라미터로 생성
        if hasattr(self, "_preset") and self._preset is not None:
            self.cloud_filter = CloudFilter.from_resin(
                self._preset.name,
                roi_min=np.array(self.roi["min"]),
                roi_max=np.array(self.roi["max"]),
            )
        else:
            self.cloud_filter = CloudFilter(
                voxel_size=voxel_size,
                plane_distance=0.003,
                roi_min=np.array(self.roi["min"]),
                roi_max=np.array(self.roi["max"]),
            )

        # L3: 분할
        self.segmenter = DBSCANSegmenter(eps=0.010, min_points=30)

        # L5: 그래스프 계획
        self.grasp_planner = GraspPlanner()
        print(f"  그래스프 DB: {self.grasp_planner.part_count}종 정의")

        # L6: Modbus 서버 (start_modbus() 호출 시 활성화)
        self.modbus_server: Optional[PickingModbusServer] = None

    @classmethod
    def from_resin(
        cls,
        resin: str,
        roi: Optional[Dict[str, List[float]]] = None,
        size_filter_tolerance: float = 0.5,
        max_candidates: int = 10,
    ) -> "BinPickingPipeline":
        """레진 프리셋 기반 파이프라인 생성.

        L2 전처리(CloudFilter), L4 매칭(PoseEstimator)의 voxel_size 및 판정 임계값이
        SSOT(bin_picking/config/resin_presets.py)에서 일관되게 적용된다.

        Args:
            resin: "grey" | "white" | "clear" | "flexible"
        """
        return cls(
            roi=roi,
            size_filter_tolerance=size_filter_tolerance,
            max_candidates=max_candidates,
            resin=resin,
        )

    def run(
        self,
        point_cloud: o3d.geometry.PointCloud,
        top_k: int = 1,
    ) -> Dict[str, Any]:
        """파이프라인을 실행한다.

        Args:
            point_cloud: 입력 포인트 클라우드 (L1 출력)
            top_k: 클러스터별 상위 K개 매칭 결과 반환

        Returns:
            dict: {
                "parts": [
                    {
                        "name": str,           # 부품 이름
                        "pose": dict,          # 6DoF (translation_mm, euler_deg, approach_vector)
                        "fitness": float,
                        "rmse": float,
                        "decision": str,       # ACCEPT/WARN/REJECT
                        "transformation": ndarray(4,4),
                        "cluster_id": int,
                        "n_points": int,
                    }, ...
                ],
                "timings": dict,
                "n_clusters": int,
                "n_accepted": int,
            }
        """
        timings = {}
        t_total = time.time()

        # ============================================================
        # L2: 전처리
        # ============================================================
        t0 = time.time()
        filtered = self.cloud_filter.process(point_cloud)
        timings["L2"] = time.time() - t0

        if len(filtered.points) < 100:
            return {
                "parts": [],
                "timings": timings,
                "n_clusters": 0,
                "n_accepted": 0,
                "error": "전처리 후 포인트 부족 (<100)",
            }

        # ============================================================
        # L3: 분할
        # ============================================================
        t0 = time.time()
        clusters = self.segmenter.segment(filtered)
        timings["L3"] = time.time() - t0

        # ============================================================
        # L4: 인식 + 자세 추정
        # ============================================================
        t0 = time.time()
        parts = []

        for i, cluster in enumerate(clusters):
            # SizeFilter
            candidates = self.size_filter.filter_candidates(cluster.pcd)
            if not candidates:
                candidates = list(self.reference_cache.keys())

            # PoseEstimator (상위 max_candidates개만)
            match_results = self.estimator.match_against_references(
                cluster.pcd,
                self.reference_cache,
                candidate_names=candidates[:self.max_candidates],
            )

            for rank, mr in enumerate(match_results[:top_k]):
                decision = self.estimator.evaluate(mr)
                pose = self.estimator.extract_pose(mr["transformation"])

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
                })

        timings["L4"] = time.time() - t0

        n_accepted = sum(1 for p in parts if p["decision"] == "ACCEPT" and p["rank"] == 0)

        # ============================================================
        # L5: 그래스프 계획
        # ============================================================
        t0 = time.time()
        picks = self.grasp_planner.plan_picks(parts)
        timings["L5"] = time.time() - t0

        # ============================================================
        # L6: Modbus 전송 (서버 활성화 시)
        # ============================================================
        t0 = time.time()
        if self.modbus_server and picks:
            self.modbus_server.write_pick_command(picks[0])  # 첫 번째 부품부터
        timings["L6"] = time.time() - t0

        timings["total"] = time.time() - t_total

        return {
            "parts": parts,
            "picks": picks,
            "timings": timings,
            "n_clusters": len(clusters),
            "n_accepted": n_accepted,
            # 시각화 용: filtered PointCloud + Cluster 객체 리스트
            # (메모리 추가되지만 데모/디버그에 유용. 기존 호출자는 접근 안 해도 무방)
            "filtered": filtered,
            "clusters": clusters,
        }

    def print_results(self, result: Dict[str, Any]):
        """결과를 포맷팅하여 출력한다."""
        parts = result["parts"]
        timings = result["timings"]

        print(f"\n  클러스터: {result['n_clusters']}개")
        print(f"  ACCEPT:   {result['n_accepted']}개")
        print()

        if parts:
            print(f"  {'ID':>3} {'부품명':>35} {'Fitness':>8} {'RMSE(mm)':>9} "
                  f"{'위치 (mm)':>30} {'판정':>8}")
            print(f"  {'-'*100}")

            for p in parts:
                if p["rank"] > 0:
                    continue  # top_k > 1일 때 2순위는 표시 안 함

                t = p["pose"]["translation_mm"]
                pos = f"({t['x']:+7.1f}, {t['y']:+7.1f}, {t['z']:+7.1f})"
                print(f"  {p['cluster_id']:>3} {p['name']:>35} "
                      f"{p['fitness']:>8.4f} {p['rmse']*1000:>9.2f} "
                      f"{pos:>30} {p['decision']:>8}")

        # L5 피킹 계획
        picks = result.get("picks", [])
        if picks:
            print(f"\n  --- L5 피킹 계획 ({len(picks)}개, z 높은 순) ---")
            for i, pick in enumerate(picks):
                pos = pick["position_mm"]
                defined = "✅" if pick["defined"] else "⚠️"
                print(f"  [{i+1}] {pick['part_name']:>30}  "
                      f"pos=({pos['x']:+7.1f}, {pos['y']:+7.1f}, {pos['z']:+7.1f})mm  "
                      f"grip={pick['gripper_width_mm']}mm/{pick['gripper_force_N']}N  {defined}")

        print()
        print(f"  시간: L2={timings.get('L2',0):.3f}s, "
              f"L3={timings.get('L3',0):.3f}s, "
              f"L4={timings.get('L4',0):.2f}s, "
              f"L5={timings.get('L5',0):.3f}s, "
              f"L6={timings.get('L6',0):.3f}s, "
              f"총={timings.get('total',0):.2f}s")


# ============================================================
# 합성 씬 생성 (테스트용)
# ============================================================
def create_synthetic_scene(cad_library: CADLibrary, n_parts: int = 3) -> o3d.geometry.PointCloud:
    """개발/테스트용 합성 씬을 생성한다."""
    import trimesh

    np.random.seed(42)

    # 중형 부품 우선 선택 (소형 부품은 다운샘플 후 소실 가능)
    preferred = [
        "01_sol_block_a", "07_guide_paper_l", "17_mks_holder",
        "bracket_sensor1", "guide_paper_roll_cover_left",
        "03_sol_block_front", "16_cam_f_bracket", "08_r_guide_a",
    ]
    available = cad_library.list_stl_files()
    if not available:
        raise RuntimeError("STL 파일이 없습니다")

    # preferred 목록에서 존재하는 것 우선, 부족하면 나머지에서 보충
    avail_names = {f.stem for f in available}
    selected_names = [n for n in preferred if n in avail_names][:n_parts]
    if len(selected_names) < n_parts:
        rest = [f for f in available if f.stem not in set(selected_names)]
        selected_names.extend([f.stem for f in rest[:n_parts - len(selected_names)]])

    selected = [cad_library.cad_dir / f"{n}.stl" for n in selected_names]
    all_points = []

    for i, stl_path in enumerate(selected):
        mesh = trimesh.load(str(stl_path))
        if max(mesh.bounding_box.extents) > 1.0:
            mesh.apply_scale(0.001)

        pts, _ = trimesh.sample.sample_surface(mesh, 5000)

        # 랜덤 자세
        euler = np.random.uniform(-np.pi / 4, np.pi / 4, 3)
        R_mat = o3d.geometry.PointCloud().get_rotation_matrix_from_xyz(euler)
        center = pts.mean(axis=0)
        pts = ((R_mat @ (pts - center).T).T)

        # 배치 (바닥 z=0 에서 60mm 위, 간격 150mm)
        offset = np.array([(i % 3) * 0.15, (i // 3) * 0.15, 0.06])
        pts += offset

        # 노이즈
        pts += np.random.normal(0, 0.0003, size=pts.shape)
        all_points.append(pts)

        name = stl_path.stem
        print(f"  [{i+1}] {name}  pos=({offset[0]*1000:.0f}, {offset[1]*1000:.0f}, {offset[2]*1000:.0f})mm")

    # 바닥면 (RANSAC이 확실히 잡도록 충분한 포인트)
    floor = np.column_stack([
        np.random.uniform(-0.10, 0.50, 10000),
        np.random.uniform(-0.10, 0.40, 10000),
        np.random.normal(0.0, 0.0003, 10000),
    ])
    all_points.append(floor)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.vstack(all_points))
    return pcd


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="빈피킹 메인 파이프라인")
    parser.add_argument("--input", type=str, help="저장된 프레임 디렉토리 (depth.npy + meta.json)")
    parser.add_argument("--realsense", action="store_true", help="RealSense D435 라이브 캡처")
    parser.add_argument("--basler", action="store_true", help="Basler Blaze-112 + ace2 라이브 캡처")
    parser.add_argument("--synthetic", action="store_true", help="합성 테스트 씬 사용")
    parser.add_argument("--n-parts", type=int, default=3, help="합성 씬 부품 수 (기본 3)")
    parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기")
    parser.add_argument(
        "--resin",
        type=str,
        default=None,
        choices=["grey", "white", "clear", "flexible"],
        help="레진 프리셋 (L2 + L4 파라미터 일관 적용). 미지정 시 기본값(voxel 2mm)",
    )
    parser.add_argument(
        "--roi-z-min", type=float, default=None,
        help=f"ROI Z 하한 (m). 미지정 시 기본값 {DEFAULT_ROI['min'][2]:.2f}. "
             "D435 근접 테스트는 0.02 권장.",
    )
    parser.add_argument(
        "--roi-z-max", type=float, default=None,
        help=f"ROI Z 상한 (m). 미지정 시 기본값 {DEFAULT_ROI['max'][2]:.2f}. "
             "D435 근접 테스트는 0.30 권장.",
    )
    parser.add_argument(
        "--depth-min", type=float, default=None,
        help="depth_to_pointcloud 최소 깊이 (m). 기본 0.3. "
             "D435 근접 테스트는 0.02 권장.",
    )
    parser.add_argument(
        "--depth-max", type=float, default=None,
        help="depth_to_pointcloud 최대 깊이 (m). 기본 3.0. "
             "D435 근접 테스트는 0.50 권장.",
    )
    args = parser.parse_args()

    # ROI/depth 오버라이드 — 세팅 간 정합성 유지 (옵션 1: Basler 기준)
    roi_override = None
    if args.roi_z_min is not None or args.roi_z_max is not None:
        roi_override = {
            "min": list(DEFAULT_ROI["min"]),
            "max": list(DEFAULT_ROI["max"]),
        }
        if args.roi_z_min is not None:
            roi_override["min"][2] = args.roi_z_min
        if args.roi_z_max is not None:
            roi_override["max"][2] = args.roi_z_max
        print(f"  [ROI override] z={roi_override['min'][2]:.3f}~{roi_override['max'][2]:.3f}m")

    depth_kwargs = {}
    if args.depth_min is not None:
        depth_kwargs["depth_min"] = args.depth_min
    if args.depth_max is not None:
        depth_kwargs["depth_max"] = args.depth_max
    if depth_kwargs:
        print(f"  [depth override] {depth_kwargs}")

    # ============================================================
    # 파이프라인 초기화
    # ============================================================
    print_section("빈피킹 파이프라인 초기화")
    if args.resin:
        pipeline = BinPickingPipeline.from_resin(args.resin)
    else:
        pipeline = BinPickingPipeline()
    if roi_override is not None:
        pipeline.roi = roi_override

    # ============================================================
    # L1: 입력 취득
    # ============================================================
    print_section("L1: 입력 취득")

    if args.synthetic:
        print("  모드: 합성 테스트 씬")
        scene_pcd = create_synthetic_scene(pipeline.cad_library, n_parts=args.n_parts)
        print(f"  씬 포인트: {len(scene_pcd.points):,}")

    elif args.input:
        input_dir = Path(args.input)
        print(f"  모드: 저장된 프레임 ({input_dir})")

        depth_path = input_dir / "depth.npy"
        meta_path = input_dir / "meta.json"

        if not depth_path.exists():
            print(f"  [오류] depth.npy 없음: {depth_path}")
            sys.exit(1)

        depth_map = np.load(str(depth_path))
        with open(meta_path) as f:
            meta = json.load(f)

        color_path = input_dir / "color.npy"
        color_image = np.load(str(color_path)) if color_path.exists() else None

        scene_pcd = depth_to_pointcloud(
            depth_map,
            fx=meta["fx"], fy=meta["fy"],
            cx=meta["cx"], cy=meta["cy"],
            depth_scale=meta.get("depth_scale", 1000.0),
            color_image=color_image,
            **depth_kwargs,
        )
        print(f"  프레임 로드: {depth_map.shape}, 포인트 {len(scene_pcd.points):,}")

    elif args.realsense:
        print("  모드: RealSense D435 라이브 캡처")
        try:
            from bin_picking.src.acquisition.realsense_capture import RealSenseCapture
            cam = RealSenseCapture()
            cam.start()
            frames = cam.capture()
            scene_pcd = cam.to_pointcloud(frames)
            cam.stop()
            print(f"  캡처 완료: 포인트 {len(scene_pcd.points):,}")
        except Exception as e:
            print(f"  [오류] RealSense 캡처 실패: {e}")
            sys.exit(1)

    elif args.basler:
        print("  모드: Basler Blaze-112 + ace2 라이브 캡처")
        try:
            from bin_picking.src.acquisition.basler_capture import BaslerCapture
            cam = BaslerCapture()
            result = cam.start()
            print(f"  Blaze-112: {'OK' if result['blaze'] else 'FAIL'}")
            print(f"  ace2:      {'OK' if result['ace2'] else 'N/A'}")
            frames = cam.capture()
            scene_pcd = cam.to_pointcloud(frames)
            cam.stop()
            print(f"  캡처 완료: 포인트 {len(scene_pcd.points):,}")
        except Exception as e:
            print(f"  [오류] Basler 캡처 실패: {e}")
            sys.exit(1)

    else:
        print("  입력 모드를 지정하세요: --synthetic, --input <dir>, --realsense, --basler")
        parser.print_help()
        sys.exit(1)

    # ============================================================
    # 파이프라인 실행
    # ============================================================
    print_section("L2→L3→L4 파이프라인 실행")
    result = pipeline.run(scene_pcd)

    # ============================================================
    # 결과 출력
    # ============================================================
    print_section("결과")
    pipeline.print_results(result)

    # ============================================================
    # 시각화
    # ============================================================
    if not args.no_vis and result["parts"]:
        print_section("시각화")
        import copy

        vis = []

        # 씬 (회색)
        scene_vis = copy.deepcopy(scene_pcd)
        scene_vis.paint_uniform_color([0.7, 0.7, 0.7])
        vis.append(scene_vis)

        # 매칭된 레퍼런스
        colors = [[1,0,0],[0,0.8,0],[0,0,1],[1,0.8,0],[1,0,1],[0,1,1]]
        for i, p in enumerate(result["parts"]):
            if p["decision"] == "REJECT" or p["name"] not in pipeline.reference_cache:
                continue
            ref = copy.deepcopy(pipeline.reference_cache[p["name"]]["pcd_down"])
            ref.transform(p["transformation"])
            ref.paint_uniform_color(colors[i % len(colors)])
            vis.append(ref)

        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.03)
        vis.append(coord)

        o3d.visualization.draw_geometries(
            vis, window_name="BinPicking Pipeline Result",
            width=1280, height=960,
        )

    print(f"\n{'='*70}")
    print("  빈피킹 파이프라인 완료!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
