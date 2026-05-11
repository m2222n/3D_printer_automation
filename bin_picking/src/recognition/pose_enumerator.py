"""
안정 자세 Enumeration — STL → stable_poses.yaml
=================================================

대표님 5/6 지시 #3 (X/Y 각도 데이터 고민)의 핵심 답변 도구.

물체가 평면(빈 바닥)에 놓였을 때 안정한 자세를 자동 추출한다.

원리:
  - 안정 자세 = 무게중심(COM)의 수직 투영이 지지면(support polygon) 내부에 있는 자세
  - trimesh.poses.compute_stable_poses() 활용 (convex hull + COM 기반)
  - 각 자세의 quasi-static 확률 (랜덤 drop 시 안착 확률) 반환

사용:
    # 단일 STL 분석
    python bin_picking/src/recognition/pose_enumerator.py --stl bin_picking/models/cad/plate_e.stl

    # 5종 우선 분석 (사진 추정 부품)
    python bin_picking/src/recognition/pose_enumerator.py --priority

    # 29종 전체 분석 → yaml 생성
    python bin_picking/src/recognition/pose_enumerator.py --all --output bin_picking/config/stable_poses.yaml

    # 확률 임계 조정 (기본 0.05 = 5% 이상만)
    python bin_picking/src/recognition/pose_enumerator.py --all --threshold 0.10

출력 형식 (YAML):
    parts:
      plate_e:
        extents_mm: [45.0, 56.0, 20.0]
        is_watertight: true
        stable_poses:
          - id: A
            probability: 0.419
            rotation_xyz_deg: [0.0, 0.0, 0.0]
            transform_4x4: [[...], [...], [...], [...]]
            pickable: null         # 그리퍼/마운팅 검토 후 결정 (TBD)
            regrasp_to: null       # 픽 불가 시 어느 자세로 (TBD)

학습 데이터 라벨링과의 연결:
    label = {
      "part_id": "05_plate_e",
      "stable_pose_id": "A",         # 본 yaml의 id
      "T_world": [4x4],              # FPFH+ICP 결과
      "rmse": 0.8,
    }

⚠️ 제약:
  - watertight=False STL은 COM 부정확 → 결과 신뢰도 낮음 (warning)
  - 모든 자세는 "현재 grasp_database.yaml"의 그래스프와 매핑 검증 필요 (별도 작업)
  - 'pickable' / 'regrasp_to' 값은 사람 판단 + 그래스프 시뮬레이션 필요 (이 도구는 자세 후보만 생성)

참고:
  - trimesh docs: https://trimesh.org/trimesh.poses.html
  - 1pager: docs/binpicking_learning_data_strategy_1pager_20260511.md (§ 3 Layer 1)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import trimesh
except ImportError:
    print("[ERROR] trimesh 미설치. pip install trimesh networkx")
    sys.exit(1)

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("[WARN] PyYAML 미설치 → JSON 출력만 가능. pip install pyyaml")


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CAD_DIR = PROJECT_ROOT / "bin_picking" / "models" / "cad"
DEFAULT_OUTPUT = PROJECT_ROOT / "bin_picking" / "config" / "stable_poses.yaml"

# 5종 우선 부품 (1pager § 2 자원 / 사진 추정)
# 캘리퍼스 실측 후 확정 필요하지만, 형상 추정으로 진행
PRIORITY_5 = [
    "plate_e.stl",                          # ⑤ 가장 단순 (앞/뒤 2자세)
    "bracket_case.stl",                     # ④ 박스형
    "main_body.stl",                        # ① 베이스 + ㄷ자
    "16_cam_f_bracket.stl",                 # ③ 소형 T자
    "guide_paper_roll_cover_left.stl",      # ② 다축 불안정
]


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class StablePose:
    """단일 안정 자세."""
    id: str                       # A, B, C, ...
    probability: float            # quasi-static 안착 확률 (0~1)
    rotation_xyz_deg: list[float] # [roll, pitch, yaw] in degrees (ZYX Euler)
    transform_4x4: list[list[float]]  # 4x4 동차 변환 행렬

    # 사람 / 후속 작업 검증 필요 (이 도구는 None 출력)
    pickable: Optional[bool] = None       # 픽 가능 여부 (그리퍼/마운팅 시뮬 후)
    regrasp_to: Optional[str] = None      # 픽 불가 시 어느 자세로 뒤집을지

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "probability": round(float(self.probability), 4),
            "rotation_xyz_deg": [round(float(x), 2) for x in self.rotation_xyz_deg],
            "transform_4x4": [[round(float(v), 6) for v in row] for row in self.transform_4x4],
            "pickable": self.pickable,
            "regrasp_to": self.regrasp_to,
        }
        return d


@dataclass
class PartPoses:
    """단일 부품의 안정 자세 컬렉션."""
    part_id: str
    stl_path: str
    extents_mm: list[float]
    is_watertight: bool
    com_mm: list[float]                # 무게중심 (mm)
    n_stable_poses_total: int          # threshold 적용 전 총 안정 자세 수
    top_pose_coverage: float           # 상위 자세들의 누적 확률 (얼마나 단순한가)
    stable_poses: list[StablePose] = field(default_factory=list)

    # 분석 메타
    threshold_used: float = 0.05
    sigma_used: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "part_id": self.part_id,
            "stl_path": self.stl_path,
            "extents_mm": [round(float(x), 2) for x in self.extents_mm],
            "is_watertight": self.is_watertight,
            "com_mm": [round(float(x), 2) for x in self.com_mm],
            "n_stable_poses_total": self.n_stable_poses_total,
            "top_pose_coverage": round(float(self.top_pose_coverage), 4),
            "threshold_used": self.threshold_used,
            "sigma_used": self.sigma_used,
            "timestamp": self.timestamp,
            "stable_poses": [p.to_dict() for p in self.stable_poses],
        }


# ============================================================
# 회전 분해 (Transform → ZYX Euler)
# ============================================================
def rotation_to_zyx_euler_deg(R: np.ndarray) -> tuple[float, float, float]:
    """3x3 회전 행렬 → ZYX Euler (roll, pitch, yaw) in degrees.

    ZYX 순서 (intrinsic): R = R_z(yaw) @ R_y(pitch) @ R_x(roll)
    HCR 펜던트 / Modbus와 동일 컨벤션.
    """
    sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(R[2, 1], R[2, 2])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = np.arctan2(R[1, 0], R[0, 0])
    else:
        roll = np.arctan2(-R[1, 2], R[1, 1])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = 0.0
    return float(np.degrees(roll)), float(np.degrees(pitch)), float(np.degrees(yaw))


# ============================================================
# 핵심: enumerate_part_poses()
# ============================================================
def enumerate_part_poses(
    stl_path: Path,
    part_id: Optional[str] = None,
    threshold: float = 0.05,
    sigma: float = 0.0,
    n_samples: int = 1,
    verbose: bool = True,
) -> Optional[PartPoses]:
    """단일 STL의 안정 자세를 추출한다.

    Args:
        stl_path: STL 파일 경로
        part_id: 부품 ID (None이면 파일명에서 stem 추출)
        threshold: 이 확률 미만 자세는 버림 (기본 0.05 = 5%)
        sigma: COM 샘플링 분산 (0 = 결정적)
        n_samples: COM 샘플링 횟수
        verbose: 진행 출력

    Returns:
        PartPoses (실패 시 None)
    """
    stl_path = Path(stl_path)
    if not stl_path.exists():
        if verbose:
            print(f"  [SKIP] STL 없음: {stl_path}")
        return None

    if part_id is None:
        part_id = stl_path.stem

    try:
        mesh = trimesh.load(str(stl_path), force="mesh")
    except Exception as e:
        if verbose:
            print(f"  [ERROR] STL 로드 실패: {e}")
        return None

    if not isinstance(mesh, trimesh.Trimesh):
        if verbose:
            print(f"  [ERROR] Trimesh 아님: {type(mesh)}")
        return None

    extents = mesh.extents
    is_watertight = bool(mesh.is_watertight)
    com = mesh.center_mass

    if verbose:
        print(f"\n  [{part_id}]")
        print(f"    vertices: {len(mesh.vertices)}, faces: {len(mesh.faces)}")
        print(f"    extents: {extents[0]:.1f}×{extents[1]:.1f}×{extents[2]:.1f} mm")
        print(f"    watertight: {is_watertight}")
        if not is_watertight:
            print("    ⚠️  non-watertight — COM 부정확 가능, 결과 신뢰도 ↓")

    # 안정 자세 계산
    t0 = time.time()
    try:
        transforms, probs = trimesh.poses.compute_stable_poses(
            mesh,
            sigma=sigma,
            n_samples=n_samples,
            threshold=0.0,  # 일단 전체 받고 후처리에서 필터
        )
    except Exception as e:
        if verbose:
            print(f"    [ERROR] compute_stable_poses 실패: {e}")
        return None

    elapsed = time.time() - t0

    n_total = len(transforms)
    if n_total == 0:
        if verbose:
            print(f"    [WARN] 안정 자세 0개")
        return None

    # 임계값 필터
    filtered_pairs = [(T, p) for T, p in zip(transforms, probs) if p >= threshold]

    # 상위 N개 누적 확률 (단순성 지표)
    top3_coverage = float(np.sum(probs[:3])) if len(probs) >= 3 else float(np.sum(probs))

    # StablePose 객체 생성 (A, B, C, ...)
    stable_poses = []
    for i, (T, p) in enumerate(filtered_pairs):
        pose_id = chr(ord("A") + i) if i < 26 else f"P{i}"
        roll, pitch, yaw = rotation_to_zyx_euler_deg(T[:3, :3])
        stable_poses.append(
            StablePose(
                id=pose_id,
                probability=float(p),
                rotation_xyz_deg=[roll, pitch, yaw],
                transform_4x4=T.tolist(),
                pickable=None,
                regrasp_to=None,
            )
        )

    if verbose:
        print(f"    안정 자세 {n_total}개 (threshold {threshold} 후 {len(stable_poses)}개)")
        print(f"    top-3 누적 확률: {top3_coverage:.3f} ({_simplicity_label(top3_coverage)})")
        print(f"    계산 시간: {elapsed:.2f}s")
        for sp in stable_poses[:5]:
            r, p, y = sp.rotation_xyz_deg
            print(
                f"      [{sp.id}] prob={sp.probability:.3f}  "
                f"rx={r:+7.1f}  ry={p:+7.1f}  rz={y:+7.1f}"
            )
        if len(stable_poses) > 5:
            print(f"      ... +{len(stable_poses) - 5} more")

    return PartPoses(
        part_id=part_id,
        stl_path=str(stl_path.relative_to(PROJECT_ROOT)) if stl_path.is_relative_to(PROJECT_ROOT) else str(stl_path),
        extents_mm=extents.tolist(),
        is_watertight=is_watertight,
        com_mm=com.tolist(),
        n_stable_poses_total=n_total,
        top_pose_coverage=top3_coverage,
        stable_poses=stable_poses,
        threshold_used=threshold,
        sigma_used=sigma,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _simplicity_label(top3: float) -> str:
    """상위 3자세 누적 확률 → 사람 친화 라벨."""
    if top3 >= 0.90:
        return "매우 단순 (top-3 ≥ 90%)"
    if top3 >= 0.75:
        return "단순 (top-3 ≥ 75%)"
    if top3 >= 0.50:
        return "중간 (top-3 ≥ 50%)"
    return "복잡 (다축 불안정)"


# ============================================================
# 일괄 처리 + YAML 출력
# ============================================================
def enumerate_multiple(
    stl_paths: list[Path],
    threshold: float = 0.05,
    sigma: float = 0.0,
    verbose: bool = True,
) -> dict[str, PartPoses]:
    """여러 STL 일괄 처리."""
    results: dict[str, PartPoses] = {}
    for stl_path in stl_paths:
        result = enumerate_part_poses(
            stl_path, threshold=threshold, sigma=sigma, verbose=verbose
        )
        if result is not None:
            results[result.part_id] = result
    return results


def save_yaml(results: dict[str, PartPoses], output_path: Path) -> None:
    """결과를 YAML 파일로 저장."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "_meta": {
            "tool": "pose_enumerator.py",
            "version": "1.0",
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "description": (
                "STL → 안정 자세 enumeration (trimesh.poses.compute_stable_poses 기반). "
                "대표님 5/6 지시 #3 X/Y 각도 데이터 명세 도구."
            ),
            "note": (
                "pickable / regrasp_to는 사람 판단 + 그래스프 시뮬 후 채워야 함. "
                "본 도구는 자세 후보 + 확률만 생성."
            ),
        },
        "parts": {pid: p.to_dict() for pid, p in results.items()},
    }

    if HAS_YAML and output_path.suffix in (".yaml", ".yml"):
        with output_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    else:
        # PyYAML 없으면 JSON으로
        json_path = output_path.with_suffix(".json")
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        output_path = json_path

    print(f"\n  ✅ 저장: {output_path}")
    print(f"     부품 수: {len(results)}")
    print(f"     크기: {output_path.stat().st_size / 1024:.1f} KB")


