"""
CAD 라이브러리 — STL → 레퍼런스 포인트 클라우드 + FPFH 사전 계산
================================================================

오프라인 준비 (카메라 입고 전 필수):
  1) bin_picking/models/cad/*.stl 로드 (trimesh)
  2) 각 CAD 모델 표면에서 10,000점 균일 샘플링 → 레퍼런스 포인트 클라우드
  3) 다운샘플링 → 법선 추정 → FPFH(33D) 특징 사전 계산
  4) pickle 저장:
     - models/reference_clouds/{name}.pkl  (포인트 + 법선)
     - models/fpfh_features/{name}.pkl     (FPFH 33D 특징)

STL 변경 시 재실행하면 캐시가 갱신됨 (MD5 해시 비교로 변경 감지).

파라미터 (논문 리뷰 확정):
  - voxel_size: 2mm (0.002m)
  - normal_radius: 8mm (voxel × 4)
  - FPFH radius: 10mm (voxel × 5)
  - 샘플링: 10,000점 (Poisson Disk)

사용법:
  # 전체 빌드 (최초 또는 STL 변경 시)
  python bin_picking/src/recognition/cad_library.py --build

  # 변경된 STL만 갱신
  python bin_picking/src/recognition/cad_library.py --build --incremental

  # 캐시 상태 확인
  python bin_picking/src/recognition/cad_library.py --status

  # 런타임 로드 테스트
  python bin_picking/src/recognition/cad_library.py --load-test

실행 환경: source .venv/binpick/bin/activate
"""

import argparse
import hashlib
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh

# Open3D는 사용 시점에 임포트 (trimesh만으로 STL 로드 가능)
try:
    import open3d as o3d
except ImportError:
    o3d = None


# ============================================================
# 경로 설정
# ============================================================
# bin_picking/ 루트 기준 상대 경로
_BINPICK_ROOT = Path(__file__).resolve().parent.parent.parent
CAD_DIR = _BINPICK_ROOT / "models" / "cad"
REF_CLOUD_DIR = _BINPICK_ROOT / "models" / "reference_clouds"
FPFH_DIR = _BINPICK_ROOT / "models" / "fpfh_features"
HASH_CACHE_PATH = _BINPICK_ROOT / "models" / ".stl_hashes.pkl"


# ============================================================
# 파라미터 (논문 리뷰 확정값)
# ============================================================
VOXEL_SIZE = 0.002          # 2mm
NORMAL_RADIUS = VOXEL_SIZE * 4   # 8mm
NORMAL_MAX_NN = 30
FPFH_RADIUS = VOXEL_SIZE * 5    # 10mm
FPFH_MAX_NN = 100
NUM_SAMPLE_POINTS = 10_000      # STL 표면 균일 샘플링 포인트 수


