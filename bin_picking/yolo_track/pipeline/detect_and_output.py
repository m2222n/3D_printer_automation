"""
협력사 좌표 6요소 출력 모듈 (5/20 명세 이행).

목적
----
협력사 빈피킹 인터페이스에 맞춘 detection 결과를 표준 형식 (YAML/JSON)으로 출력.
내부 피드백 + 협력사 5/20 답변 반영.

협력사 6요소 명세 (5/20 회신)
---------------------------------
1. x      — 2D 픽셀 가로 좌표
2. y      — 2D 픽셀 세로 좌표
3. z      — 픽셀 (x,y)의 depth (mm, Blaze)
4. edge   — 외각선 (segmentation contour). v2 detection은 bbox 4코너 fallback
5. angle  — 물체 회전 각도 (degree). v2 detection은 0° fallback, seg/OBB에서 정확값
6. label  — 클래스 이름 (Part1~5)

추가 출력 (한솔 시스템 적응성 위해)
- camera_3d: (Xc, Yc, Zc) mm — 핀홀 모델로 변환된 카메라 좌표
- bbox_pixel: (cx, cy, w, h) — axis-aligned bounding box
- confidence: float — YOLO confidence
- metadata: 카메라/intrinsics 버전 / 타임스탬프

미확정 5항목 처리 (5/20 메모리 참조)
- 좌표계 기준점: 카메라 픽셀 + camera_3d 둘 다 출력 → 한솔이 골라쓰기
- 단위: mm 통일 (Blaze depth = mm, intrinsics 단위 = pixel)
- "Pointcloud": dict YAML이 1차, PCD는 옵션
- 각도 정의: 0° = 수평, 0°~360° 표준 (yaml에 명시)
- edge 형식: polygon vertices (detection은 bbox 4코너로 fallback)

진화 경로
-------
- 현재 (v2 detection, 5/22): bbox만 → edge = 4 corners, angle = 0
- v3 seg 모델 (5/27+): mask contour → edge = polygon, angle = minAreaRect
- v4 OBB 모델 (필요 시): rotated bbox → edge + angle 정확

사용법
-----
    # CLI dry-run (RGB 이미지 + 균일 depth 800mm로 테스트)
    python -m bin_picking.yolo_track.pipeline.detect_and_output \
        --image test.jpg --output result.yaml

    # 라이브 카메라 + best.pt
    python -m bin_picking.yolo_track.pipeline.detect_and_output \
        --live --model runs/v2-yolov11m/weights/best.pt

    # Python 모듈로
    from bin_picking.yolo_track.pipeline.detect_and_output import detect_and_output
    result = detect_and_output(image, depth, model, intrinsics)

설계 결정 근거
-------------
1. detect_and_output()을 순수 함수로 → 테스트/재사용 쉬움
2. SixElement dataclass → 한솔 명세 1:1 매핑
3. depth 노이즈는 bbox 내부 median으로 완화 (단일 픽셀 X)
4. bbox 경계 클램핑 → out-of-bounds 안전
5. angle 0°~360° 표준화 → 한솔 통합 시 헷갈림 회피
6. 부가 정보 (camera_3d, bbox) 같이 출력 → 한솔이 자유롭게 선택

작성 이력
--------
- 5/22 W21 금 사무실 (v2 학습 중 병행 작성)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 상수 + 기본값
# ============================================================
SPEC_VERSION = "hansol_6elements_v1_20260520"
"""한솔 명세 버전. 명세 갱신 시 증가."""

OUTPUT_SCHEMA_VERSION = "orinu_output_v1_20260522"
"""우리 출력 스키마 버전. 필드 추가/변경 시 증가."""

DEFAULT_INTRINSICS = {
    "camera": "Basler_Blaze_112_estimated",
    "version": "estimated_v2_20260513",
    "fx": 553.0, "fy": 553.0,
    "ppx": 424.0, "ppy": 240.0,
    "width": 848, "height": 480,
    "unit": "pixel for fx/fy/ppx/ppy",
}


# ============================================================
# 데이터 클래스 — 한솔 6요소 + 부가 정보
# ============================================================
@dataclass
class SixElement:
    """
    한솔 명세 6요소 + 부가 정보.

    - 6요소 (필수): x, y, z, edge, angle, label
    - 부가: bbox_pixel, camera_3d, confidence, source, notes
    """

    # === 한솔 6요소 ===
    x: int                                    # 픽셀 가로
    y: int                                    # 픽셀 세로
    z: float                                  # depth (mm)
    edge: List[List[int]]                     # 외곽선 polygon [[x,y], ...]
    angle: float                              # 회전 각도 (degree, 0~360)
    label: str                                # 클래스 이름

    # === 부가 정보 (한솔 시스템 적응성) ===
    bbox_pixel: dict = field(default_factory=dict)
    """axis-aligned bbox: {cx, cy, w, h, x1, y1, x2, y2}"""

    camera_3d: dict = field(default_factory=dict)
    """카메라 3D 좌표 (mm): {Xc, Yc, Zc}"""

    confidence: float = 0.0
    """YOLO confidence (0~1)"""

    source: str = "detection"
    """edge/angle 출처: "detection" | "obb" | "segmentation" """

    notes: str = ""
    """이 항목에 대한 비고 (예: "depth fallback 800mm 사용")"""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DetectionFrame:
    """한 프레임의 전체 detection 결과 + 메타데이터."""
    timestamp: str
    image_shape: Tuple[int, int]               # (H, W)
    spec_version: str
    output_schema_version: str
    intrinsics: dict
    detections: List[SixElement]
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "image_shape": list(self.image_shape),
            "spec_version": self.spec_version,
            "output_schema_version": self.output_schema_version,
            "intrinsics": self.intrinsics,
            "detections": [d.to_dict() for d in self.detections],
            "notes": self.notes,
        }


# ============================================================
# Depth 안전 추출
# ============================================================
def safe_depth_at(
    depth: np.ndarray,
    x: int,
    y: int,
    window: int = 5,
    fallback_mm: Optional[float] = None,
) -> Tuple[float, str]:
    """
    (x, y) 픽셀의 depth를 안전하게 추출.

    - 단일 픽셀 노이즈 회피: window×window 영역 median
    - 0/음수/NaN 제외
    - 모두 invalid면 fallback (없으면 0.0)

    Returns:
        (depth_mm, source_note)
    """
    h, w = depth.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return (fallback_mm or 0.0, f"out_of_bounds_fallback={fallback_mm}")

    half = window // 2
    x0, x1 = max(0, x - half), min(w, x + half + 1)
    y0, y1 = max(0, y - half), min(h, y + half + 1)
    patch = depth[y0:y1, x0:x1].astype(np.float32)
    valid = patch[(patch > 0) & np.isfinite(patch)]
    if valid.size == 0:
        if fallback_mm is not None:
            return (float(fallback_mm), f"no_valid_depth_fallback={fallback_mm}mm")
        # 단일 픽셀 그대로 (0일 수 있음)
        z = float(depth[y, x])
        return (z, "single_pixel_unreliable" if z <= 0 else "single_pixel")

    z_med = float(np.median(valid))
    return (z_med, f"median_{window}x{window}_valid={valid.size}")


# ============================================================
# 픽셀 ↔ 3D (핀홀)
# ============================================================
def pixel_to_camera_3d(
    u: float, v: float, z_mm: float, intrinsics: dict
) -> Tuple[float, float, float]:
    """협력사 + 5/19 bin_picking_main.py와 동일한 핀홀 모델."""
    fx = intrinsics["fx"]
    fy = intrinsics["fy"]
    ppx = intrinsics.get("ppx", intrinsics.get("cx"))
    ppy = intrinsics.get("ppy", intrinsics.get("cy"))
    xc = (u - ppx) * z_mm / fx
    yc = (v - ppy) * z_mm / fy
    return float(xc), float(yc), float(z_mm)


# ============================================================
# bbox → edge / angle (detection fallback)
# ============================================================
def bbox_to_edge_corners(x1: int, y1: int, x2: int, y2: int) -> List[List[int]]:
    """
    axis-aligned bbox → 4 corner polygon (시계 방향 시작 = 좌상단).

    detection만 있을 때 한솔 'edge' 명세에 대한 fallback.
    seg 모델 도입 시 (v3) 진짜 polygon contour로 교체.
    """
    return [
        [int(x1), int(y1)],   # 좌상
        [int(x2), int(y1)],   # 우상
        [int(x2), int(y2)],   # 우하
        [int(x1), int(y2)],   # 좌하
    ]


def estimate_obb_angle(
    image_or_mask: np.ndarray,
    bbox: Tuple[int, int, int, int],
) -> Tuple[float, List[List[int]]]:
    """
    bbox 영역에서 OBB angle을 추정.

    detection-only일 때 cv2.minAreaRect로 OBB 시도.
    image_or_mask가 이미지면 grayscale + Otsu로 mask 생성 후 contour 찾음.
    mask면 그대로 contour.

    Returns:
        (angle_deg, polygon_4corners)
        - angle_deg: 0~360 (수평 0°, 반시계 양)
        - polygon: 4 corners (rotated)

    실패 시: angle=0, polygon=bbox 4코너 (axis-aligned)
    """
    try:
        import cv2
    except ImportError:
        logger.warning("cv2 unavailable, OBB skipped")
        return 0.0, bbox_to_edge_corners(*bbox)

    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return 0.0, bbox_to_edge_corners(*bbox)

    roi = image_or_mask[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0, bbox_to_edge_corners(*bbox)

    # Mask 만들기 (이미지면 grayscale + threshold)
    if roi.ndim == 3:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi.astype(np.uint8) if roi.dtype != np.uint8 else roi

    # 배경 분리 — Otsu auto threshold
    try:
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    except cv2.error:
        return 0.0, bbox_to_edge_corners(*bbox)

    # contour 찾기
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0, bbox_to_edge_corners(*bbox)

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 10:  # 너무 작으면 신뢰 X
        return 0.0, bbox_to_edge_corners(*bbox)

    # minAreaRect — center, (w, h), angle
    rect = cv2.minAreaRect(largest)
    box_pts = cv2.boxPoints(rect)

    # ROI 좌표 → 원본 이미지 좌표로 복원
    box_pts_global = box_pts + np.array([x1, y1], dtype=np.float32)
    polygon = [[int(p[0]), int(p[1])] for p in box_pts_global]

    # angle 정규화: cv2.minAreaRect → [-90, 0]
    # 표준 [0, 360) 으로 변환
    angle_raw = rect[2]
    # rect의 width < height면 angle += 90 (보통 longer side 기준)
    w, h = rect[1]
    if w < h:
        angle_raw += 90.0
    # 음수면 360 더하기
    angle_norm = angle_raw % 360.0

    return float(angle_norm), polygon


# ============================================================
# 핵심: detection → 6요소 변환
# ============================================================
def detection_to_six_element(
    yolo_box,
    class_names: dict,
    depth: np.ndarray,
    intrinsics: dict,
    color_image: Optional[np.ndarray] = None,
    *,
    obb_estimate: bool = True,
    depth_window: int = 5,
    depth_fallback_mm: Optional[float] = None,
) -> SixElement:
    """
    YOLO detection 1건 → 한솔 6요소 SixElement.

    Args:
        yolo_box: ultralytics Box (예: results.boxes[0])
        class_names: model.names dict
        depth: depth image (HxW, mm, uint16 or float)
        intrinsics: 카메라 intrinsics dict
        color_image: RGB image (OBB 추정 시 사용, 없으면 depth 사용)
        obb_estimate: True면 cv2.minAreaRect로 OBB 추정, False면 angle=0
        depth_window: depth 추출 시 median 영역 크기
        depth_fallback_mm: depth 추출 실패 시 fallback (None이면 0.0)

    Returns:
        SixElement
    """
    # YOLO box 파싱
    xyxy = yolo_box.xyxy[0].cpu().numpy()
    x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
    cls_id = int(yolo_box.cls[0].cpu().numpy())
    label = class_names.get(cls_id, f"class_{cls_id}")
    conf = float(yolo_box.conf[0].cpu().numpy())

    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    # bbox를 이미지 경계로 클램핑
    H, W = depth.shape[:2]
    x1c = max(0, min(W - 1, x1))
    y1c = max(0, min(H - 1, y1))
    x2c = max(0, min(W - 1, x2))
    y2c = max(0, min(H - 1, y2))

    # === z (depth) ===
    z_mm, depth_note = safe_depth_at(
        depth, cx, cy, window=depth_window, fallback_mm=depth_fallback_mm
    )

    # === edge + angle ===
    notes_parts = [f"depth_source={depth_note}"]
    if obb_estimate and color_image is not None:
        try:
            angle, polygon = estimate_obb_angle(color_image, (x1c, y1c, x2c, y2c))
            edge_source = "obb_minAreaRect_otsu"
        except Exception as e:
            logger.warning("OBB estimation failed for %s: %s", label, e)
            angle = 0.0
            polygon = bbox_to_edge_corners(x1c, y1c, x2c, y2c)
            edge_source = "bbox_fallback_obb_error"
    else:
        angle = 0.0
        polygon = bbox_to_edge_corners(x1c, y1c, x2c, y2c)
        edge_source = "bbox_axis_aligned" if not obb_estimate else "bbox_no_color"

    notes_parts.append(f"edge_source={edge_source}")

    # === camera_3d ===
    xc, yc, zc = pixel_to_camera_3d(cx, cy, z_mm, intrinsics)

    return SixElement(
        # 한솔 6요소
        x=cx,
        y=cy,
        z=round(z_mm, 1),
        edge=polygon,
        angle=round(angle, 2),
        label=label,
        # 부가
        bbox_pixel={
            "cx": cx, "cy": cy,
            "w": x2c - x1c, "h": y2c - y1c,
            "x1": x1c, "y1": y1c, "x2": x2c, "y2": y2c,
        },
        camera_3d={"Xc": round(xc, 1), "Yc": round(yc, 1), "Zc": round(zc, 1)},
        confidence=round(conf, 3),
        source=edge_source.split("_")[0],
        notes=" | ".join(notes_parts),
    )


# ============================================================
# 메인 함수: 이미지 + depth → DetectionFrame
# ============================================================
def detect_and_output(
    color_image: np.ndarray,
    depth: np.ndarray,
    model,
    intrinsics: dict,
    *,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    obb_estimate: bool = True,
    depth_fallback_mm: Optional[float] = None,
    notes: str = "",
) -> DetectionFrame:
    """
    한 프레임에서 모든 detection의 6요소를 추출.

    Args:
        color_image: RGB image (HxWx3, BGR or RGB — OBB threshold만 영향)
        depth: depth image (HxW, mm)
        model: ultralytics YOLO model (.predict 가능)
        intrinsics: 카메라 intrinsics dict
        conf_threshold: YOLO confidence threshold
        iou_threshold: NMS IoU threshold
        obb_estimate: True면 OBB(minAreaRect) 추정
        depth_fallback_mm: depth 실패 시 fallback

    Returns:
        DetectionFrame (multi-detections + metadata)
    """
    if color_image.shape[:2] != depth.shape[:2]:
        # depth와 color 해상도 다를 수 있음 → 일단 경고
        logger.warning(
            "Shape mismatch: color=%s depth=%s (RGB↔depth alignment 필요)",
            color_image.shape[:2], depth.shape[:2],
        )

    results = model.predict(
        color_image,
        conf=conf_threshold,
        iou=iou_threshold,
        verbose=False,
    )[0]

    detections = []
    for box in results.boxes:
        try:
            elem = detection_to_six_element(
                box,
                class_names=model.names,
                depth=depth,
                intrinsics=intrinsics,
                color_image=color_image,
                obb_estimate=obb_estimate,
                depth_fallback_mm=depth_fallback_mm,
            )
            detections.append(elem)
        except Exception as e:
            logger.exception("Detection conversion failed: %s", e)

    return DetectionFrame(
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        image_shape=color_image.shape[:2],
        spec_version=SPEC_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        intrinsics=intrinsics,
        detections=detections,
        notes=notes,
    )


# ============================================================
# 출력 직렬화
# ============================================================
def save_yaml(frame: DetectionFrame, path: Path) -> None:
    """YAML 저장 (한솔에 보낼 표준 형식)."""
    try:
        import yaml
    except ImportError:
        logger.error("PyYAML 미설치 — JSON으로 fallback")
        save_json(frame, path.with_suffix(".json"))
        return
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            frame.to_dict(),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    logger.info("Saved YAML: %s", path)


def save_json(frame: DetectionFrame, path: Path, *, indent: int = 2) -> None:
    """JSON 저장."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(frame.to_dict(), f, ensure_ascii=False, indent=indent)
    logger.info("Saved JSON: %s", path)