def print_summary(results: dict[str, PartPoses]) -> None:
    """결과 요약 표 출력."""
    print("\n" + "=" * 80)
    print("요약")
    print("=" * 80)
    print(f"{'부품':<35} {'extents (mm)':<22} {'자세':<6} {'top3':<8} {'난이도'}")
    print("-" * 80)
    for pid, p in results.items():
        ext = f"{p.extents_mm[0]:.0f}×{p.extents_mm[1]:.0f}×{p.extents_mm[2]:.0f}"
        difficulty = _simplicity_label(p.top_pose_coverage)
        print(
            f"{pid:<35} {ext:<22} "
            f"{len(p.stable_poses):>2}/{p.n_stable_poses_total:<3} "
            f"{p.top_pose_coverage:.3f}  {difficulty}"
        )


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="STL → 안정 자세 yaml 자동 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("사용:")[1] if "사용:" in (__doc__ or "") else "",
    )

    # 입력 (3가지 모드 중 하나 선택)
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--stl", type=Path, help="단일 STL 분석")
    mode.add_argument("--priority", action="store_true", help="우선 5종만 분석")
    mode.add_argument("--all", action="store_true", help="29종 전체 분석")

    # 옵션
    p.add_argument("--threshold", type=float, default=0.05, help="확률 임계 (기본 0.05)")
    p.add_argument("--sigma", type=float, default=0.0, help="COM 샘플링 분산 (기본 0=결정적)")
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"출력 yaml 경로 (기본 {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)})",
    )
    p.add_argument("--no-save", action="store_true", help="yaml 저장 안 함 (분석만)")
    p.add_argument("--quiet", action="store_true", help="개별 부품 출력 최소화")

    args = p.parse_args()

    # 기본 모드 = --priority (안전한 default)
    if not args.stl and not args.priority and not args.all:
        print("[INFO] 모드 미지정 → --priority (5종) 실행")
        args.priority = True

    return args


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("STL 안정 자세 Enumeration")
    print(f"Threshold: {args.threshold}")
    print(f"Sigma: {args.sigma}")
    print("=" * 60)

    # STL 경로 수집
    if args.stl:
        stl_paths = [args.stl]
    elif args.priority:
        stl_paths = [CAD_DIR / fname for fname in PRIORITY_5]
    else:  # --all
        stl_paths = sorted(CAD_DIR.glob("*.stl"))

    if not stl_paths:
        print(f"[ERROR] STL 파일 없음. CAD_DIR={CAD_DIR}")
        return 1

    print(f"분석 대상: {len(stl_paths)}개")
    for p in stl_paths:
        marker = "✓" if p.exists() else "✗"
        print(f"  {marker} {p.name}")

    # 일괄 처리
    results = enumerate_multiple(
        stl_paths, threshold=args.threshold, sigma=args.sigma, verbose=not args.quiet
    )

    if not results:
        print("\n[FAIL] 결과 0개")
        return 1

    # 요약 출력
    print_summary(results)

    # 저장
    if not args.no_save:
        save_yaml(results, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