# ============================================================
# 유틸리티
# ============================================================
def compute_file_md5(filepath: Path) -> str:
    """파일의 MD5 해시를 계산한다."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# CADLibrary 클래스
# ============================================================
class CADLibrary:
    """STL CAD 모델 라이브러리 — 레퍼런스 클라우드 + FPFH 캐시 관리.

    빌드 시: STL → trimesh 로드 → 10,000점 Poisson Disk 샘플링 →
             Open3D 다운샘플링 → 법선 → FPFH → pickle 저장

    런타임 시: pickle 로드 → Open3D 객체 복원 → PoseEstimator에 전달
    """

    def __init__(
        self,
        cad_dir: Path = CAD_DIR,
        ref_cloud_dir: Path = REF_CLOUD_DIR,
        fpfh_dir: Path = FPFH_DIR,
        voxel_size: float = VOXEL_SIZE,
        num_sample_points: int = NUM_SAMPLE_POINTS,
    ):
        self.cad_dir = Path(cad_dir)
        self.ref_cloud_dir = Path(ref_cloud_dir)
        self.fpfh_dir = Path(fpfh_dir)
        self.voxel_size = voxel_size
        self.num_sample_points = num_sample_points

        # 파생 파라미터
        self.normal_radius = voxel_size * 4
        self.normal_max_nn = NORMAL_MAX_NN
        self.fpfh_radius = voxel_size * 5
        self.fpfh_max_nn = FPFH_MAX_NN

        # 런타임 캐시 (load 후 메모리에 보관)
        self._cache: Dict[str, Dict[str, Any]] = {}

    # ============================================================
    # STL 파일 탐색
    # ============================================================
    def list_stl_files(self) -> List[Path]:
        """cad 디렉토리의 STL 파일 목록을 반환한다."""
        if not self.cad_dir.exists():
            return []
        files = sorted(self.cad_dir.glob("*.stl"))
        return [f for f in files if f.is_file()]

    def get_part_name(self, stl_path: Path) -> str:
        """STL 파일 경로에서 부품 이름을 추출한다."""
        return stl_path.stem  # 확장자 제외한 파일명

    # ============================================================
    # 변경 감지 (MD5 해시)
    # ============================================================
    def _load_hash_cache(self) -> Dict[str, str]:
        """저장된 STL 해시 캐시를 로드한다."""
        if HASH_CACHE_PATH.exists():
            with open(HASH_CACHE_PATH, "rb") as f:
                return pickle.load(f)
        return {}

    def _save_hash_cache(self, hashes: Dict[str, str]):
        """STL 해시 캐시를 저장한다."""
        HASH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HASH_CACHE_PATH, "wb") as f:
            pickle.dump(hashes, f)

    def get_changed_files(self) -> Tuple[List[Path], List[str]]:
        """변경/신규 STL 파일과 삭제된 파일을 감지한다.

        Returns:
            (changed_files, removed_names): 변경/신규 STL 경로 리스트, 삭제된 부품 이름 리스트
        """
        old_hashes = self._load_hash_cache()
        stl_files = self.list_stl_files()

        current_names = set()
        changed = []

        for stl_path in stl_files:
            name = self.get_part_name(stl_path)
            current_names.add(name)
            current_hash = compute_file_md5(stl_path)

            if name not in old_hashes or old_hashes[name] != current_hash:
                changed.append(stl_path)

        # 삭제된 파일 감지
        removed = [name for name in old_hashes if name not in current_names]

        return changed, removed

    # ============================================================
    # 단일 STL 처리
    # ============================================================
    def process_single(self, stl_path: Path) -> Dict[str, Any]:
        """단일 STL 파일을 처리하여 레퍼런스 데이터를 생성한다.

        Args:
            stl_path: STL 파일 경로

        Returns:
            dict: {
                "part_name": str,
                "points": ndarray (N, 3),
                "normals": ndarray (N, 3),
                "fpfh": ndarray (33, N),
                "bbox_features": dict,
                "num_points_original": int,  # 샘플링 포인트 수
                "num_points_downsampled": int,
                "mesh_vertices": int,
                "mesh_faces": int,
            }
        """
        if o3d is None:
            raise ImportError("Open3D가 필요합니다: pip install open3d")

        part_name = self.get_part_name(stl_path)

        # 1. trimesh로 STL 로드 (단위: mm → m 변환 확인)
        mesh_tri = trimesh.load(str(stl_path))
        if not isinstance(mesh_tri, trimesh.Trimesh):
            raise ValueError(f"{stl_path.name}: 유효한 Trimesh가 아닙니다")

        mesh_vertices = len(mesh_tri.vertices)
        mesh_faces = len(mesh_tri.faces)

        # STL 단위 감지: 바운딩 박스 최대 치수가 1m 초과면 mm 단위로 간주
        bbox_extent = mesh_tri.bounding_box.extents
        max_extent = max(bbox_extent)
        if max_extent > 1.0:
            # mm → m 변환
            mesh_tri.apply_scale(0.001)
            unit_note = f"mm→m 변환 (max_extent={max_extent:.1f}mm)"
        else:
            unit_note = f"m 단위 (max_extent={max_extent*1000:.1f}mm)"

        # 2. 10,000점 균일 샘플링 (Poisson Disk에 가까운 균일 분포)
        points_sampled, face_indices = trimesh.sample.sample_surface(
            mesh_tri, self.num_sample_points
        )
        num_points_original = len(points_sampled)

        # 3. Open3D 포인트 클라우드 생성
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points_sampled)

        # 4. Voxel 다운샘플링
        pcd_down = pcd.voxel_down_sample(self.voxel_size)
        num_points_down = len(pcd_down.points)

        # 5. 법선 추정 + 방향 정렬 (원점 기준 — 레퍼런스 모델)
        pcd_down.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.normal_radius, max_nn=self.normal_max_nn
            )
        )
        pcd_down.orient_normals_towards_camera_location(
            camera_location=np.array([0.0, 0.0, 0.0])
        )

        # 6. FPFH 특징 계산
        fpfh = o3d.pipelines.registration.compute_fpfh_feature(
            pcd_down,
            o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.fpfh_radius, max_nn=self.fpfh_max_nn
            ),
        )

        # 7. 바운딩 박스 특징 (SizeFilter용) — OBB 사용 (회전 불변)
        if len(pcd_down.points) >= 4:
            obb = pcd_down.get_oriented_bounding_box()
            extent = np.sort(obb.extent)
        else:
            bbox = pcd_down.get_axis_aligned_bounding_box()
            extent = np.sort(bbox.get_extent())
        extent = np.maximum(extent, 1e-6)
        bbox_features = {
            "extent_x": float(extent[0]),
            "extent_y": float(extent[1]),
            "extent_z": float(extent[2]),
            "volume": float(np.prod(extent)),
            "diagonal": float(np.linalg.norm(extent)),
        }

        return {
            "part_name": part_name,
            "points": np.asarray(pcd_down.points),
            "normals": np.asarray(pcd_down.normals),
            "fpfh": np.asarray(fpfh.data),  # (33, N)
            "bbox_features": bbox_features,
            "num_points_original": num_points_original,
            "num_points_downsampled": num_points_down,
            "mesh_vertices": mesh_vertices,
            "mesh_faces": mesh_faces,
            "unit_note": unit_note,
            "voxel_size": self.voxel_size,
            "fpfh_radius": self.fpfh_radius,
            "normal_radius": self.normal_radius,
        }

    # ============================================================
    # 저장
    # ============================================================
    def save_reference(self, data: Dict[str, Any]):
        """레퍼런스 데이터를 pickle로 저장한다.

        reference_clouds/{name}.pkl — 포인트 + 법선 + 바운딩 박스 + 메타
        fpfh_features/{name}.pkl    — FPFH 33D 특징 + 메타
        """
        self.ref_cloud_dir.mkdir(parents=True, exist_ok=True)
        self.fpfh_dir.mkdir(parents=True, exist_ok=True)

        name = data["part_name"]

        # 레퍼런스 클라우드
        ref_data = {
            "part_name": name,
            "points": data["points"],
            "normals": data["normals"],
            "bbox_features": data["bbox_features"],
            "num_points_original": data["num_points_original"],
            "num_points_downsampled": data["num_points_downsampled"],
            "mesh_vertices": data["mesh_vertices"],
            "mesh_faces": data["mesh_faces"],
            "unit_note": data["unit_note"],
            "voxel_size": data["voxel_size"],
        }
        ref_path = self.ref_cloud_dir / f"{name}.pkl"
        with open(ref_path, "wb") as f:
            pickle.dump(ref_data, f)

        # FPFH 특징
        fpfh_data = {
            "part_name": name,
            "fpfh": data["fpfh"],  # (33, N)
            "fpfh_radius": data["fpfh_radius"],
            "normal_radius": data["normal_radius"],
            "voxel_size": data["voxel_size"],
            "num_points": data["num_points_downsampled"],
        }
        fpfh_path = self.fpfh_dir / f"{name}.pkl"
        with open(fpfh_path, "wb") as f:
            pickle.dump(fpfh_data, f)

    # ============================================================
    # 삭제 (STL 제거 시 캐시도 정리)
    # ============================================================
    def remove_reference(self, name: str):
        """레퍼런스 캐시 파일을 삭제한다."""
        ref_path = self.ref_cloud_dir / f"{name}.pkl"
        fpfh_path = self.fpfh_dir / f"{name}.pkl"
        if ref_path.exists():
            ref_path.unlink()
        if fpfh_path.exists():
            fpfh_path.unlink()

    # ============================================================
    # 전체 빌드
    # ============================================================
    def build(self, incremental: bool = False) -> Dict[str, Any]:
        """전체 STL을 처리하여 레퍼런스 캐시를 빌드한다.

        Args:
            incremental: True면 변경된 STL만 재처리

        Returns:
            dict: 빌드 결과 요약
        """
        stl_files = self.list_stl_files()
        if not stl_files:
            print(f"  [경고] STL 파일이 없습니다: {self.cad_dir}")
            return {"total": 0, "processed": 0, "errors": []}

        # 변경 감지
        if incremental:
            changed_files, removed_names = self.get_changed_files()
            files_to_process = changed_files

            # 삭제된 파일 캐시 정리
            for name in removed_names:
                self.remove_reference(name)
                print(f"  [삭제] {name}")
        else:
            files_to_process = stl_files
            removed_names = []

        print(f"  STL 총: {len(stl_files)}개")
        if incremental:
            print(f"  변경/신규: {len(files_to_process)}개, 삭제: {len(removed_names)}개")
        print()

        # 해시 캐시 (빌드 후 저장)
        hash_cache = self._load_hash_cache()
        errors = []
        processed = 0
        total_time = 0.0

        for i, stl_path in enumerate(files_to_process):
            name = self.get_part_name(stl_path)
            t0 = time.time()

            try:
                data = self.process_single(stl_path)
                self.save_reference(data)
                elapsed = time.time() - t0
                total_time += elapsed

                # 해시 업데이트
                hash_cache[name] = compute_file_md5(stl_path)

                ext = data["bbox_features"]
                print(
                    f"  [{i+1:>3}/{len(files_to_process)}] {name:>40}  "
                    f"mesh={data['mesh_faces']:>6} faces  "
                    f"pts={data['num_points_downsampled']:>5}  "
                    f"bbox=({ext['extent_x']*1000:.1f} x {ext['extent_y']*1000:.1f} x {ext['extent_z']*1000:.1f})mm  "
                    f"{elapsed:.2f}s  "
                    f"({data['unit_note']})"
                )
                processed += 1

            except Exception as e:
                elapsed = time.time() - t0
                errors.append({"name": name, "error": str(e)})
                print(f"  [{i+1:>3}/{len(files_to_process)}] {name:>40}  [ERROR] {e}")

        # 해시 캐시 저장
        self._save_hash_cache(hash_cache)

        # 출력 디렉토리 크기 계산
        ref_size = sum(f.stat().st_size for f in self.ref_cloud_dir.glob("*.pkl"))
        fpfh_size = sum(f.stat().st_size for f in self.fpfh_dir.glob("*.pkl"))

        summary = {
            "total": len(stl_files),
            "processed": processed,
            "errors": errors,
            "removed": removed_names,
            "total_time": total_time,
            "ref_cloud_size_kb": ref_size / 1024,
            "fpfh_size_kb": fpfh_size / 1024,
        }

        return summary

    # ============================================================
    # 런타임 로드 (PoseEstimator에서 사용)
    # ============================================================
    def load_all(self) -> Dict[str, Dict[str, Any]]:
        """모든 레퍼런스를 로드하여 PoseEstimator 호환 캐시를 반환한다.

        Returns:
            {name: {"pcd_down": PointCloud, "fpfh": Feature, "bbox_features": dict}}
        """
        if o3d is None:
            raise ImportError("Open3D가 필요합니다: pip install open3d")

        cache = {}
        ref_files = sorted(self.ref_cloud_dir.glob("*.pkl"))

        for ref_path in ref_files:
            name = ref_path.stem
            fpfh_path = self.fpfh_dir / f"{name}.pkl"

            if not fpfh_path.exists():
                print(f"  [경고] FPFH 없음: {name} → 건너뜀")
                continue

            with open(ref_path, "rb") as f:
                ref_data = pickle.load(f)
            with open(fpfh_path, "rb") as f:
                fpfh_data = pickle.load(f)

            # Open3D 객체 복원
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(ref_data["points"])
            pcd.normals = o3d.utility.Vector3dVector(ref_data["normals"])

            fpfh = o3d.pipelines.registration.Feature()
            fpfh.data = fpfh_data["fpfh"]

            cache[name] = {
                "pcd_down": pcd,
                "fpfh": fpfh,
                "bbox_features": ref_data["bbox_features"],
            }

        self._cache = cache
        return cache

    def load_single(self, name: str) -> Optional[Dict[str, Any]]:
        """단일 레퍼런스를 로드한다."""
        if name in self._cache:
            return self._cache[name]

        ref_path = self.ref_cloud_dir / f"{name}.pkl"
        fpfh_path = self.fpfh_dir / f"{name}.pkl"

        if not ref_path.exists() or not fpfh_path.exists():
            return None

        with open(ref_path, "rb") as f:
            ref_data = pickle.load(f)
        with open(fpfh_path, "rb") as f:
            fpfh_data = pickle.load(f)

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(ref_data["points"])
        pcd.normals = o3d.utility.Vector3dVector(ref_data["normals"])

        fpfh = o3d.pipelines.registration.Feature()
        fpfh.data = fpfh_data["fpfh"]

        entry = {
            "pcd_down": pcd,
            "fpfh": fpfh,
            "bbox_features": ref_data["bbox_features"],
        }
        self._cache[name] = entry
        return entry

    # ============================================================
    # 상태 확인
    # ============================================================
    def status(self) -> Dict[str, Any]:
        """캐시 상태를 반환한다."""
        stl_files = self.list_stl_files()
        ref_files = sorted(self.ref_cloud_dir.glob("*.pkl")) if self.ref_cloud_dir.exists() else []
        fpfh_files = sorted(self.fpfh_dir.glob("*.pkl")) if self.fpfh_dir.exists() else []

        stl_names = {self.get_part_name(f) for f in stl_files}
        ref_names = {f.stem for f in ref_files}
        fpfh_names = {f.stem for f in fpfh_files}

        # 캐시가 있는데 STL이 없는 파일 (정리 대상)
        orphan_refs = ref_names - stl_names
        orphan_fpfh = fpfh_names - stl_names

        # STL이 있는데 캐시가 없는 파일 (빌드 필요)
        missing_refs = stl_names - ref_names
        missing_fpfh = stl_names - fpfh_names

        # 변경 감지
        changed, removed = self.get_changed_files()

        return {
            "stl_count": len(stl_files),
            "ref_count": len(ref_files),
            "fpfh_count": len(fpfh_files),
            "missing": sorted(missing_refs | missing_fpfh),
            "orphan": sorted(orphan_refs | orphan_fpfh),
            "changed": [self.get_part_name(f) for f in changed],
            "removed": removed,
        }


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="CAD 라이브러리 — STL → 레퍼런스 포인트 클라우드 + FPFH 캐시"
    )
    parser.add_argument("--build", action="store_true", help="전체 STL 빌드")
    parser.add_argument("--incremental", action="store_true", help="변경된 STL만 재처리 (--build와 함께)")
    parser.add_argument("--status", action="store_true", help="캐시 상태 확인")
    parser.add_argument("--load-test", action="store_true", help="런타임 로드 테스트")
    parser.add_argument("--cad-dir", type=str, default=None, help="CAD 디렉토리 경로 (기본: models/cad/)")
    args = parser.parse_args()

    lib = CADLibrary()
    if args.cad_dir:
        lib.cad_dir = Path(args.cad_dir)

    if args.status:
        print_section("CAD 라이브러리 상태")
        st = lib.status()
        print(f"  STL 파일:        {st['stl_count']}개")
        print(f"  레퍼런스 캐시:   {st['ref_count']}개")
        print(f"  FPFH 캐시:       {st['fpfh_count']}개")
        if st["missing"]:
            print(f"  빌드 필요:       {', '.join(st['missing'])}")
        if st["changed"]:
            print(f"  변경됨:          {', '.join(st['changed'])}")
        if st["orphan"]:
            print(f"  고아 캐시:       {', '.join(st['orphan'])}")
        if not st["missing"] and not st["changed"]:
            print(f"  → 모든 캐시 최신 상태")

    elif args.build:
        print_section("CAD 라이브러리 빌드")
        summary = lib.build(incremental=args.incremental)

        print_section("빌드 결과")
        print(f"  STL 총:          {summary['total']}개")
        print(f"  처리 완료:       {summary['processed']}개")
        if summary["errors"]:
            print(f"  오류:            {len(summary['errors'])}개")
            for err in summary["errors"]:
                print(f"    - {err['name']}: {err['error']}")
        if summary["removed"]:
            print(f"  삭제됨:          {', '.join(summary['removed'])}")
        print(f"  총 소요 시간:    {summary['total_time']:.1f}s")
        print(f"  레퍼런스 크기:   {summary['ref_cloud_size_kb']:.0f} KB")
        print(f"  FPFH 크기:       {summary['fpfh_size_kb']:.0f} KB")
        print(f"  합계:            {(summary['ref_cloud_size_kb'] + summary['fpfh_size_kb']):.0f} KB")

    elif args.load_test:
        print_section("런타임 로드 테스트")
        t0 = time.time()
        cache = lib.load_all()
        elapsed = time.time() - t0

        print(f"  로드 모델:       {len(cache)}종")
        print(f"  로드 시간:       {elapsed*1000:.1f}ms")
        print()

        if cache:
            header = f"  {'부품명':>40}  {'포인트':>6}  {'FPFH':>10}  {'bbox (mm)':>30}"
            print(header)
            print(f"  {'-'*95}")

            for name, data in sorted(cache.items()):
                n_pts = len(data["pcd_down"].points)
                fpfh_shape = f"{data['fpfh'].dimension()}D x {data['fpfh'].num()}"
                bb = data["bbox_features"]
                bbox_str = f"({bb['extent_x']*1000:.1f} x {bb['extent_y']*1000:.1f} x {bb['extent_z']*1000:.1f})"
                print(f"  {name:>40}  {n_pts:>6}  {fpfh_shape:>10}  {bbox_str:>30}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