# ============================================================
# CLI
# ============================================================
def _cli_image(args) -> int:
    """단일 이미지로 dry-run."""
    try:
        import cv2
    except ImportError:
        print("cv2 미설치 — pip install opencv-python", file=sys.stderr)
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics 미설치 — pip install ultralytics", file=sys.stderr)
        return 1

    img_path = Path(args.image)
    if not img_path.exists():
        print(f"이미지 없음: {img_path}", file=sys.stderr)
        return 1

    image = cv2.imread(str(img_path))
    if image is None:
        print(f"이미지 로드 실패: {img_path}", file=sys.stderr)
        return 1

    # depth가 없으면 균일 depth (테스트용)
    if args.depth:
        depth_path = Path(args.depth)
        # uint16 PNG 또는 npy 지원
        if depth_path.suffix == ".npy":
            depth = np.load(depth_path)
        else:
            depth = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
            if depth is None:
                print(f"depth 로드 실패: {depth_path}", file=sys.stderr)
                return 1
        notes = f"depth from {depth_path.name}"
    else:
        H, W = image.shape[:2]
        depth = np.full((H, W), args.fake_depth_mm, dtype=np.float32)
        notes = f"synthetic_uniform_depth_{args.fake_depth_mm}mm (no depth provided)"

    # 모델 로드
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"모델 없음: {model_path}", file=sys.stderr)
        return 1
    model = YOLO(str(model_path))

    # intrinsics 결정
    intrinsics = DEFAULT_INTRINSICS.copy()
    intrinsics["width"] = image.shape[1]
    intrinsics["height"] = image.shape[0]

    # 실행
    frame = detect_and_output(
        color_image=image,
        depth=depth,
        model=model,
        intrinsics=intrinsics,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        obb_estimate=not args.no_obb,
        depth_fallback_mm=args.fake_depth_mm,
        notes=notes,
    )

    # 출력
    print(f"=== 6요소 출력 ({img_path.name}) ===")
    print(f"Spec: {frame.spec_version}")
    print(f"Detections: {len(frame.detections)}")
    print()
    for i, det in enumerate(frame.detections):
        print(f"[{i}] {det.label} conf={det.confidence:.3f}")
        print(f"    x={det.x} y={det.y} z={det.z}mm angle={det.angle}°")
        print(f"    edge={det.edge}")
        print(f"    camera_3d={det.camera_3d}")
        print(f"    notes={det.notes}")
        print()

    # 파일 저장
    if args.output:
        out_path = Path(args.output)
        if out_path.suffix in [".yaml", ".yml"]:
            save_yaml(frame, out_path)
        else:
            save_json(frame, out_path)

    # 시각화
    if args.save_viz:
        try:
            import cv2
            vis = image.copy()
            for det in frame.detections:
                bx = det.bbox_pixel
                cv2.rectangle(vis, (bx["x1"], bx["y1"]), (bx["x2"], bx["y2"]), (0, 255, 0), 2)
                # OBB polygon
                pts = np.array(det.edge, dtype=np.int32)
                cv2.polylines(vis, [pts], isClosed=True, color=(255, 200, 0), thickness=2)
                cv2.circle(vis, (det.x, det.y), 4, (0, 0, 255), -1)
                txt = f"{det.label} {det.confidence:.2f} ang={det.angle:.0f}"
                cv2.putText(vis, txt, (bx["x1"], max(0, bx["y1"] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            viz_path = img_path.with_name(img_path.stem + "_6elements.jpg")
            cv2.imwrite(str(viz_path), vis)
            print(f"Visualization: {viz_path}")
        except Exception as e:
            logger.warning("Visualization failed: %s", e)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="한솔 6요소 출력 (5/20 명세) — YOLO detection → x,y,z,edge,angle,label"
    )
    parser.add_argument("--image", required=True, help="입력 RGB 이미지 경로")
    parser.add_argument("--depth", default=None,
                        help="depth 이미지 (uint16 PNG 또는 .npy). 없으면 균일 fake-depth")
    parser.add_argument("--fake-depth-mm", type=float, default=800.0,
                        help="depth 없을 때 균일 depth (mm)")
    parser.add_argument("--model", default=None,
                        help="YOLO best.pt 경로 (기본은 v1)")
    parser.add_argument("--conf", type=float, default=0.25, help="confidence threshold")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold")
    parser.add_argument("--no-obb", action="store_true",
                        help="OBB 추정 끄기 (angle=0, edge=bbox 4코너)")
    parser.add_argument("--output", default=None,
                        help="출력 파일 (.yaml/.yml/.json). 미지정 시 콘솔만")
    parser.add_argument("--save-viz", action="store_true",
                        help="시각화 이미지 저장 (_6elements.jpg)")

    args = parser.parse_args()

    if args.model is None:
        # 기본: v1 학습 결과
        default_v1 = (
            Path(__file__).resolve().parents[1]
            / "runs" / "v1-yolov8n-0719" / "weights" / "best.pt"
        )
        args.model = str(default_v1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    return _cli_image(args)


if __name__ == "__main__":
    sys.exit(main())
