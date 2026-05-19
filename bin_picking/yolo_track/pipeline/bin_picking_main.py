"""
YOLO 트랙 (트랙 2) 빈피킹 메인 파이프라인.

협력사 인계 `hanwha_bin_picking.py` 흐름을 우리 환경에 맞춰 어댑테이션.
원본은 로컬 보관 (git 추적 X).

흐름:
    카메라 라이브 (Basler) → YOLO 추론 (best.pt) → 2D bbox + depth →
    3D 카메라 좌표 → (옵션) Hand-Eye 변환 → 로봇 베이스 좌표 →
    Modbus 송신 (dry-run 또는 실 로봇)

우리 환경 차이점 (vs 협력사):
    - 카메라: RealSense → Basler Blaze (depth) + ACE2 (RGB, 추후)
    - 좌표: 6DoF (Rx,Ry,Rz) → 4DoF (X,Y,Z,Theta) — 회의 합의
    - 로봇 통신: TCP/Socket → Modbus INT16 (register 130~140)
    - 자세 매칭: bbox 중심만 (협력사) → 6DoF 트랙 1 결과 후크 준비 (트랙 1 통합 대비)

사용법:
    # 카메라 + YOLO 라이브 (Mac에서, 어댑터 + 카메라 연결 필요)
    python -m bin_picking.yolo_track.pipeline.bin_picking_main --live

    # 저장된 이미지로 dry-run (6000에서, 카메라 없이 추론 검증)
    python -m bin_picking.yolo_track.pipeline.bin_picking_main --image path/to/test.jpg

    # mock 카메라 + 모의 픽셀 입력 (CI 또는 빠른 동작 확인)
    python -m bin_picking.yolo_track.pipeline.bin_picking_main --mock

키 (라이브 모드):
    좌클릭   PICK 픽셀 지정
    우클릭   PLACE 픽셀 지정
    Space    pick-and-place 시퀀스 실행 (dry-run)
    y        YOLO 검출 최상위 1개를 PICK 타겟으로
    q        종료

작성 이력:
    - 5/19 W21 화 KAIST 점심/저녁 (Phase 2.2)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# 기본 경로 — 5/18 학습 결과
DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "yolo_track" / "runs" / "v1-yolov8n-0719" / "weights" / "best.pt"
)


# ============================================================
# 결과 데이터 클래스
# ============================================================
@dataclass
class Detection:
    """YOLO 검출 결과 1건."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2 (pixel)
    cx: int
    cy: int

    @classmethod
    def from_yolo_box(cls, box, names: dict) -> "Detection":
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        cls_id = int(box.cls[0].cpu().numpy())
        return cls(
            class_id=cls_id,
            class_name=names.get(cls_id, str(cls_id)),
            confidence=float(box.conf[0].cpu().numpy()),
            bbox=(x1, y1, x2, y2),
            cx=(x1 + x2) // 2,
            cy=(y1 + y2) // 2,
        )


@dataclass
class PickTarget:
    """픽업 타겟 (픽셀 + 3D 좌표 + 옵션 클래스)."""
    u: int
    v: int
    z_mm: float
    camera_xyz: Tuple[float, float, float]
    robot_xyz: Optional[Tuple[float, float, float]] = None
    class_name: Optional[str] = None
    confidence: Optional[float] = None


# ============================================================
# 핀홀 카메라 모델 + Hand-Eye 변환 (협력사 차용 + 4DoF 단순화)
# ============================================================
def pixel_to_camera_3d(
    u: int, v: int, z_mm: float, intrinsics: dict
) -> Tuple[float, float, float]:
    """
    협력사 project_2d_to_3d_camera() 핀홀 모델.
    (u, v, z) → (Xc, Yc, Zc) [mm]

    intrinsics: {"fx", "fy", "ppx", "ppy", ...} (협력사 호환 키)
    """
    fx = intrinsics["fx"]
    fy = intrinsics["fy"]
    ppx = intrinsics.get("ppx", intrinsics.get("cx"))
    ppy = intrinsics.get("ppy", intrinsics.get("cy"))
    xc = (u - ppx) * z_mm / fx
    yc = (v - ppy) * z_mm / fy
    return xc, yc, z_mm


