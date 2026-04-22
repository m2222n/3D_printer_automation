"""
대표님 시연용 라이브 데모 UI 렌더러
=====================================

Basler Blaze-112 (ToF depth) + ace2 (RGB 5MP) 듀얼 카메라의 입력과
L1~L5 파이프라인 인식 결과를 2×2 그리드로 실시간 시각화한다.

레이아웃:
    ┌───────────────────────┬───────────────────────┐
    │  ① ace2 RGB           │  ② Blaze-112 depth    │
    │  (리사이즈된 컬러 뷰) │  (viridis 컬러맵)     │
    ├───────────────────────┼───────────────────────┤
    │  ③ 인식 결과 오버레이 │  ④ 성능/매칭 정보 표  │
    │  (CAD 투영 + 색상)    │  (부품명/fitness/RMSE)│
    └───────────────────────┴───────────────────────┘

사용법:
    from bin_picking.src.visualization.demo_ui import DemoRenderer
    r = DemoRenderer(cell_w=640, cell_h=480)
    canvas = r.render(rgb_image, depth_map, overlay_image, parts_info)
    cv2.imshow("Demo", canvas)

설계 원칙:
- numpy + OpenCV만 사용 (Open3D 창 대신 2D 이미지로 통합)
- 각 셀은 독립적으로 None 허용 (부분 데이터 상태도 표시)
- 셀 크기 통일, 상하좌우 패딩 일정
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


# ============================================================
# 색상 팔레트 (BGR)
# ============================================================
COLOR_BG = (32, 32, 32)              # 어두운 회색 (전체 배경)
COLOR_FRAME = (80, 80, 80)           # 셀 테두리
COLOR_TITLE_BG = (48, 48, 48)        # 타이틀 바
COLOR_TEXT = (230, 230, 230)         # 기본 텍스트
COLOR_ACCEPT = (0, 200, 0)           # ACCEPT (초록)
COLOR_WARN = (0, 200, 220)           # WARN (노랑)
COLOR_REJECT = (0, 0, 220)           # REJECT (빨강)
COLOR_HEADER = (200, 200, 50)        # 표 헤더 (청록)

# 텍스트 설정
FONT = cv2.FONT_HERSHEY_SIMPLEX


# ============================================================
# 데이터 구조
# ============================================================
@dataclass
class PartInfo:
    """인식된 부품 하나의 정보."""
    name: str
    fitness: float
    rmse_mm: float
    decision: str           # "ACCEPT" | "WARN" | "REJECT"
    cluster_id: int
    n_points: int
    extent_mm: tuple        # (x, y, z) 바운딩 박스 크기

    @property
    def color(self) -> tuple:
        if self.decision == "ACCEPT":
            return COLOR_ACCEPT
        elif self.decision == "WARN":
            return COLOR_WARN
        else:
            return COLOR_REJECT


@dataclass
class PipelineStats:
    """파이프라인 실행 통계."""
    n_input_points: int = 0
    n_filtered_points: int = 0
    n_clusters: int = 0
    n_accepted: int = 0
    n_warn: int = 0
    n_rejected: int = 0
    time_l2_ms: float = 0.0
    time_l3_ms: float = 0.0
    time_l4_ms: float = 0.0
    time_total_ms: float = 0.0


# ============================================================
# DemoRenderer
# ============================================================
class DemoRenderer:
    """2×2 그리드 데모 UI 렌더러."""

    def __init__(
        self,
        cell_w: int = 640,
        cell_h: int = 480,
        title_h: int = 38,
        padding: int = 8,
    ):
        """
        Parameters
        ----------
        cell_w, cell_h: 각 셀의 픽셀 크기 (이미지 영역만, 타이틀 제외)
        title_h: 셀 상단 타이틀 바 높이
        padding: 셀 간 간격 (픽셀)
        """
        self.cell_w = cell_w
        self.cell_h = cell_h
        self.title_h = title_h
        self.pad = padding

        # 캔버스 전체 크기
        cell_total_h = cell_h + title_h
        self.canvas_w = cell_w * 2 + padding * 3
        self.canvas_h = cell_total_h * 2 + padding * 3

    # ============================================================
    # 공개 API
    # ============================================================
    def render(
        self,
        rgb_image: Optional[np.ndarray] = None,
        depth_map: Optional[np.ndarray] = None,
        overlay_image: Optional[np.ndarray] = None,
        parts: Optional[List[PartInfo]] = None,
        stats: Optional[PipelineStats] = None,
        status_text: Optional[str] = None,
    ) -> np.ndarray:
        """2×2 그리드 캔버스를 렌더링한다.

        Parameters
        ----------
        rgb_image: ace2 원본 또는 리사이즈된 컬러 이미지 (H, W, 3) BGR
        depth_map: Blaze-112 depth (H, W) uint16 mm 단위
        overlay_image: depth 위에 CAD 오버레이된 이미지 (H, W, 3) BGR
        parts: 인식된 부품 목록 (top-1만 표시 권장)
        stats: 파이프라인 통계
        status_text: 하단 상태바에 표시할 텍스트 (예: "LIVE" / "CAPTURED" / "WAITING")

        Returns
        -------
        canvas: (canvas_h, canvas_w, 3) BGR 이미지
        """
        canvas = np.full((self.canvas_h, self.canvas_w, 3), COLOR_BG, dtype=np.uint8)

        # 셀 위치 계산
        cell_positions = self._compute_cell_positions()

        # ① ace2 RGB
        rgb_cell = self._render_rgb_cell(rgb_image)
        self._place_cell(canvas, rgb_cell, cell_positions[0], "1. ace2 RGB (5MP)")

        # ② Blaze-112 depth
        depth_cell = self._render_depth_cell(depth_map)
        self._place_cell(canvas, depth_cell, cell_positions[1], "2. Blaze-112 Depth (ToF)")

        # ③ 인식 결과 오버레이
        overlay_cell = self._render_overlay_cell(overlay_image, parts)
        self._place_cell(canvas, overlay_cell, cell_positions[2], "3. Recognition (CAD Overlay)")

        # ④ 성능 표
        table_cell = self._render_table_cell(parts, stats)
        self._place_cell(canvas, table_cell, cell_positions[3], "4. Matching Results")

        # 하단 상태바 (옵션)
        if status_text:
            self._render_status_bar(canvas, status_text)

        return canvas

    # ============================================================
    # 내부: 셀 위치
    # ============================================================
    def _compute_cell_positions(self) -> List[tuple]:
        """4개 셀의 (x, y) 좌상단 좌표 반환."""
        w, h, p = self.cell_w, self.cell_h + self.title_h, self.pad
        return [
            (p, p),                    # ① 좌상
            (p * 2 + w, p),            # ② 우상
            (p, p * 2 + h),            # ③ 좌하
            (p * 2 + w, p * 2 + h),    # ④ 우하
        ]

    # ============================================================
    # 내부: 셀 렌더링
    # ============================================================
    def _render_rgb_cell(self, rgb: Optional[np.ndarray]) -> np.ndarray:
        """① ace2 RGB 셀 — 입력 이미지를 cell 크기에 맞게 리사이즈."""
        if rgb is None:
            return self._render_placeholder("No RGB input")

        # BGR 가정. 단채널이면 BGR로 변환
        if len(rgb.shape) == 2:
            rgb = cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)

        h, w = rgb.shape[:2]
        # aspect ratio 유지하며 cell 크기에 맞추기
        resized = self._resize_keep_aspect(rgb, self.cell_w, self.cell_h)
        return resized

    def _render_depth_cell(self, depth: Optional[np.ndarray]) -> np.ndarray:
        """② Blaze-112 depth 셀 — viridis 컬러맵 적용."""
        if depth is None:
            return self._render_placeholder("No depth input")

        # uint16 mm → 8bit 정규화 (viridis)
        valid_mask = depth > 0
        if not valid_mask.any():
            return self._render_placeholder("Depth all zero")

        d_valid = depth[valid_mask]
        d_min, d_max = d_valid.min(), d_valid.max()

        # 정규화
        normalized = np.zeros_like(depth, dtype=np.uint8)
        if d_max > d_min:
            normalized[valid_mask] = (
                ((d_valid.astype(np.float32) - d_min) / (d_max - d_min)) * 255
            ).astype(np.uint8)

        # viridis 컬러맵
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_VIRIDIS)
        # 무효 픽셀은 검은색
        colored[~valid_mask] = [0, 0, 0]

        # depth 범위 텍스트 오버레이
        resized = self._resize_keep_aspect(colored, self.cell_w, self.cell_h)
        range_text = f"Range: {d_min}-{d_max} mm  Valid: {valid_mask.mean()*100:.0f}%"
        cv2.putText(
            resized, range_text, (10, resized.shape[0] - 12),
            FONT, 0.5, COLOR_TEXT, 1, cv2.LINE_AA,
        )
        return resized

    def _render_overlay_cell(
        self,
        overlay: Optional[np.ndarray],
        parts: Optional[List[PartInfo]],
    ) -> np.ndarray:
        """③ 인식 결과 오버레이 셀.

        overlay가 있으면 그대로 사용, 없으면 placeholder 표시.
        오버레이 위에 판정 배지(ACCEPT/WARN/REJECT) 추가.
        """
        if overlay is None:
            if parts:
                # 오버레이 이미지 없어도 부품 정보 있으면 간단한 안내
                img = self._render_placeholder("Click [c] to capture")
            else:
                img = self._render_placeholder("Waiting for capture...")
        else:
            img = self._resize_keep_aspect(overlay, self.cell_w, self.cell_h)

        # 판정 배지 (우상단 — CAD 오버레이 가리지 않도록)
        if parts:
            top = parts[0]
            badge = top.decision
            color = top.color
            badge_font_scale = 0.6
            badge_thickness = 1
            text_size = cv2.getTextSize(badge, FONT, badge_font_scale, badge_thickness)[0]
            box_w = text_size[0] + 12
            box_h = text_size[1] + 10
            x1 = self.cell_w - box_w - 10
            y1 = 10
            cv2.rectangle(img, (x1, y1), (x1 + box_w, y1 + box_h), color, -1)
            cv2.putText(
                img, badge, (x1 + 6, y1 + text_size[1] + 4),
                FONT, badge_font_scale, (255, 255, 255), badge_thickness, cv2.LINE_AA,
            )

        return img

    def _render_table_cell(
        self,
        parts: Optional[List[PartInfo]],
        stats: Optional[PipelineStats],
    ) -> np.ndarray:
        """④ 성능/매칭 표 셀."""
        img = np.full((self.cell_h, self.cell_w, 3), (24, 24, 24), dtype=np.uint8)

        if parts is None and stats is None:
            return self._render_placeholder("No results yet")

        y = 30
        line_h = 26

        # 섹션 1: 파이프라인 통계
        if stats is not None:
            cv2.putText(img, "Pipeline Stats", (16, y),
                        FONT, 0.6, COLOR_HEADER, 1, cv2.LINE_AA)
            y += line_h + 4

            # L2 감소율 (Input pts > 0일 때만 계산)
            if stats.n_input_points > 0 and stats.n_filtered_points >= 0:
                kept_pct = 100.0 * stats.n_filtered_points / stats.n_input_points
                filtered_line = (
                    f"Filtered  : {stats.n_filtered_points:>10,}  "
                    f"({kept_pct:>4.1f}% kept, {stats.time_l2_ms:>6.1f} ms)"
                )
            else:
                filtered_line = (
                    f"Filtered  : {stats.n_filtered_points:>10,}  "
                    f"({stats.time_l2_ms:>6.1f} ms)"
                )

            lines = [
                f"Input pts : {stats.n_input_points:>10,}",
                filtered_line,
                f"Clusters  : {stats.n_clusters:>10,}  "
                f"({stats.time_l3_ms:>6.1f} ms)",
                f"Matching  : ACCEPT {stats.n_accepted} / "
                f"WARN {stats.n_warn} / REJECT {stats.n_rejected}  "
                f"({stats.time_l4_ms:>6.1f} ms)",
                f"Total     : {stats.time_total_ms:>6.1f} ms",
            ]
            for line in lines:
                cv2.putText(img, line, (16, y),
                            FONT, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)
                y += line_h

        # 섹션 2: 매칭 결과 (top-5)
        y += 12
        if parts:
            cv2.putText(img, "Matches (top-5)", (16, y),
                        FONT, 0.6, COLOR_HEADER, 1, cv2.LINE_AA)
            y += line_h + 4

            # 컬럼 레이아웃 — 고정 x 좌표로 정렬 (mono-font 가정 없앰)
            col_x = {
                "num":  16,
                "name": 46,
                "fit":  330,
                "rmse": 410,
                "dec":  510,
            }
            # 헤더
            header_font = 0.5
            for key, label in [("num", "#"), ("name", "Part"),
                               ("fit", "Fit"), ("rmse", "RMSE(mm)"), ("dec", "Dec")]:
                cv2.putText(img, label, (col_x[key], y),
                            FONT, header_font, COLOR_HEADER, 1, cv2.LINE_AA)
            y += line_h

            row_font = 0.5
            for i, p in enumerate(parts[:5]):
                name = p.name[:22]   # 22자까지 표시
                cv2.putText(img, f"{i+1}", (col_x["num"], y),
                            FONT, row_font, COLOR_TEXT, 1, cv2.LINE_AA)
                cv2.putText(img, name, (col_x["name"], y),
                            FONT, row_font, COLOR_TEXT, 1, cv2.LINE_AA)
                cv2.putText(img, f"{p.fitness:.2f}", (col_x["fit"], y),
                            FONT, row_font, COLOR_TEXT, 1, cv2.LINE_AA)
                cv2.putText(img, f"{p.rmse_mm:.2f}", (col_x["rmse"], y),
                            FONT, row_font, COLOR_TEXT, 1, cv2.LINE_AA)
                cv2.putText(img, p.decision, (col_x["dec"], y),
                            FONT, row_font, p.color, 1, cv2.LINE_AA)
                y += line_h - 2
        else:
            cv2.putText(img, "No matches yet. Press [c] to capture.",
                        (16, y), FONT, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)

        return img

    # ============================================================
    # 내부: 유틸
    # ============================================================
    def _render_placeholder(self, text: str) -> np.ndarray:
        """빈 셀용 플레이스홀더."""
        img = np.full((self.cell_h, self.cell_w, 3), (24, 24, 24), dtype=np.uint8)
        text_size = cv2.getTextSize(text, FONT, 0.7, 1)[0]
        tx = (self.cell_w - text_size[0]) // 2
        ty = (self.cell_h + text_size[1]) // 2
        cv2.putText(img, text, (tx, ty),
                    FONT, 0.7, (128, 128, 128), 1, cv2.LINE_AA)
        return img

    def _resize_keep_aspect(
        self,
        img: np.ndarray,
        target_w: int,
        target_h: int,
    ) -> np.ndarray:
        """Aspect ratio 유지하며 target 크기에 맞추기. 남는 공간은 검은색."""
        h, w = img.shape[:2]
        scale = min(target_w / w, target_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # letterbox
        result = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        y_off = (target_h - new_h) // 2
        x_off = (target_w - new_w) // 2
        result[y_off:y_off+new_h, x_off:x_off+new_w] = resized
        return result

    def _place_cell(
        self,
        canvas: np.ndarray,
        cell_img: np.ndarray,
        pos: tuple,
        title: str,
    ) -> None:
        """캔버스에 셀 이미지 + 타이틀 바 배치."""
        x, y = pos

        # 타이틀 바
        cv2.rectangle(
            canvas,
            (x, y), (x + self.cell_w, y + self.title_h),
            COLOR_TITLE_BG, -1,
        )
        cv2.putText(
            canvas, title, (x + 12, y + self.title_h - 12),
            FONT, 0.8, COLOR_HEADER, 2, cv2.LINE_AA,
        )

        # 셀 이미지
        y_img = y + self.title_h
        canvas[y_img:y_img + self.cell_h, x:x + self.cell_w] = cell_img

        # 셀 테두리
        cv2.rectangle(
            canvas,
            (x, y), (x + self.cell_w, y + self.title_h + self.cell_h),
            COLOR_FRAME, 1,
        )

    def _render_status_bar(self, canvas: np.ndarray, text: str) -> None:
        """하단 상태바 (간단)."""
        h = canvas.shape[0]
        cv2.putText(
            canvas, text, (self.pad, h - 10),
            FONT, 0.5, COLOR_HEADER, 1, cv2.LINE_AA,
        )


# ============================================================
# 헬퍼: 파이프라인 결과 → UI 데이터 변환
# ============================================================
def parts_from_pipeline_result(result: Dict[str, Any]) -> List[PartInfo]:
    """main_pipeline.run() 결과의 parts 리스트를 PartInfo로 변환.

    rank==0 만 필터링 (각 클러스터의 top-1).
    """
    if result is None or "parts" not in result:
        return []

    parts = []
    for p in result["parts"]:
        if p.get("rank", 0) > 0:
            continue
        parts.append(PartInfo(
            name=p["name"],
            fitness=p["fitness"],
            rmse_mm=p["rmse"] * 1000.0,
            decision=p["decision"],
            cluster_id=p.get("cluster_id", 0),
            n_points=p.get("n_points", 0),
            extent_mm=tuple(p.get("extent_mm", (0, 0, 0))),
        ))

    # fitness 높은 순
    parts.sort(key=lambda x: x.fitness, reverse=True)
    return parts


def stats_from_pipeline_result(result: Dict[str, Any], input_pcd_len: int = 0) -> PipelineStats:
    """main_pipeline.run() 결과를 PipelineStats로 변환."""
    if result is None:
        return PipelineStats()

    timings = result.get("timings", {})

    # filtered PointCloud 크기 (있을 때만)
    filtered = result.get("filtered")
    n_filtered = 0
    if filtered is not None and hasattr(filtered, "points"):
        n_filtered = len(filtered.points)

    # total 시간은 timings["total"] 있으면 우선 사용, 없으면 합산
    total_ms = timings.get("total")
    if total_ms is None:
        # L2, L3, L4, L5, L6만 합산 (total 중복 제외)
        total_ms = sum(
            v for k, v in timings.items() if k in ("L2", "L3", "L4", "L5", "L6")
        )
    total_ms *= 1000.0

    # ACCEPT/WARN/REJECT 카운트 (rank==0만)
    n_accept = 0
    n_warn = 0
    n_reject = 0
    for p in result.get("parts", []):
        if p.get("rank", 0) > 0:
            continue
        d = p.get("decision", "")
        if d == "ACCEPT":
            n_accept += 1
        elif d == "WARN":
            n_warn += 1
        elif d == "REJECT":
            n_reject += 1

    return PipelineStats(
        n_input_points=input_pcd_len,
        n_filtered_points=n_filtered,
        n_clusters=result.get("n_clusters", len(result.get("clusters", []))),
        n_accepted=n_accept,
        n_warn=n_warn,
        n_rejected=n_reject,
        time_l2_ms=timings.get("L2", 0.0) * 1000.0,
        time_l3_ms=timings.get("L3", 0.0) * 1000.0,
        time_l4_ms=timings.get("L4", 0.0) * 1000.0,
        time_total_ms=total_ms,
    )
