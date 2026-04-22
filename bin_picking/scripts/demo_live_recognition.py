#!/usr/bin/env python
"""
대표님 시연용 라이브 인식 데모
===============================

Basler Blaze-112 (ToF) + ace2 (RGB 5MP) 듀얼 카메라의 입력과
L1~L5 파이프라인 인식 결과를 2×2 그리드로 실시간 시각화.

3가지 입력 모드 지원:
    --basler       : Basler 2대 라이브 (본 데모, 4/23 이후)
    --realsense    : D435 라이브 (카메라 없는 환경의 대체)
    --load DIR     : 저장된 프레임 로드 (오프라인 리허설)
    --synthetic    : 합성 씬 생성 (완전 단독 검증)

키 바인딩:
    c / SPACE      : 현재 프레임 캡처 → 파이프라인 실행 → 결과 오버레이
    s              : 현재 화면 PNG 저장 (/tmp/demo_<timestamp>.png)
    r              : 재시작 (결과 리셋, 라이브 모드로 복귀)
    q / ESC        : 종료

사용법:
    # Basler 본 데모 (카메라 입고 후)
    sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --basler

    # D435로 리허설
    sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --realsense

    # 저장된 프레임으로 오프라인 데모
    .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --load ~/Desktop/d435_bracket_retry2

    # 합성 씬 (완전 오프라인)
    .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --synthetic

실행 환경: source .venv/binpick/bin/activate
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

# ============================================================
# 의존성 (지연 import로 mode별 분기)
# ============================================================
try:
    import open3d as o3d
except ImportError:
    o3d = None

from bin_picking.src.visualization.demo_ui import (
    DemoRenderer,
    PartInfo,
    PipelineStats,
    parts_from_pipeline_result,
    stats_from_pipeline_result,
)


# ============================================================
# 프레임 소스 추상화
# ============================================================
@dataclass
class FrameBundle:
    """모든 소스에서 공통으로 반환하는 프레임 묶음."""
    rgb: Optional[np.ndarray]       # (H, W, 3) BGR 또는 None
    depth: Optional[np.ndarray]     # (H, W) uint16 mm 또는 None
    fx: float
    fy: float
    cx: float
    cy: float
    depth_scale: float = 1000.0     # depth 값 → m 변환


class FrameSource:
    """프레임 소스 공통 인터페이스."""

    def start(self) -> None:
        ...

    def read(self) -> FrameBundle:
        raise NotImplementedError

    def stop(self) -> None:
        ...


class RealSenseSource(FrameSource):
    """Intel RealSense D435 라이브."""

    def __init__(self, depth_min: float = 0.10, depth_max: float = 1.5):
        from bin_picking.src.acquisition.realsense_capture import RealSenseCapture
        self.cam = RealSenseCapture(
            width=640, height=480, fps=30,
            depth_min=depth_min, depth_max=depth_max,
        )

    def start(self) -> None:
        self.cam.start()
        # 자동 노출 안정화
        for _ in range(30):
            self.cam.capture()

    def read(self) -> FrameBundle:
        frames = self.cam.capture()
        return FrameBundle(
            rgb=frames.color_image,
            depth=frames.depth_map,
            fx=frames.intrinsics.fx,
            fy=frames.intrinsics.fy,
            cx=frames.intrinsics.cx,
            cy=frames.intrinsics.cy,
            depth_scale=frames.depth_scale,
        )

    def stop(self) -> None:
        self.cam.stop()


class BaslerSource(FrameSource):
    """Basler Blaze-112 + ace2 듀얼 라이브."""

    def __init__(self, depth_min: float = 0.3, depth_max: float = 1.5):
        from bin_picking.src.acquisition.basler_capture import BaslerCapture
        self.cam = BaslerCapture(depth_min=depth_min, depth_max=depth_max)

    def start(self) -> None:
        result = self.cam.start()
        print(f"  [Basler] Blaze-112: {'OK' if result['blaze'] else 'FAIL'}")
        print(f"  [Basler] ace2:      {'OK' if result['ace2'] else 'N/A'}")

    def read(self) -> FrameBundle:
        frames = self.cam.capture()
        return FrameBundle(
            rgb=frames.color_image,
            depth=frames.depth_map,
            fx=frames.depth_intrinsics.fx,
            fy=frames.depth_intrinsics.fy,
            cx=frames.depth_intrinsics.cx,
            cy=frames.depth_intrinsics.cy,
            depth_scale=frames.depth_scale,
        )

    def stop(self) -> None:
        self.cam.stop()


class LoadedSource(FrameSource):
    """저장된 프레임을 반복 재생 (리허설용)."""

    def __init__(self, frame_dir: str):
        import json
        d = Path(frame_dir)
        self.depth = np.load(d / "depth.npy")

        color_path = d / "color.npy"
        self.color = np.load(color_path) if color_path.exists() else None

        meta = json.loads((d / "meta.json").read_text())
        self.fx = float(meta["fx"])
        self.fy = float(meta["fy"])
        self.cx = float(meta["cx"])
        self.cy = float(meta["cy"])
        self.depth_scale = float(meta.get("depth_scale", 1000.0))

    def start(self) -> None:
        pass

    def read(self) -> FrameBundle:
        return FrameBundle(
            rgb=self.color,
            depth=self.depth,
            fx=self.fx, fy=self.fy, cx=self.cx, cy=self.cy,
            depth_scale=self.depth_scale,
        )

    def stop(self) -> None:
        pass


class SyntheticSource(FrameSource):
    """합성 depth + color (완전 단독 검증)."""

    def __init__(self):
        self.counter = 0

    def start(self) -> None:
        pass

    def read(self) -> FrameBundle:
        # 간단한 합성 씬: 바닥 + 박스 3개 + 시간 따라 약간 흔들림
        H, W = 480, 640
        depth = np.full((H, W), 800, dtype=np.uint16)  # 바닥 800mm

        # 박스 3개 (다른 높이)
        jitter = (self.counter % 30) - 15
        for (py, px, ph, pw, d) in [
            (150 + jitter, 150, 80, 100, 600),
            (250 - jitter // 2, 300, 100, 120, 650),
            (100, 450 + jitter, 60, 80, 550),
        ]:
            depth[py:py+ph, px:px+pw] = d

        # 노이즈
        depth = depth + np.random.normal(0, 3, (H, W)).astype(np.int16)
        depth = np.clip(depth, 0, 65535).astype(np.uint16)

        # 색상
        color = np.full((H, W, 3), (200, 200, 200), dtype=np.uint8)
        for i, (py, px, ph, pw, d) in enumerate([
            (150 + jitter, 150, 80, 100, 600),
            (250 - jitter // 2, 300, 100, 120, 650),
            (100, 450 + jitter, 60, 80, 550),
        ]):
            colors = [(50, 50, 200), (50, 200, 50), (200, 50, 50)]
            color[py:py+ph, px:px+pw] = colors[i]

        self.counter += 1

        return FrameBundle(
            rgb=color,
            depth=depth,
            fx=460.0, fy=460.0, cx=320.0, cy=240.0,
            depth_scale=1000.0,
        )

    def stop(self) -> None:
        pass


# ============================================================
# 파이프라인 연결 (지연 로드 — pipeline 객체 재사용)
# ============================================================
class PipelineRunner:
    """BinPickingPipeline을 1회 초기화하고 여러 번 실행."""

    def __init__(self, resin: Optional[str] = None):
        from bin_picking.src.main_pipeline import BinPickingPipeline
        print("  [파이프라인] 레퍼런스 캐시 로딩...")
        t0 = time.time()
        if resin:
            self.pipeline = BinPickingPipeline.from_resin(resin)
        else:
            self.pipeline = BinPickingPipeline()
        print(f"  [파이프라인] 로드 완료 ({(time.time()-t0)*1000:.0f}ms)")

    def run(self, fb: FrameBundle) -> Optional[Dict[str, Any]]:
        """FrameBundle → L1(변환) → L2~L5 → 결과."""
        from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

        if fb.depth is None:
            return None

        # L1: depth → PointCloud
        pcd = depth_to_pointcloud(
            depth_map=fb.depth,
            fx=fb.fx, fy=fb.fy, cx=fb.cx, cy=fb.cy,
            color_image=fb.rgb,
            depth_scale=fb.depth_scale,
        )
        if len(pcd.points) < 100:
            return None

        # L2~L5
        result = self.pipeline.run(pcd, top_k=5)
        result["input_pcd_len"] = len(pcd.points)
        result["input_pcd"] = pcd  # 오버레이 렌더링용
        return result


# ============================================================
# 오버레이 이미지 생성 (depth 위에 매칭된 CAD 영역 하이라이트)
# ============================================================
def render_overlay_image(
    fb: FrameBundle,
    result: Optional[Dict[str, Any]],
    width: int = 640,
    height: int = 480,
) -> Optional[np.ndarray]:
    """depth 이미지 위에 인식 결과 오버레이.

    간단한 방식: depth 컬러맵 + 클러스터 bounding box를 2D로 투영하여 박스 그리기.
    각 클러스터의 bounding box 중심을 카메라 intrinsics로 픽셀 좌표로 투영.
    """
    if fb.depth is None:
        return None

    # depth 컬러맵
    depth = fb.depth
    valid = depth > 0
    if not valid.any():
        return None

    d_valid = depth[valid]
    d_min, d_max = d_valid.min(), d_valid.max()
    norm = np.zeros_like(depth, dtype=np.uint8)
    if d_max > d_min:
        norm[valid] = (
            ((d_valid.astype(np.float32) - d_min) / (d_max - d_min)) * 255
        ).astype(np.uint8)
    img = cv2.applyColorMap(norm, cv2.COLORMAP_VIRIDIS)
    img[~valid] = [0, 0, 0]

    # depth 해상도를 target에 맞추기
    h, w = img.shape[:2]
    if (w, h) != (width, height):
        img = cv2.resize(img, (width, height))
        scale_x = width / w
        scale_y = height / h
    else:
        scale_x = scale_y = 1.0

    if result is None:
        return img

    # 클러스터별 bounding box 투영
    clusters = result.get("clusters", [])
    parts = [p for p in result.get("parts", []) if p.get("rank", 0) == 0]

    for i, cluster in enumerate(clusters):
        if i >= len(parts):
            break

        part = parts[i]
        decision = part.get("decision", "REJECT")

        # 판정별 색상 (BGR)
        if decision == "ACCEPT":
            color = (0, 200, 0)
        elif decision == "WARN":
            color = (0, 200, 220)
        else:
            color = (0, 0, 220)

        # 클러스터 중심을 2D 픽셀로 투영
        try:
            pts = np.asarray(cluster.pcd.points)
            if len(pts) == 0:
                continue

            # 카메라 intrinsics로 투영 (depth_scale 이미 m 단위 기준)
            x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
            valid_z = z > 0
            if not valid_z.any():
                continue

            u = (x[valid_z] * fb.fx / z[valid_z] + fb.cx) * scale_x
            v = (y[valid_z] * fb.fy / z[valid_z] + fb.cy) * scale_y

            u_min, u_max = int(u.min()), int(u.max())
            v_min, v_max = int(v.min()), int(v.max())

            # bounding box
            cv2.rectangle(img, (u_min, v_min), (u_max, v_max), color, 2)

            # 라벨 (부품 이름 축약)
            name = part["name"][:20]
            fit = part["fitness"]
            label = f"{name} ({fit:.2f})"
            cv2.putText(
                img, label, (u_min, max(v_min - 8, 18)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )
        except Exception as e:
            # 투영 실패해도 데모 계속
            print(f"  [overlay] 클러스터 {i} 투영 실패: {e}")
            continue

    return img


# ============================================================
# 메인 루프
# ============================================================
def run_demo(args):
    # 1. 프레임 소스 생성
    print(f"\n{'='*60}")
    print(f"  라이브 인식 데모 - 모드: {args.mode.upper()}")
    print(f"{'='*60}\n")

    if args.mode == "basler":
        source = BaslerSource()
    elif args.mode == "realsense":
        source = RealSenseSource()
    elif args.mode == "load":
        source = LoadedSource(args.load)
    elif args.mode == "synthetic":
        source = SyntheticSource()
    else:
        raise ValueError(f"Unknown mode: {args.mode}")

    # 2. 파이프라인 초기화
    runner = PipelineRunner(resin=args.resin)

    # 3. UI 렌더러
    renderer = DemoRenderer(cell_w=args.cell_w, cell_h=args.cell_h)
    window_name = "Bin-Picking Live Recognition (Orinu)"

    # 디스플레이 없는 환경 (test-render) — 1회 렌더링 후 종료
    if args.test_render:
        source.start()
        fb = source.read()
        print("  [test-render] 파이프라인 실행 중...")
        result = runner.run(fb)
        if result is None:
            print("  [test-render] 파이프라인 실패 — 포인트 부족")
            parts = []
            stats = None
            overlay = None
        else:
            parts = parts_from_pipeline_result(result)
            stats = stats_from_pipeline_result(
                result, input_pcd_len=result.get("input_pcd_len", 0),
            )
            overlay = render_overlay_image(
                fb, result,
                width=renderer.cell_w, height=renderer.cell_h,
            )
            print(f"  [test-render] {stats.n_clusters} 클러스터, "
                  f"ACCEPT {stats.n_accepted} / WARN {stats.n_warn} / REJECT {stats.n_rejected}")

        canvas = renderer.render(
            rgb_image=fb.rgb,
            depth_map=fb.depth,
            overlay_image=overlay,
            parts=parts,
            stats=stats,
            status_text=f"TEST RENDER ({args.mode})",
        )

        cv2.imwrite(args.test_render, canvas)
        print(f"  [test-render] 저장: {args.test_render}")
        source.stop()
        return

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, renderer.canvas_w, renderer.canvas_h)

    # 4. 카메라 시작
    try:
        source.start()
    except Exception as e:
        print(f"  [ERROR] 소스 시작 실패: {e}")
        return

    # 5. 상태
    last_result = None
    last_overlay = None
    last_parts = []
    last_stats = None
    status_text = "LIVE [c]=capture  [s]=save  [q]=quit"

    print("  [시작] 키: c=캡처, s=PNG저장, r=리셋, q=종료\n")

    try:
        while True:
            loop_t0 = time.time()

            # 프레임 읽기
            try:
                fb = source.read()
            except Exception as e:
                print(f"  [WARN] 프레임 읽기 실패: {e}")
                time.sleep(0.1)
                continue

            # 캔버스 렌더링
            canvas = renderer.render(
                rgb_image=fb.rgb,
                depth_map=fb.depth,
                overlay_image=last_overlay,
                parts=last_parts,
                stats=last_stats,
                status_text=status_text,
            )

            cv2.imshow(window_name, canvas)

            # 키 입력 (load/synthetic은 30fps 제한)
            wait_ms = 1 if args.mode in ("basler", "realsense") else 33
            key = cv2.waitKey(wait_ms) & 0xFF

            if key == ord('q') or key == 27:  # q 또는 ESC
                print("  [종료] 사용자 요청")
                break

            elif key == ord('c') or key == ord(' '):  # c 또는 SPACE
                print("  [캡처] 파이프라인 실행 중...")
                t0 = time.time()
                last_result = runner.run(fb)
                elapsed = time.time() - t0

                if last_result is None:
                    print(f"  [캡처] 실패: 유효 포인트 없음")
                    status_text = "CAPTURE FAILED - retry with [c]"
                else:
                    last_parts = parts_from_pipeline_result(last_result)
                    last_stats = stats_from_pipeline_result(
                        last_result,
                        input_pcd_len=last_result.get("input_pcd_len", 0),
                    )
                    last_overlay = render_overlay_image(
                        fb, last_result,
                        width=renderer.cell_w, height=renderer.cell_h,
                    )
                    n_acc = last_stats.n_accepted
                    n_warn = last_stats.n_warn
                    n_rej = last_stats.n_rejected
                    print(
                        f"  [캡처] 완료 ({elapsed*1000:.0f}ms): "
                        f"ACCEPT {n_acc} / WARN {n_warn} / REJECT {n_rej}"
                    )
                    status_text = (
                        f"CAPTURED - {last_stats.n_clusters} clusters, "
                        f"ACCEPT {n_acc} / WARN {n_warn} / REJECT {n_rej}"
                    )

            elif key == ord('s'):  # s: PNG 저장
                out_dir = Path("/tmp")
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                out_path = out_dir / f"demo_{timestamp}.png"
                cv2.imwrite(str(out_path), canvas)
                print(f"  [저장] {out_path}")
                status_text = f"SAVED: {out_path.name}"

            elif key == ord('r'):  # r: 리셋
                last_result = None
                last_overlay = None
                last_parts = []
                last_stats = None
                status_text = "RESET - LIVE mode"
                print("  [리셋] 결과 초기화")

    except KeyboardInterrupt:
        print("\n  [종료] Ctrl+C")

    finally:
        source.stop()
        cv2.destroyAllWindows()
        print("\n  [완료] 데모 종료")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="대표님 시연용 라이브 인식 데모",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--basler", action="store_true", help="Basler 라이브 (Blaze-112 + ace2)")
    group.add_argument("--realsense", action="store_true", help="RealSense D435 라이브")
    group.add_argument("--load", type=str, help="저장된 프레임 디렉토리")
    group.add_argument("--synthetic", action="store_true", help="합성 씬")

    parser.add_argument(
        "--resin", type=str, default=None,
        choices=["grey", "white", "clear", "flexible"],
        help="레진 프리셋 (L2+L4 파라미터 일관 적용)",
    )
    parser.add_argument("--cell-w", type=int, default=640, help="셀 가로 (기본 640)")
    parser.add_argument("--cell-h", type=int, default=480, help="셀 세로 (기본 480)")
    parser.add_argument(
        "--test-render", type=str, default=None,
        help="디스플레이 없이 1회 렌더링 후 PNG만 저장 (CI/서버 검증용)",
    )

    args = parser.parse_args()

    # 모드 결정
    if args.basler:
        args.mode = "basler"
    elif args.realsense:
        args.mode = "realsense"
    elif args.load:
        args.mode = "load"
    elif args.synthetic:
        args.mode = "synthetic"

    run_demo(args)


if __name__ == "__main__":
    main()