def load_handeye_matrix(npy_path: Path) -> Optional[np.ndarray]:
    """T_gripper2camera.npy 로드. 없으면 None."""
    if npy_path.exists():
        T = np.load(npy_path)
        if T.shape == (4, 4):
            logger.info("Hand-Eye matrix loaded from %s", npy_path)
            return T
        logger.warning("T_gripper2camera shape mismatch: %s", T.shape)
    else:
        logger.warning(
            "T_gripper2camera.npy not found at %s — using identity. "
            "Calibration 필요 (calibration/handeye_calibration.py).",
            npy_path,
        )
    return None


# ============================================================
# Robot stub (5/27 robot_modbus.py로 대체 예정)
# ============================================================
class RobotStub:
    """5/22 시연용 dummy. 실제 Modbus 송신은 robot_modbus.py에서 구현."""

    def __init__(self):
        # 한화 HCR-10L 가상 대기 자세 (실 값은 5/22~ 측정)
        self.current_pose = [250.0, 0.0, 450.0, 0.0]  # X, Y, Z, Theta (4DoF)

    def get_current_pose(self) -> List[float]:
        return list(self.current_pose)

    def execute_pick(self, target: PickTarget) -> None:
        logger.info(
            "[ROBOT STUB] Pick @ pixel (%d, %d), cam=(%.1f, %.1f, %.1f)mm, robot=%s, class=%s conf=%.2f",
            target.u, target.v,
            *target.camera_xyz,
            target.robot_xyz, target.class_name, target.confidence or 0.0,
        )
        # 실 구현: Modbus register 130~140 송신
        # (robot/hanwha_robot_modbus.py — 5/27 작성 예정)


