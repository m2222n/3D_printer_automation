"""
자동 라벨링 파이프라인 — 단독 부품 캡처 → L1~L4 → GT pose 라벨
=================================================================

3-Layer 학습 데이터 전략의 Layer 3 핵심 도구.
대표님 5/6 지시 #2 (실물 다각도 학습 데이터) 구현체.

입력: 단독 부품 캡처 디렉토리 (Basler 또는 D435)
  capture_dir/
    frame_0001/  (또는 다른 명명)
      depth.npy
      color.npy (선택)
      confidence.npy (선택, Basler만)
      meta.json   (intrinsics + depth_scale)
    frame_0002/
    ...

처리: 프레임별 L1~L4 파이프라인
  1. depth → PointCloud (depth_to_pointcloud)
  2. L2 CloudFilter (전처리)
  3. L3 DBSCANSegmenter (단독 부품 가정 → 최대 클러스터)
  4. L4 PoseEstimator.match_against_references → 6DoF GT
  5. stable_pose_id 자동 매핑 (회전 비교)
  6. 품질 게이트 (RMSE / fitness / 클러스터 크기)

출력: dataset/<part_id>/pose_<sid>/
  auto/    — 자동 라벨 통과 (RMSE < 1.5mm 등)
    <frame>_rgb.png, _depth.npy, _label.json
  review/  — 수동 보정 큐
    <frame>_rgb.png, _depth.npy, _label.json (with reason)

라벨 형식 (1pager § 4):
  {
    "part_id": "plate_e",
    "stable_pose_id": "A",
    "T_world": [[4x4]],
    "rmse": 0.8,
    "fitness": 0.92,
    "n_points": 5234,
    "source_frame": "capture_dir/frame_0001",
    "camera": "blaze-112",
    "timestamp": "2026-05-15T14:00:00",
    "auto_status": "ACCEPT" | "REVIEW",
    "review_reason": null | "rmse_high" | "low_fitness" | ...
  }

사용:
  # 단일 부품 디렉토리 처리 (가장 가능성 높은 매칭으로 part 자동 결정)
  python bin_picking/src/labeling/auto_label.py \\
    --capture-dir bin_picking/models/basler_frames/plate_e_test/ \\
    --output dataset/

  # 부품 미리 지정 (다른 부품 후보 차단)
  python bin_picking/src/labeling/auto_label.py \\
    --capture-dir captures/plate_e_yaw_sweep/ \\
    --part plate_e \\
    --output dataset/

  # 시뮬 모드 (Basler/D435 없는 환경에서 코드 검증용)
  python bin_picking/src/labeling/auto_label.py --simulate

설계 결정:
  - 단독 부품 가정 → DBSCAN 가장 큰 클러스터 사용 (overlap 없음)
  - stable_pose_id는 yaml의 transform_4x4와 회전 비교 (Frobenius norm)
  - 카메라 종류 무관 (depth + intrinsics만 있으면 됨, Basler/D435 호환)
  - 품질 게이트는 보수적으로 시작 (자동 라벨 신뢰도 우선)

⚠️ 카메라 입고 후 캘리브된 intrinsics가 들어가야 함 (현재는 추정값 사용)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# 품질 게이트 (자동 라벨 ACCEPT 기준)
# ============================================================
@dataclass
class QualityGate:
    """자동 라벨링 통과 기준. 보수적으로 시작."""
    max_rmse_mm: float = 1.5          # RMSE 임계 (mm)
    min_fitness: float = 0.3          # ICP fitness 임계
    min_cluster_points: int = 200     # 클러스터 최소 포인트
    max_cluster_points: int = 50000   # 클러스터 최대 (너무 크면 전경 분리 실패)
    min_pose_match_score: float = 0.85  # stable_pose 매칭 신뢰도 (1 - normalized rotation distance)


# ============================================================
# 라벨 결과 데이터 클래스
# ============================================================
@dataclass
class LabelResult:
    """프레임별 라벨링 결과."""
    source_frame: str
    part_id: Optional[str]
    stable_pose_id: Optional[str]
    pose_match_score: float          # stable_pose 매칭 신뢰도 (0~1)
    T_world: Optional[list]          # 4x4 변환 (list of lists, JSON 직렬화)
    rmse: float
    fitness: float
    n_points: int
    camera: str
    timestamp: str
    auto_status: str                 # "ACCEPT" | "REVIEW" | "FAIL"
    review_reason: Optional[str]     # ACCEPT면 None
    pipeline_time_sec: float

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# stable_pose 자동 매핑
# ============================================================
def rotation_distance(R1: np.ndarray, R2: np.ndarray) -> float:
    """두 회전 행렬 간 거리 (rad). Frobenius norm 기반.

    `||R1 - R2||_F` 가 아니라, R1·R2.T 의 trace로 각도 추출:
      trace(R) = 1 + 2·cos(θ)  →  θ = arccos((trace - 1) / 2)
    """
    R = R1 @ R2.T
    trace = np.clip(np.trace(R), -1.0, 3.0)
    cos_theta = (trace - 1) / 2
    cos_theta = float(np.clip(cos_theta, -1.0, 1.0))
    return float(np.arccos(cos_theta))


def canonicalize_pose_id(pose_id: str, symmetry_groups: Optional[list]) -> str:
    """대칭 그룹 처리: group 내 자세는 group의 첫 id로 통일.

    예: symmetry_groups=[["A","B"]] 이고 pose_id="B" → "A" 반환.
    그룹에 없으면 원래 id 그대로.
    """
    if not symmetry_groups:
        return pose_id
    for group in symmetry_groups:
        if pose_id in group:
            return group[0]  # canonical = group의 첫 id
    return pose_id


def find_closest_stable_pose(
    T_world: np.ndarray, part_yaml: dict
) -> tuple[Optional[str], float]:
    """T_world의 회전을 stable_poses 중 가장 가까운 것에 매핑.

    Args:
        T_world: 4x4 변환 행렬 (현재 인식 결과)
        part_yaml: parts.<part_id> dict (pose_enumerator 결과)

    Returns:
        (stable_pose_id, match_score)
        match_score = 1 - (angular_distance / π), 1.0 = 완전 일치

    대칭 처리: part_yaml에 symmetry_groups가 있으면 group 내 자세는
    canonical id로 통일. 예: P5 main_body A·B 180° 대칭 → 둘 다 "A" 라벨.
    이 경우 match_score는 group 내 최소 거리로 계산 (대칭 자세 둘 다와 가까운 쪽).
    """
    stable_poses = part_yaml.get("stable_poses", [])
    if not stable_poses:
        return None, 0.0

    symmetry_groups = part_yaml.get("symmetry_groups")

    R_target = T_world[:3, :3]
    best_id = None
    best_dist_rad = float("inf")

    for sp in stable_poses:
        T_sp = np.array(sp["transform_4x4"])
        R_sp = T_sp[:3, :3]
        dist = rotation_distance(R_target, R_sp)
        if dist < best_dist_rad:
            best_dist_rad = dist
            best_id = sp["id"]

    # 대칭 그룹이 있으면 canonical id로 통일
    canonical_id = canonicalize_pose_id(best_id, symmetry_groups) if best_id else None

    # match_score: 0(180° 차이) ~ 1(완전 일치)
    score = 1.0 - (best_dist_rad / np.pi)
    return canonical_id, float(score)


# ============================================================
# 캡처 디렉토리 로더 (Basler/D435 호환)
# ============================================================
def list_capture_frames(capture_dir: Path) -> list[Path]:
    """캡처 디렉토리에서 프레임 서브폴더 목록 (depth.npy 있는 것만)."""
    capture_dir = Path(capture_dir)
    if not capture_dir.is_dir():
        return []

    # 패턴 1: capture_dir/frame_NNNN/depth.npy
    frame_dirs = [
        d for d in sorted(capture_dir.iterdir())
        if d.is_dir() and (d / "depth.npy").exists()
    ]
    if frame_dirs:
        return frame_dirs

    # 패턴 2: capture_dir 자체에 depth.npy (단일 프레임)
    if (capture_dir / "depth.npy").exists():
        return [capture_dir]

    return []


def load_frame(frame_dir: Path) -> Optional[dict]:
    """프레임 디렉토리에서 depth/color/intrinsics 로드.

    반환 형식:
        {
            "depth": np.ndarray,           # (H, W) uint16/uint32 mm
            "color": np.ndarray | None,    # (H, W, 3) BGR
            "confidence": np.ndarray | None,
            "intrinsics": dict,            # {width, height, fx, fy, cx, cy}
            "depth_scale": float,          # raw → m
            "name": str,
        }
    """
    frame_dir = Path(frame_dir)
    depth_path = frame_dir / "depth.npy"
    meta_path = frame_dir / "meta.json"
    if not depth_path.exists():
        return None

    depth = np.load(depth_path)

    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
    else:
        return None  # meta 없으면 intrinsics 모름 → skip

    depth_scale = meta.pop("depth_scale", 1000.0)
    # color_intrinsics는 별도, 메인은 depth_intrinsics 또는 평탄 dict
    color_intr = meta.pop("color_intrinsics", None)
    intr = meta  # 나머지 = depth intrinsics

    color = None
    color_path = frame_dir / "color.npy"
    if color_path.exists():
        color = np.load(color_path)

    confidence = None
    conf_path = frame_dir / "confidence.npy"
    if conf_path.exists():
        confidence = np.load(conf_path)

    return {
        "depth": depth,
        "color": color,
        "confidence": confidence,
        "intrinsics": intr,
        "color_intrinsics": color_intr,
        "depth_scale": depth_scale,
        "name": frame_dir.name,
    }


# ============================================================
# 핵심 파이프라인 (L1~L4)
# ============================================================
def process_frame(
    frame: dict,
    cad_library,
    pose_estimator,
    cloud_filter,
    segmenter,
    candidate_part: Optional[str] = None,
    verbose: bool = True,
) -> tuple[Optional[dict], Optional[str]]:
    """단일 프레임 L1~L4 처리.

    Returns:
        (best_match_dict, error_reason)
        best_match_dict: {"name", "fitness", "rmse", "transformation", "n_points"}
        둘 중 하나는 None
    """
    import open3d as o3d

    from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

    intr = frame["intrinsics"]

    # L1: depth → pointcloud
    pcd = depth_to_pointcloud(
        depth_map=frame["depth"],
        fx=intr["fx"],
        fy=intr["fy"],
        cx=intr["cx"],
        cy=intr["cy"],
        color_image=frame.get("color"),
        depth_scale=frame["depth_scale"],
        depth_min=0.1,
        depth_max=5.0,
        confidence_map=frame.get("confidence"),
    )

    if len(pcd.points) < 1000:
        return None, "too_few_points"

    # L2: 전처리 (CloudFilter API 변형 대응)
    try:
        for method_name in ("filter_pipeline", "filter", "process", "apply"):
            method = getattr(cloud_filter, method_name, None)
            if method is None:
                continue
            result = method(pcd)
            pcd_filtered = result[0] if isinstance(result, tuple) else result
            break
        else:
            raise RuntimeError("CloudFilter API 없음")
    except Exception as e:
        return None, f"l2_failed: {e}"

    if len(pcd_filtered.points) < 200:
        return None, "l2_too_few_points"

    # L3: DBSCAN (단독 부품 → 최대 클러스터)
    try:
        clusters = segmenter.segment(pcd_filtered)
    except Exception as e:
        return None, f"l3_failed: {e}"

    if not clusters:
        return None, "no_clusters"

    # 최대 클러스터 선택 (단독 부품 가정)
    largest = max(clusters, key=lambda c: len(c.pcd.points))
    n_points = len(largest.pcd.points)

    if n_points < 200:
        return None, "cluster_too_small"

    # L4: 매칭 (candidate_part 지정 시 그 부품만, 아니면 전체 후보)
    candidate_names = None
    if candidate_part:
        # CAD 라이브러리에 part_id 있는지 확인
        ref_cache = cad_library.reference_cache
        # 정확 매칭 또는 stem 매칭
        names = list(ref_cache.keys())
        match = [n for n in names if n == candidate_part or Path(n).stem == candidate_part]
        if match:
            candidate_names = match
        else:
            if verbose:
                print(f"    [WARN] candidate_part '{candidate_part}' not in CAD library")

    try:
        matches = pose_estimator.match_against_references(
            largest.pcd,
            cad_library.reference_cache,
            candidate_names=candidate_names,
        )
    except Exception as e:
        return None, f"l4_failed: {e}"

    if not matches:
        return None, "no_matches"

    # fitness 가장 높은 매칭 (이미 정렬돼 있음)
    best = matches[0]
    best["n_points"] = n_points
    return best, None


# ============================================================
# 메인 자동 라벨링
# ============================================================
def auto_label_directory(
    capture_dir: Path,
    output_dir: Path,
    stable_poses_yaml: Path,
    candidate_part: Optional[str] = None,
    camera_label: str = "unknown",
    gate: Optional[QualityGate] = None,
    verbose: bool = True,
) -> list[LabelResult]:
    """디렉토리 내 모든 프레임 자동 라벨링.

    Returns:
        LabelResult 리스트.
    """
    import yaml

    capture_dir = Path(capture_dir)
    output_dir = Path(output_dir)
    gate = gate or QualityGate()

    # 1. stable_poses.yaml 로드
    if not Path(stable_poses_yaml).exists():
        raise FileNotFoundError(
            f"stable_poses.yaml 없음: {stable_poses_yaml}. "
            f"먼저 pose_enumerator.py 실행 필요."
        )

    with open(stable_poses_yaml) as f:
        pose_db = yaml.safe_load(f)

    parts_db = pose_db.get("parts", {})
    if verbose:
        print(f"[stable_poses] {len(parts_db)}개 부품 로드: {list(parts_db.keys())[:5]}{'...' if len(parts_db) > 5 else ''}")

    # 2. CAD 라이브러리 + Pose Estimator 초기화 (지연 import — Open3D 필요)
    print("[init] CADLibrary + PoseEstimator 로드 중...")
    from bin_picking.src.recognition.cad_library import CADLibrary
    from bin_picking.src.recognition.pose_estimator import PoseEstimator
    from bin_picking.src.preprocessing.cloud_filter import CloudFilter
    from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter

    cad_lib = CADLibrary(voxel_size=0.002)
    # CAD 캐시 자동 로드 (이미 빌드돼 있다면)
    try:
        cad_lib.load_cache()
        n_loaded = len(cad_lib.reference_cache)
        if verbose:
            print(f"[cad_library] {n_loaded}개 레퍼런스 캐시 로드")
    except Exception as e:
        print(f"[ERROR] CAD 캐시 로드 실패: {e}")
        print("       먼저 cad_library.py로 캐시 빌드 필요")
        return []

    if not cad_lib.reference_cache:
        print("[ERROR] CAD 레퍼런스 0개. cad_library.py 빌드 먼저.")
        return []

    pose_est = PoseEstimator(voxel_size=0.002, use_fgr=True, refine_top_k=0)
    cloud_filt = CloudFilter(voxel_size=0.002)
    segmenter = DBSCANSegmenter(eps=0.008, min_points=100)

    # 3. 프레임 목록
    frame_dirs = list_capture_frames(capture_dir)
    if not frame_dirs:
        print(f"[ERROR] 프레임 없음: {capture_dir}")
        return []

    if verbose:
        print(f"[frames] {len(frame_dirs)}개 프레임 처리 시작")

    # 4. 프레임별 처리
    results: list[LabelResult] = []
    ts_now = time.strftime("%Y-%m-%dT%H:%M:%S")

    for i, frame_dir in enumerate(frame_dirs):
        if verbose:
            print(f"\n[{i + 1}/{len(frame_dirs)}] {frame_dir.name}")

        t0 = time.time()
        frame = load_frame(frame_dir)
        if frame is None:
            results.append(
                LabelResult(
                    source_frame=str(frame_dir),
                    part_id=None,
                    stable_pose_id=None,
                    pose_match_score=0.0,
                    T_world=None,
                    rmse=float("inf"),
                    fitness=0.0,
                    n_points=0,
                    camera=camera_label,
                    timestamp=ts_now,
                    auto_status="FAIL",
                    review_reason="frame_load_failed",
                    pipeline_time_sec=time.time() - t0,
                )
            )
            continue

        # 파이프라인 실행
        best, err = process_frame(
            frame, cad_lib, pose_est, cloud_filt, segmenter,
            candidate_part=candidate_part, verbose=verbose,
        )
        elapsed = time.time() - t0

        if best is None:
            if verbose:
                print(f"    [FAIL] {err}")
            results.append(
                LabelResult(
                    source_frame=str(frame_dir),
                    part_id=None,
                    stable_pose_id=None,
                    pose_match_score=0.0,
                    T_world=None,
                    rmse=float("inf"),
                    fitness=0.0,
                    n_points=0,
                    camera=camera_label,
                    timestamp=ts_now,
                    auto_status="FAIL",
                    review_reason=err,
                    pipeline_time_sec=elapsed,
                )
            )
            continue

        # 인식된 부품 ID
        recognized_part = Path(best["name"]).stem  # e.g. "plate_e.stl" -> "plate_e"
        rmse_mm = best["rmse"] * 1000  # m → mm
        T_world = best["transformation"]

        # stable_pose 매핑
        part_yaml = parts_db.get(recognized_part)
        if part_yaml is None:
            sp_id, sp_score = None, 0.0
            if verbose:
                print(f"    [WARN] '{recognized_part}'가 stable_poses.yaml에 없음")
        else:
            sp_id, sp_score = find_closest_stable_pose(T_world, part_yaml)

        # 품질 게이트
        status, reason = _evaluate_gate(
            rmse_mm=rmse_mm,
            fitness=best["fitness"],
            n_points=best["n_points"],
            pose_match_score=sp_score,
            gate=gate,
        )

        if verbose:
            print(
                f"    part={recognized_part}  pose={sp_id} (score {sp_score:.2f})  "
                f"rmse={rmse_mm:.2f}mm  fitness={best['fitness']:.2f}  "
                f"pts={best['n_points']}  →  {status}"
            )
            if reason:
                print(f"    reason: {reason}")

        result = LabelResult(
            source_frame=str(frame_dir),
            part_id=recognized_part,
            stable_pose_id=sp_id,
            pose_match_score=sp_score,
            T_world=T_world.tolist(),
            rmse=float(rmse_mm),
            fitness=float(best["fitness"]),
            n_points=int(best["n_points"]),
            camera=camera_label,
            timestamp=ts_now,
            auto_status=status,
            review_reason=reason,
            pipeline_time_sec=elapsed,
        )
        results.append(result)

        # 저장
        _save_labeled_frame(frame_dir, frame, result, output_dir)

    return results


def _evaluate_gate(
    rmse_mm: float, fitness: float, n_points: int, pose_match_score: float, gate: QualityGate
) -> tuple[str, Optional[str]]:
    """품질 게이트 평가."""
    if rmse_mm > gate.max_rmse_mm:
        return "REVIEW", f"rmse_high ({rmse_mm:.2f} > {gate.max_rmse_mm})"
    if fitness < gate.min_fitness:
        return "REVIEW", f"low_fitness ({fitness:.2f} < {gate.min_fitness})"
    if n_points < gate.min_cluster_points:
        return "REVIEW", f"cluster_small ({n_points} < {gate.min_cluster_points})"
    if n_points > gate.max_cluster_points:
        return "REVIEW", f"cluster_large ({n_points} > {gate.max_cluster_points})"
    if pose_match_score < gate.min_pose_match_score:
        return "REVIEW", f"pose_mismatch (score {pose_match_score:.2f} < {gate.min_pose_match_score})"
    return "ACCEPT", None


def _save_labeled_frame(
    frame_dir: Path, frame: dict, result: LabelResult, output_root: Path
) -> None:
    """라벨링된 프레임을 dataset 구조로 저장.

    출력:
      output_root/<part_id>/pose_<sid>/<auto|review|fail>/<frame_name>_{rgb,depth,label}.{png,npy,json}
    """
    output_root = Path(output_root)
    part_id = result.part_id or "unknown"
    sp_id = result.stable_pose_id or "X"
    status_dir = result.auto_status.lower()  # accept/review/fail

    dest = output_root / part_id / f"pose_{sp_id}" / status_dir
    dest.mkdir(parents=True, exist_ok=True)

    stem = frame_dir.name

    # depth 저장
    np.save(dest / f"{stem}_depth.npy", frame["depth"])

    # color 저장 (있으면)
    if frame.get("color") is not None:
        try:
            import cv2

            cv2.imwrite(str(dest / f"{stem}_rgb.png"), frame["color"])
        except ImportError:
            np.save(dest / f"{stem}_rgb.npy", frame["color"])

    # 라벨 저장
    with open(dest / f"{stem}_label.json", "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)


# ============================================================
# 요약 + 통계
# ============================================================
def print_summary(results: list[LabelResult]) -> None:
    print("\n" + "=" * 70)
    print("자동 라벨링 요약")
    print("=" * 70)

    n_total = len(results)
    n_accept = sum(1 for r in results if r.auto_status == "ACCEPT")
    n_review = sum(1 for r in results if r.auto_status == "REVIEW")
    n_fail = sum(1 for r in results if r.auto_status == "FAIL")

    print(f"전체: {n_total}")
    print(f"  ✅ ACCEPT: {n_accept} ({n_accept / max(n_total, 1) * 100:.1f}%)")
    print(f"  ⚠️  REVIEW: {n_review} ({n_review / max(n_total, 1) * 100:.1f}%)")
    print(f"  ❌ FAIL:   {n_fail} ({n_fail / max(n_total, 1) * 100:.1f}%)")

    if n_accept > 0:
        accepted = [r for r in results if r.auto_status == "ACCEPT"]
        rmse_vals = [r.rmse for r in accepted]
        fit_vals = [r.fitness for r in accepted]
        print("\n  ACCEPT 통계:")
        print(f"    RMSE      median {np.median(rmse_vals):.2f}mm   max {max(rmse_vals):.2f}mm")
        print(f"    fitness   median {np.median(fit_vals):.2f}     min {min(fit_vals):.2f}")

    # 부품/자세 분포
    from collections import Counter

    parts_counter = Counter(r.part_id for r in results if r.part_id)
    poses_counter = Counter(
        (r.part_id, r.stable_pose_id) for r in results
        if r.part_id and r.stable_pose_id
    )

    if parts_counter:
        print("\n  부품 분포:")
        for part, n in parts_counter.most_common():
            print(f"    {part}: {n}")

    if poses_counter:
        print("\n  자세 분포 (top 10):")
        for (part, sp), n in poses_counter.most_common(10):
            print(f"    {part} / pose_{sp}: {n}")

    # REVIEW 사유 분포
    if n_review + n_fail > 0:
        reason_counter = Counter(
            r.review_reason for r in results
            if r.auto_status in ("REVIEW", "FAIL") and r.review_reason
        )
        print("\n  REVIEW/FAIL 사유:")
        for reason, n in reason_counter.most_common():
            print(f"    {reason}: {n}")

    # 시간 통계
    if results:
        times = [r.pipeline_time_sec for r in results]
        print(f"\n  파이프라인 시간: median {np.median(times):.2f}s, max {max(times):.2f}s")


def save_run_summary(results: list[LabelResult], output_dir: Path) -> None:
    """전체 실행 summary.json 저장."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"run_summary_{time.strftime('%Y%m%dT%H%M%S')}.json"
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_total": len(results),
        "n_accept": sum(1 for r in results if r.auto_status == "ACCEPT"),
        "n_review": sum(1 for r in results if r.auto_status == "REVIEW"),
        "n_fail": sum(1 for r in results if r.auto_status == "FAIL"),
        "results": [r.to_dict() for r in results],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ Summary 저장: {summary_path}")


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="단독 부품 캡처 → L1~L4 → GT pose 자동 라벨링",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--capture-dir",
        type=Path,
        help="캡처 디렉토리 (frame_NNNN/depth.npy 패턴)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "bin_picking" / "models" / "dataset_v1",
        help="라벨링 결과 저장 디렉토리",
    )
    p.add_argument(
        "--stable-poses",
        type=Path,
        default=PROJECT_ROOT / "bin_picking" / "config" / "stable_poses.yaml",
        help="pose_enumerator 결과 yaml",
    )
    p.add_argument(
        "--part",
        type=str,
        default=None,
        help="후보 부품 지정 (다른 후보 차단). 미지정 시 모든 CAD에 매칭",
    )
    p.add_argument(
        "--camera",
        type=str,
        default="unknown",
        help="카메라 라벨 (blaze-112, d435, ace2 등)",
    )
    # 품질 게이트 옵션
    p.add_argument("--max-rmse-mm", type=float, default=1.5)
    p.add_argument("--min-fitness", type=float, default=0.3)
    p.add_argument("--min-pose-match", type=float, default=0.85)
    p.add_argument("--min-cluster-points", type=int, default=200)
    # 모드
    p.add_argument("--simulate", action="store_true", help="시뮬 모드 (코드 검증)")
    p.add_argument("--quiet", action="store_true")

    return p.parse_args()


