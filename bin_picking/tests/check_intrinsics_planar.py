"""
Intrinsics 평면 sanity check — A4 평면 캡처 → RANSAC 평면 fit 잔차 통계
========================================================================

5/15 사무실 도착 시 본 캡처 들어가기 전 30분 검증용.

현재 BLAZE intrinsics 는 추정값 (fx=553, fy=188, FOV 75°×104° 기반 계산).
정식 ChArUco 캘리브 안 됐기에 ±2~5% 비뚤어졌을 가능성.

이게 비뚤어지면:
- depth → pointcloud 변환된 점군이 휘어보임
- L4 ICP 가 휜 점군에 CAD 맞추므로 RMSE 체계적 발생
- ACCEPT 비율이 본질적으로 낮아짐

검증 방법: 평평한 A4 종이 한 장을 카메라 앞 60~80cm 에 배치 → 캡처 →
pointcloud 변환 → RANSAC 평면 fit → 잔차 통계 보고

판정 기준 (5/13 결정):
- RMS < 2.0mm: ✅ intrinsics 신뢰 OK, 본 캡처 진행
- 2.0 ~ 5.0mm: ⚠️ 주의 — auto_label.py 게이트 완화 (`--max-rmse-mm 3.0`) 검토
- > 5.0mm: ❌ 캘리브 필요 — ChArUco 보드로 정식 캘리브 (별도 1~2시간)

사용:
    # 1. 캡처 먼저 (test_basler_live.py)
    python bin_picking/tests/test_basler_live.py --live --save \\
        --output /tmp/planar_check/frame_0001

    # 2. sanity check
    python bin_picking/tests/check_intrinsics_planar.py \\
        --frame /tmp/planar_check/frame_0001

또는 한 번에:
    python bin_picking/tests/check_intrinsics_planar.py --capture-and-check

권장 배치:
- A4 흰 종이 한 장 (책상 위 평평하게)
- 카메라 60~80cm, 광축이 종이 중심 향하도록
- 종이가 시야 안에 다 들어가는지 라이브 뷰어로 사전 확인
- 종이 외 다른 물체 없는 깨끗한 시야 (배경 노이즈 최소화)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# 판정 임계
# ============================================================
RMS_OK_THRESHOLD_MM = 2.0       # 이하면 intrinsics 신뢰 OK
RMS_WARN_THRESHOLD_MM = 5.0     # 이하면 게이트 완화로 진행 가능, 초과면 캘리브 필요
MIN_INLIER_RATIO = 0.7          # RANSAC inlier 비율 최소 (평면이 시야 70%+ 차지)


# ============================================================
# RANSAC 평면 fit (Open3D)
# ============================================================
def fit_plane_ransac(
    pcd, distance_threshold: float = 0.005, num_iterations: int = 1000
) -> tuple[np.ndarray, list, float]:
    """RANSAC 으로 점군에 평면 fit.

    Returns:
        (plane_coeffs, inlier_indices, inlier_ratio)
        plane_coeffs: [a, b, c, d] (ax + by + cz + d = 0)
    """
    plane_model, inliers = pcd.segment_plane(
        distance_threshold=distance_threshold,
        ransac_n=3,
        num_iterations=num_iterations,
    )
    inlier_ratio = len(inliers) / len(pcd.points) if len(pcd.points) > 0 else 0.0
    return np.asarray(plane_model), inliers, inlier_ratio


def compute_residuals_mm(pcd, plane_coeffs: np.ndarray) -> np.ndarray:
    """점군 각 점의 평면까지 수직 거리 (mm)."""
    points = np.asarray(pcd.points)  # (N, 3) in meters
    a, b, c, d = plane_coeffs
    # 점 (x, y, z) 의 평면까지 거리 = |ax + by + cz + d| / sqrt(a² + b² + c²)
    norm = np.sqrt(a * a + b * b + c * c)
    if norm < 1e-9:
        return np.array([])
    distances_m = np.abs(points @ np.array([a, b, c]) + d) / norm
    return distances_m * 1000.0  # m → mm


# ============================================================
# 프레임 → 점군 → 평면 fit
# ============================================================
def check_frame(frame_dir: Path, verbose: bool = True) -> dict:
    """단일 프레임 평면 sanity check.

    Returns:
        dict with keys: status, rms_mm, max_mm, p95_mm, inlier_ratio,
                       n_points_total, n_points_inlier, intrinsics_version, message
    """
    import open3d as o3d  # noqa: F401  (lazy import)

    from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

    depth_path = frame_dir / "depth.npy"
    meta_path = frame_dir / "meta.json"

    if not depth_path.exists():
        return {"status": "FAIL", "message": f"depth.npy 없음: {depth_path}"}
    if not meta_path.exists():
        return {"status": "FAIL", "message": f"meta.json 없음: {meta_path}"}

    depth = np.load(depth_path)
    meta = json.loads(meta_path.read_text())

    intr_version = meta.get("intrinsics_version", "unknown")
    fx = float(meta["fx"])
    fy = float(meta["fy"])
    cx = float(meta["cx"])
    cy = float(meta["cy"])
    depth_scale = float(meta.get("depth_scale", 1000.0))

    if verbose:
        print(f"\n[프레임] {frame_dir}")
        print(f"  depth shape: {depth.shape}, dtype: {depth.dtype}")
        print(f"  intrinsics: fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f}")
        print(f"  intrinsics_version: {intr_version}")
        print(f"  depth_scale: {depth_scale}")

    # depth → pointcloud
    pcd = depth_to_pointcloud(
        depth_map=depth,
        fx=fx, fy=fy, cx=cx, cy=cy,
        depth_scale=depth_scale,
        depth_min=0.3,
        depth_max=2.0,  # A4 평면은 60~80cm 거리 가정
    )

    n_pts = len(pcd.points)
    if verbose:
        print(f"  pointcloud: {n_pts} points")

    if n_pts < 1000:
        return {
            "status": "FAIL",
            "message": f"점군 부족 ({n_pts} < 1000). A4 종이 시야 안 / 거리 확인",
            "n_points_total": n_pts,
            "intrinsics_version": intr_version,
        }

    # RANSAC 평면 fit (5mm 이하 잔차 = inlier)
    plane_coeffs, inlier_idx, inlier_ratio = fit_plane_ransac(
        pcd, distance_threshold=0.005
    )
    if verbose:
        print(f"  plane: {plane_coeffs[0]:.3f}x + {plane_coeffs[1]:.3f}y + {plane_coeffs[2]:.3f}z + {plane_coeffs[3]:.3f} = 0")
        print(f"  inlier ratio: {inlier_ratio:.2%} ({len(inlier_idx)} / {n_pts})")

    if inlier_ratio < MIN_INLIER_RATIO:
        return {
            "status": "FAIL",
            "message": (
                f"inlier 비율 부족 ({inlier_ratio:.0%} < {MIN_INLIER_RATIO:.0%}). "
                f"평면이 시야의 대부분을 차지해야 함. A4 종이 배치 / 배경 점 제거 확인"
            ),
            "inlier_ratio": inlier_ratio,
            "n_points_total": n_pts,
            "intrinsics_version": intr_version,
        }

    # inlier 점들에 대해 잔차 통계
    inlier_pcd = pcd.select_by_index(inlier_idx)
    residuals_mm = compute_residuals_mm(inlier_pcd, plane_coeffs)

    rms_mm = float(np.sqrt(np.mean(residuals_mm ** 2)))
    max_mm = float(np.max(residuals_mm))
    p95_mm = float(np.percentile(residuals_mm, 95))
    mean_mm = float(np.mean(residuals_mm))

    # 판정
    if rms_mm < RMS_OK_THRESHOLD_MM:
        status = "PASS"
        message = (
            f"✅ intrinsics 신뢰 OK (RMS {rms_mm:.2f}mm < {RMS_OK_THRESHOLD_MM}mm). "
            f"본 캡처 진행 가능."
        )
    elif rms_mm < RMS_WARN_THRESHOLD_MM:
        status = "WARN"
        message = (
            f"⚠️ intrinsics 추정 오차 의심 (RMS {rms_mm:.2f}mm, 임계 {RMS_OK_THRESHOLD_MM}~{RMS_WARN_THRESHOLD_MM}mm). "
            f"auto_label.py 게이트 완화 (`--max-rmse-mm 3.0`) 또는 ChArUco 정식 캘리브 검토. "
            f"진행은 가능하나 라벨 RMSE 분포 모니터링 필수."
        )
    else:
        status = "FAIL"
        message = (
            f"❌ intrinsics 캘리브 필요 (RMS {rms_mm:.2f}mm > {RMS_WARN_THRESHOLD_MM}mm). "
            f"점군이 평면을 평면으로 인식 못 함 = depth 좌표 비뚤어짐. "
            f"ChArUco 보드 정식 캘리브 진행 후 재시도. 본 캡처 보류 권장."
        )

    return {
        "status": status,
        "rms_mm": rms_mm,
        "mean_mm": mean_mm,
        "max_mm": max_mm,
        "p95_mm": p95_mm,
        "inlier_ratio": inlier_ratio,
        "n_points_total": n_pts,
        "n_points_inlier": len(inlier_idx),
        "intrinsics_version": intr_version,
        "plane_coeffs": plane_coeffs.tolist(),
        "message": message,
    }


# ============================================================
# 캡처 + 체크 통합 모드 (5/15 사무실 빠른 검증용)
# ============================================================
def capture_and_check(output_dir: Path, no_ace2: bool = True) -> dict:
    """test_basler_live.py 캡처 후 즉시 체크.

    Returns: check_frame 결과 dict.
    """
    import subprocess

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bin_picking" / "tests" / "test_basler_live.py"),
        "--live", "--save",
        "--output", str(output_dir),
    ]
    if no_ace2:
        cmd.append("--no-ace2")

    print(f"\n[capture] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {
            "status": "FAIL",
            "message": f"캡처 실패: {result.stderr[-500:]}",
        }

    return check_frame(output_dir, verbose=True)


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="A4 평면 캡처 → RANSAC 평면 fit → intrinsics sanity check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--frame",
        type=Path,
        help="이미 캡처된 프레임 디렉토리 (depth.npy + meta.json)",
    )
    p.add_argument(
        "--capture-and-check",
        action="store_true",
        help="test_basler_live.py 로 캡처 후 즉시 체크",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "bin_picking" / "models" / "captures" / "planar_check",
        help="--capture-and-check 모드 시 저장 위치",
    )
    p.add_argument("--ace2", action="store_true", help="ACE2 RGB 도 포함 (기본: --no-ace2)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.capture_and_check:
        result = capture_and_check(args.output, no_ace2=not args.ace2)
    elif args.frame:
        if not args.frame.is_dir():
            print(f"[ERROR] 프레임 디렉토리 없음: {args.frame}")
            return 1
        result = check_frame(args.frame, verbose=True)
    else:
        print("[ERROR] --frame <dir> 또는 --capture-and-check 필요")
        return 1

    print("\n" + "=" * 70)
    print("Intrinsics 평면 sanity check 결과")
    print("=" * 70)

    if result["status"] in ("PASS", "WARN", "FAIL"):
        rms = result.get("rms_mm")
        if rms is not None:
            print(f"\n  RMS:       {rms:.2f} mm")
            print(f"  Mean:      {result['mean_mm']:.2f} mm")
            print(f"  P95:       {result['p95_mm']:.2f} mm")
            print(f"  Max:       {result['max_mm']:.2f} mm")
            print(f"  Inlier:    {result['inlier_ratio']:.1%} ({result['n_points_inlier']} / {result['n_points_total']})")
            print(f"  intrinsics_version: {result['intrinsics_version']}")
        print(f"\n  판정:     {result['status']}")
        print(f"  메시지:   {result['message']}")

    # 결과를 프레임 폴더 또는 출력 폴더에 json 저장
    out_root = args.frame if args.frame else args.output
    if out_root and out_root.exists():
        report_path = out_root / "planar_check_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ 리포트 저장: {report_path}")

    # exit code: PASS=0, WARN=0 (진행 가능), FAIL=1
    return 0 if result["status"] in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
