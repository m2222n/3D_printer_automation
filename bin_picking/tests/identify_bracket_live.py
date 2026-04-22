"""
브래킷 식별 라이브 스크립트 — D435 라이브 뷰 + SPACE 캡처 + CAD 매칭
====================================================================
카메라 앞 30~40cm에 실제 브래킷 부품을 놓고,
SPACE를 누르면 즉석에서 L2~L4 파이프라인을 돌려
어떤 브래킷인지 판별한다.

실행 (Mac, sudo 필요):
    sudo /Users/m2222n/Work/Orinu.ai/3D_printer_automation/3D_printer_automation/.venv/binpick/bin/python \
        bin_picking/tests/identify_bracket_live.py

조작:
    SPACE    — 현재 프레임으로 식별 실행
    s        — 현재 프레임 저장 (bin_picking/models/d435_frames/)
    ESC / q  — 종료
"""

from __future__ import annotations

import copy
import os
import sys
import time

import cv2
import numpy as np
import pyrealsense2 as rs

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import open3d as o3d

from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud
from bin_picking.src.acquisition.realsense_capture import (
    CapturedFrames, RSIntrinsics,
)
from bin_picking.src.preprocessing.cloud_filter import CloudFilter
from bin_picking.src.recognition.cad_library import CADLibrary
from bin_picking.src.recognition.pose_estimator import PoseEstimator
from bin_picking.src.recognition.size_filter import SizeFilter
from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter


FRAME_SAVE_DIR = os.path.join(PROJECT_ROOT, "bin_picking", "models", "d435_frames")

# 브래킷 계열 레퍼런스만 후보로 (이름에 bracket/brkt 포함)
BRACKET_KEYWORDS = ("bracket", "brkt")

# 촬영 거리 (권장: 손으로 들어올린 상태에서 30~40cm)
DEPTH_MIN = 0.15
DEPTH_MAX = 0.80


def is_bracket_name(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in BRACKET_KEYWORDS)


def compute_auto_roi(pcd: o3d.geometry.PointCloud, margin: float = 0.02):
    pts = np.asarray(pcd.points)
    if len(pts) == 0:
        return None
    roi_min = pts.min(axis=0) - margin
    roi_max = pts.max(axis=0) + margin
    # 바닥면 위 5mm부터
    roi_min[2] = max(roi_min[2], pts[:, 2].min() + 0.005)
    return {"min": roi_min, "max": roi_max}


def build_frames(depth: np.ndarray, color: np.ndarray,
                 intr: RSIntrinsics, depth_scale: float) -> CapturedFrames:
    return CapturedFrames(
        depth_map=depth.copy(),
        color_image=color.copy(),
        intrinsics=intr,
        depth_scale=depth_scale,
    )