# ============================================================
# 메인 컨트롤러
# ============================================================
class BinPickingController:
    """YOLO + 카메라 + Hand-Eye + 로봇 통합."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        handeye_path: Optional[Path] = None,
        use_ace2: bool = False,
        dry_run: bool = True,
    ):
        self.dry_run = dry_run
        self.handeye_path = handeye_path
        self.gripper2cam = (
            load_handeye_matrix(handeye_path) if handeye_path else None
        )
        if self.gripper2cam is None:
            self.gripper2cam = np.eye(4)

        # YOLO 모델 로드
        from ultralytics import YOLO  # 지연 임포트 (CI에서 미설치 환경 회피)
        if not model_path.exists():
            raise FileNotFoundError(
                f"YOLO model not found: {model_path}\n"
                "5/18 학습 결과가 yolo_track/runs/v1-yolov8n-0719/weights/best.pt에 있는지 확인"
            )
        self.model = YOLO(str(model_path))
        logger.info("YOLO loaded: %s (classes=%s)", model_path.name, list(self.model.names.values()))

        # 카메라 (lazy init — mock 모드에서는 None)
        self._camera = None
        self.use_ace2 = use_ace2

        # 로봇 (5/27 robot_modbus.py로 대체)
        self.robot = RobotStub()

    def open_camera(self) -> None:
        """카메라 시작. mock 모드에서는 호출 X."""
        if self._camera is None:
            from bin_picking.yolo_track.camera.basler_wrapper import BaslerWrapper
            self._camera = BaslerWrapper(use_ace2=self.use_ace2)
            self._camera.start()

    @property
    def intrinsics(self) -> dict:
        if self._camera is None:
            raise RuntimeError("Camera not started")
        return self._camera.intrinsics

    def detect(self, image: np.ndarray) -> List[Detection]:
        """YOLO 추론 → Detection 리스트."""
        results = self.model.predict(image, verbose=False)[0]
        return [Detection.from_yolo_box(box, self.model.names) for box in results.boxes]

    def pixel_to_robot(self, u: int, v: int, z_mm: float) -> Tuple[float, float, float]:
        """픽셀 + depth → 로봇 베이스 좌표 (mm). Hand-Eye 미캘리브 시 카메라 좌표 그대로."""
        intr = self.intrinsics
        cam_xyz = pixel_to_camera_3d(u, v, z_mm, intr)
        if np.allclose(self.gripper2cam, np.eye(4)):
            # 캘리브 안 됨 → 카메라 좌표 그대로 (좌표계 미정)
            return cam_xyz
        # P_base = T_base2gripper @ T_gripper2cam @ P_camera
        # T_base2gripper는 4DoF 단순화 (X,Y,Z,Theta) — 추후 구현
        # 지금은 T_gripper2cam만 적용 (gripper 기준 좌표 반환)
        p_cam_h = np.array([*cam_xyz, 1.0])
        p_gripper = self.gripper2cam @ p_cam_h
        return tuple(p_gripper[:3])

    def make_target(self, u: int, v: int, depth_image: np.ndarray, detection: Optional[Detection] = None) -> Optional[PickTarget]:
        """(u, v) + depth → PickTarget. depth=0이면 None."""
        if not (0 <= u < depth_image.shape[1] and 0 <= v < depth_image.shape[0]):
            logger.warning("Pixel out of range: (%d, %d)", u, v)
            return None
        z_mm = float(depth_image[v, u])
        if z_mm <= 0:
            logger.warning("Invalid depth at (%d, %d): %f", u, v, z_mm)
            return None
        cam_xyz = pixel_to_camera_3d(u, v, z_mm, self.intrinsics)
        try:
            robot_xyz = self.pixel_to_robot(u, v, z_mm)
        except Exception as e:
            logger.warning("Robot transform failed (handeye not ready?): %s", e)
            robot_xyz = None
        return PickTarget(
            u=u, v=v, z_mm=z_mm,
            camera_xyz=cam_xyz,
            robot_xyz=robot_xyz,
            class_name=detection.class_name if detection else None,
            confidence=detection.confidence if detection else None,
        )

    def execute(self, target: PickTarget) -> None:
        """픽업 실행 (dry-run이면 로그만)."""
        if self.dry_run:
            logger.info("[DRY RUN] %s", target)
        self.robot.execute_pick(target)

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()


# ============================================================
# 시각화
# ============================================================
def draw_detections(image: np.ndarray, detections: List[Detection]) -> np.ndarray:
    """탐지 박스 + 라벨 그리기."""
    import cv2
    out = image.copy()
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(out, (det.cx, det.cy), 4, (0, 0, 255), -1)
        label = f"{det.class_name} {det.confidence:.2f}"
        cv2.putText(out, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return out


def draw_picks(image: np.ndarray, pick_uv: Optional[Tuple[int, int]], place_uv: Optional[Tuple[int, int]]) -> np.ndarray:
    """PICK / PLACE 마커 표시."""
    import cv2
    out = image.copy()
    if pick_uv is not None:
        cv2.circle(out, pick_uv, 8, (255, 0, 0), -1)
        cv2.putText(out, "PICK", (pick_uv[0] + 10, pick_uv[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    if place_uv is not None:
        cv2.circle(out, place_uv, 8, (0, 0, 255), -1)
        cv2.putText(out, "PLACE", (place_uv[0] + 10, place_uv[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return out


# ============================================================
# 모드별 실행
# ============================================================
def run_live(args) -> None:
    """라이브 모드 — Mac에서 카메라 + YOLO + GUI."""
    import cv2

    controller = BinPickingController(
        model_path=Path(args.model),
        handeye_path=Path(args.handeye) if args.handeye else None,
        use_ace2=args.ace2,
        dry_run=True,
    )
    controller.open_camera()
    logger.info("Camera intrinsics: %s", controller.intrinsics)

    pick_uv: Optional[Tuple[int, int]] = None
    place_uv: Optional[Tuple[int, int]] = None

    def on_mouse(event, x, y, flags, param):
        nonlocal pick_uv, place_uv
        if event == cv2.EVENT_LBUTTONDOWN:
            pick_uv = (x, y)
            logger.info("PICK selected: (%d, %d)", x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            place_uv = (x, y)
            logger.info("PLACE selected: (%d, %d)", x, y)

    window = "Bin Picking YOLO Live"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)

    try:
        while True:
            color, frames, depth = controller._camera.get_frames()
            if depth is None:
                continue

            # YOLO 추론 (color가 있으면 color, 없으면 depth visualize)
            if color is not None:
                detections = controller.detect(color)
                display = draw_detections(color, detections)
            else:
                # ACE2 없으면 depth 컬러맵으로 추론 시도 (학습 데이터는 RGB지만 일단 표시)
                depth_vis = cv2.convertScaleAbs(depth, alpha=0.03)
                depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
                detections = []  # depth만으로는 YOLO 추론 X
                display = depth_color

            display = draw_picks(display, pick_uv, place_uv)

            # 하단 안내
            info = f"[Space] Execute | [y] YOLO top1 -> PICK | [q] Quit | dets={len(detections)}"
            h, w = display.shape[:2]
            cv2.rectangle(display, (0, h - 30), (w, h), (45, 45, 45), -1)
            cv2.putText(display, info, (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1)

            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                break
            elif key == ord('y') and detections:
                top = max(detections, key=lambda d: d.confidence)
                pick_uv = (top.cx, top.cy)
                logger.info("YOLO top1 → PICK: %s @ (%d, %d)",
                            top.class_name, top.cx, top.cy)
            elif key == ord(' '):
                if pick_uv is None:
                    logger.warning("PICK not set — skip execute")
                    continue
                # 가까운 detection 찾아서 클래스 정보 주입
                matching = None
                if detections:
                    matching = min(detections, key=lambda d: (d.cx - pick_uv[0])**2 + (d.cy - pick_uv[1])**2)
                target = controller.make_target(pick_uv[0], pick_uv[1], depth, matching)
                if target is None:
                    continue
                controller.execute(target)

    finally:
        controller.close()
        cv2.destroyAllWindows()


def run_image(args) -> None:
    """단일 이미지 dry-run — 6000에서 카메라 없이 추론 검증."""
    import cv2

    img_path = Path(args.image)
    if not img_path.exists():
        logger.error("Image not found: %s", img_path)
        sys.exit(1)

    image = cv2.imread(str(img_path))
    if image is None:
        logger.error("Failed to load image: %s", img_path)
        sys.exit(1)

    controller = BinPickingController(
        model_path=Path(args.model),
        dry_run=True,
    )
    detections = controller.detect(image)
    print(f"=== YOLO 추론 결과 ({img_path.name}) ===")
    print(f"Detections: {len(detections)}")
    for i, det in enumerate(detections):
        print(f"  [{i}] {det.class_name} conf={det.confidence:.3f} bbox={det.bbox} center=({det.cx},{det.cy})")

    if args.save_viz:
        out = draw_detections(image, detections)
        out_path = img_path.with_name(img_path.stem + "_pred.jpg")
        cv2.imwrite(str(out_path), out)
        print(f"Visualization saved: {out_path}")


def run_mock(args) -> None:
    """Mock 모드 — 카메라/이미지 없이 시퀀스 흐름만 검증."""
    print("=== Mock 모드: 모듈 import + 컨트롤러 초기화 검증 ===")
    controller = BinPickingController(
        model_path=Path(args.model),
        dry_run=True,
    )
    print(f"✅ YOLO 로드 OK ({len(controller.model.names)} 클래스)")
    print(f"   classes: {list(controller.model.names.values())}")
    print(f"✅ Hand-Eye matrix: {'loaded' if not np.allclose(controller.gripper2cam, np.eye(4)) else 'identity (캘리브 필요)'}")
    print(f"✅ Robot stub: pose={controller.robot.get_current_pose()}")

    # 가짜 PickTarget 생성
    fake_intr = {"fx": 553.0, "fy": 553.0, "ppx": 424.0, "ppy": 240.0, "cx": 424.0, "cy": 240.0, "width": 848, "height": 480}
    cam_xyz = pixel_to_camera_3d(424, 240, 800.0, fake_intr)
    print(f"✅ pixel_to_camera_3d (center, z=800mm) = {cam_xyz}")

    target = PickTarget(u=424, v=240, z_mm=800.0, camera_xyz=cam_xyz, class_name="part_3", confidence=0.95)
    controller.execute(target)
    print("=== Mock 모드 완료 ===")


# ============================================================
# Entry point
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="YOLO 트랙 빈피킹 메인")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH),
                        help="YOLO best.pt 경로 (기본 5/18 학습 결과)")
    parser.add_argument("--handeye", default=None,
                        help="T_gripper2camera.npy 경로 (선택)")
    parser.add_argument("--ace2", action="store_true",
                        help="ACE2 RGB 동시 캡처 (5/22~)")

    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument("--live", action="store_true", help="라이브 카메라 (Mac)")
    mode.add_argument("--image", type=str, help="단일 이미지 dry-run (6000)")
    mode.add_argument("--mock", action="store_true", help="Mock 모드 (CI / 모듈 검증)")

    parser.add_argument("--save-viz", action="store_true", help="--image 모드에서 시각화 저장")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.live:
        run_live(args)
    elif args.image:
        run_image(args)
    else:
        run_mock(args)


if __name__ == "__main__":
    main()