def simulate_mode() -> int:
    """카메라/캡처 없이 시뮬 모드로 코드 검증."""
    print("=" * 60)
    print("Simulate 모드 — 코드 검증 (카메라 불필요)")
    print("=" * 60)

    # rotation_distance 검증
    R_eye = np.eye(3)
    R_90z = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    R_180z = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, 1]])

    d_eye = rotation_distance(R_eye, R_eye)
    d_90 = rotation_distance(R_eye, R_90z)
    d_180 = rotation_distance(R_eye, R_180z)
    print(f"\n[rotation_distance]")
    print(f"  eye - eye = {np.degrees(d_eye):.1f}° (기대 0°)")
    print(f"  eye - 90°z = {np.degrees(d_90):.1f}° (기대 90°)")
    print(f"  eye - 180°z = {np.degrees(d_180):.1f}° (기대 180°)")
    assert abs(d_eye) < 1e-6
    assert abs(np.degrees(d_90) - 90) < 0.1
    assert abs(np.degrees(d_180) - 180) < 0.1
    print("  ✅ rotation_distance 검증 PASS")

    # QualityGate 검증
    gate = QualityGate()
    cases = [
        ("정상", 0.8, 0.5, 1000, 0.95, "ACCEPT", None),
        ("RMSE 초과", 2.0, 0.5, 1000, 0.95, "REVIEW", "rmse_high"),
        ("fitness 낮음", 0.8, 0.2, 1000, 0.95, "REVIEW", "low_fitness"),
        ("cluster 부족", 0.8, 0.5, 100, 0.95, "REVIEW", "cluster_small"),
        ("pose 매칭 낮음", 0.8, 0.5, 1000, 0.5, "REVIEW", "pose_mismatch"),
    ]
    print("\n[QualityGate]")
    for name, rmse, fit, pts, sp_score, exp_status, exp_reason_prefix in cases:
        status, reason = _evaluate_gate(rmse, fit, pts, sp_score, gate)
        ok = (status == exp_status) and (
            exp_reason_prefix is None
            or (reason and reason.startswith(exp_reason_prefix))
        )
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}: status={status}, reason={reason}")
        assert ok, f"FAIL: {name}"

    # stable_pose 매핑 검증
    print("\n[find_closest_stable_pose]")
    fake_yaml = {
        "stable_poses": [
            {"id": "A", "transform_4x4": np.eye(4).tolist()},
            {"id": "B", "transform_4x4": np.diag([-1, -1, 1, 1]).tolist()},  # 180°z
        ]
    }
    T_test = np.eye(4)
    sid, score = find_closest_stable_pose(T_test, fake_yaml)
    print(f"  eye → {sid} (score {score:.3f}) — 기대 A, score 1.0")
    assert sid == "A" and score > 0.99

    T_test2 = np.diag([-1, -1, 1, 1]).astype(float)
    sid2, score2 = find_closest_stable_pose(T_test2, fake_yaml)
    print(f"  180°z → {sid2} (score {score2:.3f}) — 기대 B, score 1.0")
    assert sid2 == "B" and score2 > 0.99

    # 5° 회전 (A에 가까움)
    angle = np.radians(5)
    R = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    T_5deg = np.eye(4)
    T_5deg[:3, :3] = R
    sid3, score3 = find_closest_stable_pose(T_5deg, fake_yaml)
    print(f"  5°z → {sid3} (score {score3:.3f}) — 기대 A, score > 0.97")
    assert sid3 == "A" and score3 > 0.97

    # 대칭 그룹 검증 (P5 main_body A·B 180° 통합 케이스)
    print("\n[symmetry_groups (대칭 통합)]")
    sym_yaml = {
        "stable_poses": [
            {"id": "A", "transform_4x4": np.eye(4).tolist()},
            {"id": "B", "transform_4x4": np.diag([-1, -1, 1, 1]).tolist()},  # 180°z (A와 대칭)
            {"id": "C", "transform_4x4": [
                [1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]  # 90°x (별개)
            ]},
        ],
        "symmetry_groups": [["A", "B"]],
    }
    # B에 매칭돼야 정상이지만, 대칭 그룹 처리로 canonical A 반환
    T_b = np.diag([-1, -1, 1, 1]).astype(float)
    sid_b, score_b = find_closest_stable_pose(T_b, sym_yaml)
    print(f"  B 입력 + sym=[A,B] → {sid_b} (score {score_b:.3f}) — 기대 A (canonical), score 1.0")
    assert sid_b == "A" and score_b > 0.99

    # C는 그룹 밖이라 그대로
    T_c = np.array([
        [1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]
    ], dtype=float)
    sid_c, score_c = find_closest_stable_pose(T_c, sym_yaml)
    print(f"  C 입력 + sym=[A,B] → {sid_c} (score {score_c:.3f}) — 기대 C, score 1.0")
    assert sid_c == "C" and score_c > 0.99

    # canonicalize_pose_id 단위 테스트
    assert canonicalize_pose_id("A", [["A", "B"]]) == "A"
    assert canonicalize_pose_id("B", [["A", "B"]]) == "A"
    assert canonicalize_pose_id("C", [["A", "B"]]) == "C"
    assert canonicalize_pose_id("A", None) == "A"
    print("  ✅ canonicalize_pose_id 단위 테스트 PASS")

    print("\n✅ 모든 시뮬 검증 PASS")
    return 0