def run_identification(
    frames: CapturedFrames,
    reference_cache: dict,
    bracket_refs: list,
    size_filter: SizeFilter,
    estimator: PoseEstimator,
) -> list:
    """L1 완료된 프레임으로 L2~L4 실행. 상위 매칭 리스트 반환."""
    t_total = time.time()

    # depth → pointcloud
    pcd = depth_to_pointcloud(
        depth_map=frames.depth_map,
        fx=frames.intrinsics.fx, fy=frames.intrinsics.fy,
        cx=frames.intrinsics.cx, cy=frames.intrinsics.cy,
        color_image=frames.color_image,
        depth_scale=frames.depth_scale,
        depth_min=DEPTH_MIN, depth_max=DEPTH_MAX,
    )
    print(f"  [L1] PointCloud: {len(pcd.points):,} pts")

    roi = compute_auto_roi(pcd)
    if roi is None:
        print("  [ERROR] 유효 포인트 없음")
        return []

    # L2: 전처리
    cloud_filter = CloudFilter(
        voxel_size=0.003,
        sor_nb_neighbors=20, sor_std_ratio=2.0,
        normal_radius=0.01, normal_max_nn=30,
        plane_distance=0.01, plane_iterations=2000,
        roi_min=roi["min"], roi_max=roi["max"],
    )
    filtered = cloud_filter.process(pcd)
    print(f"  [L2] 전처리 후: {len(filtered.points):,} pts")

    if len(filtered.points) < 100:
        print("  [WARN] 전처리 후 포인트 부족")
        return []

    # L3: DBSCAN
    segmenter = DBSCANSegmenter(
        eps=0.015, min_points=50,
        min_cluster_points=30, max_cluster_points=500000,
        min_size_mm=10.0, max_size_mm=500.0,
    )
    clusters = segmenter.segment(filtered)
    print(f"  [L3] 클러스터: {len(clusters)}개")

    if not clusters:
        print("  [WARN] 클러스터 없음")
        return []

    # 가장 큰 클러스터를 대상으로 (브래킷 1개 가정)
    target = max(clusters, key=lambda c: c.n_points)
    print(f"  [L3] 타겟 클러스터: {target.n_points} pts, "
          f"extent={target.extent_mm[0]:.0f}x{target.extent_mm[1]:.0f}x{target.extent_mm[2]:.0f}mm")

    # L4: CAD 매칭 (브래킷 후보만)
    size_candidates = size_filter.filter_candidates(target.pcd)
    # 브래킷 후보와 교집합
    if size_candidates:
        candidates = [n for n in size_candidates if is_bracket_name(n)]
    else:
        candidates = []
    if not candidates:
        # 크기 필터가 브래킷을 전부 걸러냈으면 전체 브래킷 후보로
        candidates = bracket_refs

    print(f"  [L4] 크기 필터 통과 브래킷 후보: {len(candidates)}/{len(bracket_refs)}종")

    match_results = estimator.match_against_references(
        target.pcd, reference_cache, candidate_names=candidates,
    )

    print(f"  [L4] 매칭 결과 (상위 5):")
    results = []
    for rank, mr in enumerate(match_results[:5]):
        decision = estimator.evaluate(mr)
        results.append({
            "name": mr["name"],
            "fitness": mr["fitness"],
            "rmse": mr["rmse"],
            "decision": decision,
            "rank": rank,
        })
        marker = "★" if rank == 0 else " "
        print(f"    {marker} {rank+1}. {mr['name']:>30}  "
              f"fitness={mr['fitness']:.4f}  "
              f"RMSE={mr['rmse']*1000:6.2f}mm  {decision}")

    print(f"  총 시간: {time.time() - t_total:.2f}s")
    return results


def overlay_text(img: np.ndarray, lines: list[str], y0: int = 30) -> None:
    for i, line in enumerate(lines):
        y = y0 + i * 28
        cv2.putText(img, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0), 2, cv2.LINE_AA)