def main() -> int:
    args = parse_args()

    if args.simulate:
        return simulate_mode()

    if not args.capture_dir:
        print("[ERROR] --capture-dir 필요 (또는 --simulate)")
        return 1

    if not args.capture_dir.is_dir():
        print(f"[ERROR] 캡처 디렉토리 없음: {args.capture_dir}")
        return 1

    gate = QualityGate(
        max_rmse_mm=args.max_rmse_mm,
        min_fitness=args.min_fitness,
        min_pose_match_score=args.min_pose_match,
        min_cluster_points=args.min_cluster_points,
    )

    print("=" * 60)
    print("자동 라벨링 파이프라인")
    print(f"캡처: {args.capture_dir}")
    print(f"출력: {args.output}")
    print(f"부품 후보: {args.part or '전체 CAD'}")
    print(f"품질 게이트: rmse<{gate.max_rmse_mm}mm, fitness>{gate.min_fitness}, pose>{gate.min_pose_match_score}")
    print("=" * 60)

    t_total = time.time()
    try:
        results = auto_label_directory(
            capture_dir=args.capture_dir,
            output_dir=args.output,
            stable_poses_yaml=args.stable_poses,
            candidate_part=args.part,
            camera_label=args.camera,
            gate=gate,
            verbose=not args.quiet,
        )
    except Exception as e:
        print(f"\n[FATAL] {e}")
        traceback.print_exc()
        return 2

    if not results:
        print("[FAIL] 결과 0건")
        return 3

    print_summary(results)
    save_run_summary(results, args.output)

    elapsed = time.time() - t_total
    print(f"\n전체 시간: {elapsed:.1f}s ({elapsed / len(results):.2f}s/frame)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