def main():
    print("=" * 70)
    print("  브래킷 식별 라이브 — D435 + CAD 매칭")
    print("=" * 70)

    # 레퍼런스 로드
    print("\n[1/2] CAD 레퍼런스 로드...")
    cad_library = CADLibrary()
    reference_cache = cad_library.load_all()
    if not reference_cache:
        print("  [ERROR] 레퍼런스 캐시 없음. cad_library.py --build 먼저 실행")
        sys.exit(1)

    bracket_refs = [name for name in reference_cache.keys() if is_bracket_name(name)]
    print(f"  전체 {len(reference_cache)}종 중 브래킷 {len(bracket_refs)}종:")
    for name in bracket_refs:
        print(f"    - {name}")
    if not bracket_refs:
        print("  [ERROR] 브래킷 레퍼런스를 찾지 못했습니다.")
        sys.exit(1)

    size_filter = SizeFilter(tolerance=0.5)
    for name, data in reference_cache.items():
        size_filter.add_reference(name, data["bbox_features"])
    estimator = PoseEstimator(voxel_size=0.002)

    # D435 라이브 시작
    print("\n[2/2] D435 라이브 시작...")
    pipe = rs.pipeline()
    cfg = rs.config()
    cfg.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    cfg.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    align = rs.align(rs.stream.color)
    profile = pipe.start(cfg)

    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale_m = depth_sensor.get_depth_scale()   # m/unit, 보통 0.001
    # our depth_to_pointcloud uses mm-unit depth with depth_scale=1000
    # RealSense에서 depth_frame.get_data()는 uint16 (unit=m 변환 scale)
    # 편의상 depth_scale_m을 "unit → m"로 쓰고, depth_to_pointcloud에는
    # depth * depth_scale_m * 1000 → mm 변환 후 전달하는 방식도 있지만
    # 기존 realsense_capture.py 관례에 맞춰 depth_scale=1/depth_scale_m를 전달
    depth_scale = 1.0 / depth_scale_m   # 보통 1000.0

    color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intr_rs = color_stream.get_intrinsics()
    intr = RSIntrinsics.from_rs_intrinsics(intr_rs)
    print(f"  intrinsics: fx={intr.fx:.1f}, fy={intr.fy:.1f}, "
          f"cx={intr.cx:.1f}, cy={intr.cy:.1f}, depth_scale={depth_scale:.1f}")

    # 자동 노출 안정화
    for _ in range(30):
        pipe.wait_for_frames()

    last_result: list | None = None
    result_show_until = 0.0

    print("\n조작: SPACE=식별, s=프레임 저장, ESC/q=종료\n")
    try:
        while True:
            frames_rs = pipe.wait_for_frames()
            aligned = align.process(frames_rs)

            depth_frame = aligned.get_depth_frame()
            color_frame = aligned.get_color_frame()
            if not depth_frame or not color_frame:
                continue

            depth = np.asanyarray(depth_frame.get_data())  # uint16, unit=depth_scale_m
            color = np.asanyarray(color_frame.get_data())  # BGR

            # depth 컬러맵
            depth_mm = depth.astype(np.float32) * depth_scale_m * 1000.0   # 실제 mm
            # 화면용: 0~1500mm → JET
            depth_vis = np.clip(depth_mm / 1500.0 * 255.0, 0, 255).astype(np.uint8)
            depth_cm = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

            # 중앙 depth 샘플 (대상 거리 확인)
            h, w = depth.shape
            center_d = depth_mm[h // 2, w // 2]
            center_txt = f"center: {center_d:.0f}mm" if center_d > 0 else "center: -"

            # 가이드 박스 (중앙 200x200)
            cx, cy = w // 2, h // 2
            cv2.rectangle(color, (cx - 100, cy - 100), (cx + 100, cy + 100),
                          (0, 255, 255), 1)
            cv2.rectangle(depth_cm, (cx - 100, cy - 100), (cx + 100, cy + 100),
                          (0, 255, 255), 1)

            lines = [
                "SPACE=identify  s=save  ESC=quit",
                center_txt,
                f"target range: {int(DEPTH_MIN*1000)}-{int(DEPTH_MAX*1000)}mm",
            ]

            # 최근 결과 5초간 표시
            if last_result and time.time() < result_show_until:
                top = last_result[0]
                tag = "ACCEPT" if top["decision"] == "ACCEPT" else top["decision"]
                lines.append("")
                lines.append(f"[{tag}] {top['name']}")
                lines.append(f"fitness={top['fitness']:.3f}  "
                             f"RMSE={top['rmse']*1000:.1f}mm")

            overlay_text(color, lines)
            combined = np.hstack([color, depth_cm])
            cv2.imshow("Bracket ID (SPACE=identify, ESC=quit)", combined)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

            if key == ord("s"):
                # 현재 프레임 저장
                cf = build_frames(depth, color, intr, depth_scale)
                cf.save(FRAME_SAVE_DIR)
                print(f"  [저장] {FRAME_SAVE_DIR}")

            if key == 32:  # SPACE
                print("\n" + "=" * 70)
                print("  식별 실행")
                print("=" * 70)
                cf = build_frames(depth, color, intr, depth_scale)
                last_result = run_identification(
                    cf, reference_cache, bracket_refs, size_filter, estimator,
                )
                result_show_until = time.time() + 5.0

    finally:
        pipe.stop()
        cv2.destroyAllWindows()
        print("\n종료")


if __name__ == "__main__":
    main()
