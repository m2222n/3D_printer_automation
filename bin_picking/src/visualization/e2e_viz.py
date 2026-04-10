"""
E2E 매칭 테스트 시각화 모듈
============================
합성 씬 E2E 테스트 결과를 Open3D 오프스크린 렌더링으로 PNG 자동 저장.
대표님 요청: "안 되는 케이스에 스크린샷/이미지 첨부해서 왜 안 되는지 시각적으로 설명"

이미지 종류:
  1. overview.png — 전체 씬 오버뷰 (정답/오매칭/미검출 색상 구분)
  2. cluster_{id}_{부품}_{판정}.png — 클러스터별 매칭 상세
  3. failure_{id}_{부품}_gt_vs_matched.png — 오매칭 비교 (정답 vs 매칭)
  4. summary.txt — 텍스트 요약

사용법:
    from bin_picking.src.visualization.e2e_viz import E2EVisualizer
    viz = E2EVisualizer(output_dir="viz_output/easy_default_42")
    viz.generate_all(scene_pcd, results, clusters, ground_truth,
                     reference_cache, eval_result, metadata)
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

try:
    import open3d as o3d
    import open3d.visualization.rendering as rendering
except ImportError:
    o3d = None
    rendering = None


# 색상 팔레트 (RGB 0~1)
COLOR_SCENE = [0.7, 0.7, 0.7]       # 씬 배경: 회색
COLOR_CORRECT = [0.2, 0.8, 0.2]     # 정답 매칭: 초록
COLOR_MISMATCH = [0.9, 0.1, 0.1]    # 오매칭: 빨강
COLOR_MISSED = [0.2, 0.2, 0.9]      # 미검출 GT: 파랑
COLOR_FALSE_POS = [1.0, 0.6, 0.0]   # 오검출: 주황
COLOR_GT_REF = [0.0, 0.5, 1.0]      # GT 레퍼런스 (비교용): 시안


def _match_gt_to_clusters(
    ground_truth: List[Dict],
    results: List[Dict],
    spacing: float = 0.15,
) -> Dict[int, Optional[int]]:
    """GT 부품을 클러스터에 공간적으로 매칭.

    Returns:
        {gt_index: result_index} or {gt_index: None} if unmatched
    """
    mapping = {}
    used_results = set()
    threshold = spacing * 0.7  # spacing의 70% 이내

    for gi, gt in enumerate(ground_truth):
        gt_pos = gt["offset"]
        best_dist = float("inf")
        best_ri = None

        for ri, r in enumerate(results):
            if ri in used_results:
                continue
            cluster_center = r.get("cluster_center")
            if cluster_center is None:
                continue
            dist = np.linalg.norm(np.array(gt_pos) - np.array(cluster_center))
            if dist < best_dist and dist < threshold:
                best_dist = dist
                best_ri = ri

        mapping[gi] = best_ri
        if best_ri is not None:
            used_results.add(best_ri)

    return mapping


def _classify_results(
    ground_truth: List[Dict],
    results: List[Dict],
    gt_to_cluster: Dict[int, Optional[int]],
) -> List[Dict]:
    """각 클러스터/GT를 분류: CORRECT, MISMATCH, MISSED, FALSE_POS.

    Returns:
        list of classification dicts
    """
    classifications = []
    matched_cluster_ids = set()

    for gi, gt in enumerate(ground_truth):
        ri = gt_to_cluster.get(gi)
        gt_name = gt["name"]

        if ri is None:
            # DBSCAN이 클러스터를 못 잡음
            classifications.append({
                "type": "MISSED",
                "gt_index": gi,
                "gt_name": gt_name,
                "cluster_index": None,
                "matched_name": None,
                "gt_transform": gt["transformation"],
            })
        else:
            matched_cluster_ids.add(ri)
            r = results[ri]
            matched_name = r["matched_name"]
            decision = r["decision"]

            if decision != "ACCEPT":
                classifications.append({
                    "type": "MISSED",
                    "gt_index": gi,
                    "gt_name": gt_name,
                    "cluster_index": ri,
                    "matched_name": matched_name,
                    "gt_transform": gt["transformation"],
                    "result": r,
                })
            elif matched_name == gt_name:
                classifications.append({
                    "type": "CORRECT",
                    "gt_index": gi,
                    "gt_name": gt_name,
                    "cluster_index": ri,
                    "matched_name": matched_name,
                    "gt_transform": gt["transformation"],
                    "result": r,
                })
            else:
                classifications.append({
                    "type": "MISMATCH",
                    "gt_index": gi,
                    "gt_name": gt_name,
                    "cluster_index": ri,
                    "matched_name": matched_name,
                    "gt_transform": gt["transformation"],
                    "result": r,
                })

    # False positive: ACCEPT인데 어떤 GT와도 매칭 안 된 클러스터
    for ri, r in enumerate(results):
        if ri not in matched_cluster_ids and r["decision"] == "ACCEPT":
            classifications.append({
                "type": "FALSE_POS",
                "gt_index": None,
                "gt_name": None,
                "cluster_index": ri,
                "matched_name": r["matched_name"],
                "result": r,
            })

    return classifications


class E2EVisualizer:
    """E2E 매칭 결과 시각화 + PNG 자동 저장."""

    def __init__(self, width: int = 1280, height: int = 960,
                 output_dir: str = "viz_output"):
        if o3d is None:
            raise ImportError("Open3D가 필요합니다.")

        self.width = width
        self.height = height
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._renderer = None

    def _get_renderer(self):
        """OffscreenRenderer 생성 (lazy init)."""
        if self._renderer is None:
            try:
                self._renderer = rendering.OffscreenRenderer(self.width, self.height)
                self._renderer.scene.set_background([1.0, 1.0, 1.0, 1.0])
                # 조명
                self._renderer.scene.scene.set_sun_light(
                    [0.0, 0.0, -1.0], [1.0, 1.0, 1.0], 75000
                )
                self._renderer.scene.scene.enable_sun_light(True)
            except Exception:
                # Fallback: Visualizer 캡처
                self._renderer = "fallback"
        return self._renderer

    def _make_material(self, point_size: float = 3.0):
        """포인트 클라우드 렌더링 머티리얼."""
        mat = rendering.MaterialRecord()
        mat.shader = "defaultUnlit"
        mat.point_size = point_size
        return mat

    def _compute_overhead_camera(self, bounds_min, bounds_max, margin=1.3):
        """오버헤드 뷰 카메라 파라미터 계산."""
        center = (bounds_min + bounds_max) / 2
        extent = bounds_max - bounds_min
        fov_deg = 60.0
        fov_rad = np.radians(fov_deg)
        distance = max(extent[0], extent[1]) * margin / (2 * np.tan(fov_rad / 2))
        distance = max(distance, 0.3)  # 최소 거리

        eye = [center[0], center[1], center[2] + distance]
        target = center.tolist()
        up = [0, -1, 0]
        return fov_deg, eye, target, up

    def _render_scene_to_image(self, geometries, bounds_min=None, bounds_max=None,
                               camera_params=None):
        """지오메트리 목록을 오프스크린 렌더링하여 numpy array로 반환."""
        renderer = self._get_renderer()

        if renderer == "fallback":
            return self._render_fallback(geometries, bounds_min, bounds_max)

        # 씬 클리어
        renderer.scene.clear_geometry()

        mat = self._make_material(point_size=3.0)

        for i, (name, geom, color) in enumerate(geometries):
            g = copy.deepcopy(geom)
            if color is not None:
                g.paint_uniform_color(color)
            renderer.scene.add_geometry(f"{name}_{i}", g, mat)

        # 카메라 설정
        if camera_params:
            fov, eye, target, up = camera_params
        elif bounds_min is not None and bounds_max is not None:
            fov, eye, target, up = self._compute_overhead_camera(bounds_min, bounds_max)
        else:
            # 전체 바운딩 박스에서 추정
            all_pts = []
            for _, geom, _ in geometries:
                pts = np.asarray(geom.points)
                if len(pts) > 0:
                    all_pts.append(pts)
            if all_pts:
                all_pts = np.vstack(all_pts)
                fov, eye, target, up = self._compute_overhead_camera(
                    all_pts.min(axis=0), all_pts.max(axis=0)
                )
            else:
                return np.ones((self.height, self.width, 3), dtype=np.uint8) * 255

        renderer.setup_camera(fov, target, eye, up)

        img = renderer.render_to_image()
        return np.asarray(img)

    def _render_fallback(self, geometries, bounds_min, bounds_max):
        """Visualizer(visible=False) 방식 fallback."""
        vis = o3d.visualization.Visualizer()
        vis.create_window(visible=False, width=self.width, height=self.height)

        for _, geom, color in geometries:
            g = copy.deepcopy(geom)
            if color is not None:
                g.paint_uniform_color(color)
            vis.add_geometry(g)

        ctr = vis.get_view_control()
        if bounds_min is not None and bounds_max is not None:
            center = (bounds_min + bounds_max) / 2
            ctr.set_lookat(center.tolist())
            ctr.set_front([0, 0, 1])
            ctr.set_up([0, -1, 0])
            extent = bounds_max - bounds_min
            ctr.set_zoom(0.5)

        vis.poll_events()
        vis.update_renderer()
        img = vis.capture_screen_float_buffer(do_render=True)
        vis.destroy_window()
        return (np.asarray(img) * 255).astype(np.uint8)

    def _add_text_overlay(self, img: np.ndarray, lines: List[str],
                          position: str = "top-left",
                          font_scale: float = 0.6,
                          bg_alpha: float = 0.7) -> np.ndarray:
        """이미지에 텍스트 오버레이 추가 (OpenCV)."""
        img = img.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 1
        line_height = int(25 * font_scale / 0.6)
        padding = 10

        # 텍스트 영역 크기 계산
        max_width = 0
        for line in lines:
            (w, h), _ = cv2.getTextSize(line, font, font_scale, thickness)
            max_width = max(max_width, w)

        total_height = len(lines) * line_height + padding * 2
        total_width = max_width + padding * 2

        # 위치
        if position == "top-left":
            x0, y0 = 10, 10
        elif position == "top-right":
            x0 = img.shape[1] - total_width - 10
            y0 = 10
        elif position == "bottom-left":
            x0 = 10
            y0 = img.shape[0] - total_height - 10
        else:
            x0, y0 = 10, 10

        # 반투명 배경
        overlay = img.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + total_width, y0 + total_height),
                      (0, 0, 0), -1)
        img = cv2.addWeighted(overlay, bg_alpha, img, 1 - bg_alpha, 0)

        # 텍스트 렌더링
        for i, line in enumerate(lines):
            ty = y0 + padding + (i + 1) * line_height
            # 판정에 따른 색상
            if "CORRECT" in line:
                color = (50, 200, 50)
            elif "MISMATCH" in line:
                color = (50, 50, 230)
            elif "MISSED" in line:
                color = (230, 50, 50)
            elif "FALSE_POS" in line:
                color = (0, 150, 255)
            elif "PASS" in line:
                color = (50, 200, 50)
            elif "FAIL" in line:
                color = (50, 50, 230)
            else:
                color = (255, 255, 255)
            cv2.putText(img, line, (x0 + padding, ty), font, font_scale,
                        color, thickness, cv2.LINE_AA)
        return img

    def _save_image(self, img: np.ndarray, filename: str, text_lines: List[str] = None):
        """이미지 저장 (텍스트 오버레이 옵션)."""
        if text_lines:
            img = self._add_text_overlay(img, text_lines)

        path = self.output_dir / filename
        # Open3D 렌더링은 RGB, OpenCV는 BGR
        cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        print(f"    [저장] {path}")

    # ================================================================
    # 1. Overview 이미지
    # ================================================================
    def render_overview(
        self,
        scene_pcd: "o3d.geometry.PointCloud",
        results: List[Dict],
        clusters: List,
        ground_truth: List[Dict],
        reference_cache: Dict,
        classifications: List[Dict],
        eval_result: Dict,
        metadata: Dict,
    ):
        """전체 씬 오버뷰 렌더링."""
        print("\n  [VIZ] Overview 렌더링...")

        geometries = []

        # 씬 (회색)
        geometries.append(("scene", scene_pcd, COLOR_SCENE))

        # 분류별 레퍼런스 오버레이
        for cls in classifications:
            ri = cls.get("cluster_index")
            ctype = cls["type"]

            if ctype == "CORRECT" and ri is not None:
                r = cls["result"]
                ref_name = r["matched_name"]
                if ref_name in reference_cache and r["transformation"] is not None:
                    ref_pcd = copy.deepcopy(reference_cache[ref_name]["pcd_down"])
                    ref_pcd.transform(r["transformation"])
                    geometries.append((f"correct_{ref_name}", ref_pcd, COLOR_CORRECT))

            elif ctype == "MISMATCH" and ri is not None:
                r = cls["result"]
                ref_name = r["matched_name"]
                if ref_name in reference_cache and r["transformation"] is not None:
                    ref_pcd = copy.deepcopy(reference_cache[ref_name]["pcd_down"])
                    ref_pcd.transform(r["transformation"])
                    geometries.append((f"mismatch_{ref_name}", ref_pcd, COLOR_MISMATCH))

            elif ctype == "MISSED":
                # GT 위치에 GT 레퍼런스를 파란색으로 표시
                gt_name = cls["gt_name"]
                gt_T = cls["gt_transform"]
                if gt_name in reference_cache and gt_T is not None:
                    ref_pcd = copy.deepcopy(reference_cache[gt_name]["pcd_down"])
                    ref_pcd.transform(gt_T)
                    geometries.append((f"missed_{gt_name}", ref_pcd, COLOR_MISSED))

            elif ctype == "FALSE_POS" and ri is not None:
                r = cls["result"]
                ref_name = r["matched_name"]
                if ref_name in reference_cache and r["transformation"] is not None:
                    ref_pcd = copy.deepcopy(reference_cache[ref_name]["pcd_down"])
                    ref_pcd.transform(r["transformation"])
                    geometries.append((f"fp_{ref_name}", ref_pcd, COLOR_FALSE_POS))

        # 바운딩 박스 계산
        scene_pts = np.asarray(scene_pcd.points)
        bounds_min = scene_pts.min(axis=0)
        bounds_max = scene_pts.max(axis=0)

        img = self._render_scene_to_image(geometries, bounds_min, bounds_max)

        # 텍스트 오버레이
        diff = metadata.get("difficulty", "?")
        scen = metadata.get("scenario", "?")
        seed = metadata.get("seed", "?")
        rate = eval_result.get("recognition_rate", 0)
        n_correct = eval_result.get("n_correct", 0)
        n_gt = eval_result.get("n_gt_parts", 0)

        n_mismatch = sum(1 for c in classifications if c["type"] == "MISMATCH")
        n_missed = sum(1 for c in classifications if c["type"] == "MISSED")
        n_fp = sum(1 for c in classifications if c["type"] == "FALSE_POS")

        text = [
            f"E2E Overview: {diff} / {scen} / seed={seed}",
            f"Recognition: {n_correct}/{n_gt} ({rate:.0f}%)",
            f"RMSE: {eval_result.get('avg_rmse_mm', 0):.2f}mm",
            f"",
            f"GREEN=correct({n_correct})  RED=mismatch({n_mismatch})",
            f"BLUE=missed({n_missed})  ORANGE=false_pos({n_fp})",
        ]

        self._save_image(img, "overview.png", text)

    # ================================================================
    # 2. 클러스터별 상세 이미지
    # ================================================================
    def render_cluster_details(
        self,
        clusters: List,
        results: List[Dict],
        classifications: List[Dict],
        reference_cache: Dict,
    ):
        """각 클러스터별 매칭 상세 렌더링."""
        print("\n  [VIZ] 클러스터 상세 렌더링...")

        for cls in classifications:
            ri = cls.get("cluster_index")
            ctype = cls["type"]
            gt_name = cls.get("gt_name", "unknown")

            if ri is None:
                # MISSED (클러스터 없음) — GT 레퍼런스만 표시
                gt_T = cls.get("gt_transform")
                if gt_name in reference_cache and gt_T is not None:
                    ref_pcd = copy.deepcopy(reference_cache[gt_name]["pcd_down"])
                    ref_pcd.transform(gt_T)
                    geometries = [
                        (f"gt_{gt_name}", ref_pcd, COLOR_MISSED),
                    ]
                    pts = np.asarray(ref_pcd.points)
                    img = self._render_scene_to_image(
                        geometries, pts.min(axis=0) - 0.02, pts.max(axis=0) + 0.02
                    )
                    text = [
                        f"MISSED: {gt_name}",
                        f"DBSCAN failed to detect this part",
                        f"(blue = GT reference at GT position)",
                    ]
                    fname = f"cluster_XX_{gt_name}_MISSED.png"
                    self._save_image(img, fname, text)
                continue

            if ri >= len(clusters):
                continue

            cluster = clusters[ri]
            r = results[ri]
            matched_name = r.get("matched_name", "---")

            # 색상 결정
            if ctype == "CORRECT":
                ref_color = COLOR_CORRECT
                verdict = "CORRECT"
            elif ctype == "MISMATCH":
                ref_color = COLOR_MISMATCH
                verdict = "MISMATCH"
            elif ctype == "FALSE_POS":
                ref_color = COLOR_FALSE_POS
                verdict = "FALSE_POS"
            else:
                ref_color = COLOR_MISSED
                verdict = "MISSED"

            geometries = [
                ("cluster", cluster.pcd, COLOR_SCENE),
            ]

            # 매칭된 레퍼런스 오버레이
            if matched_name in reference_cache and r.get("transformation") is not None:
                ref_pcd = copy.deepcopy(reference_cache[matched_name]["pcd_down"])
                ref_pcd.transform(r["transformation"])
                geometries.append((f"ref_{matched_name}", ref_pcd, ref_color))

            # 카메라: 클러스터 바운딩 박스 기준 줌
            c_pts = np.asarray(cluster.pcd.points)
            margin = 0.03
            bounds_min = c_pts.min(axis=0) - margin
            bounds_max = c_pts.max(axis=0) + margin

            img = self._render_scene_to_image(geometries, bounds_min, bounds_max)

            fitness = r.get("fitness", 0)
            rmse = r.get("rmse", 0) * 1000

            text = [
                f"Cluster {ri}: {verdict}",
                f"GT: {gt_name}",
                f"Matched: {matched_name}",
                f"fitness={fitness:.4f}  RMSE={rmse:.2f}mm",
                f"pts={r.get('n_cluster_pts', 0)}",
            ]

            label = gt_name if gt_name else matched_name
            fname = f"cluster_{ri:02d}_{label}_{verdict}.png"
            self._save_image(img, fname, text)

    # ================================================================
    # 3. 실패 비교 이미지 (GT vs 매칭)
    # ================================================================
    def render_failure_comparisons(
        self,
        clusters: List,
        results: List[Dict],
        classifications: List[Dict],
        reference_cache: Dict,
    ):
        """오매칭 케이스: GT 레퍼런스 vs 매칭된 레퍼런스 비교."""
        print("\n  [VIZ] 실패 비교 렌더링...")

        mismatches = [c for c in classifications if c["type"] == "MISMATCH"]

        if not mismatches:
            print("    오매칭 없음 — 건너뛰기")
            return

        for cls in mismatches:
            ri = cls["cluster_index"]
            gt_name = cls["gt_name"]
            matched_name = cls["matched_name"]
            gt_T = cls["gt_transform"]
            r = cls["result"]
            matched_T = r["transformation"]

            if ri is None or ri >= len(clusters):
                continue

            cluster = clusters[ri]
            c_pts = np.asarray(cluster.pcd.points)
            margin = 0.03
            bounds_min = c_pts.min(axis=0) - margin
            bounds_max = c_pts.max(axis=0) + margin

            # --- 좌측: 클러스터 + GT 레퍼런스 (시안) ---
            geom_left = [("cluster", cluster.pcd, COLOR_SCENE)]
            if gt_name in reference_cache and gt_T is not None:
                gt_pcd = copy.deepcopy(reference_cache[gt_name]["pcd_down"])
                gt_pcd.transform(gt_T)
                geom_left.append((f"gt_{gt_name}", gt_pcd, COLOR_GT_REF))

            img_left = self._render_scene_to_image(geom_left, bounds_min, bounds_max)

            # --- 우측: 클러스터 + 매칭 레퍼런스 (빨강) ---
            geom_right = [("cluster", cluster.pcd, COLOR_SCENE)]
            if matched_name in reference_cache and matched_T is not None:
                matched_pcd = copy.deepcopy(reference_cache[matched_name]["pcd_down"])
                matched_pcd.transform(matched_T)
                geom_right.append((f"match_{matched_name}", matched_pcd, COLOR_MISMATCH))

            img_right = self._render_scene_to_image(geom_right, bounds_min, bounds_max)

            # 좌우 나란히 합성
            img_combined = np.hstack([img_left, img_right])

            fitness = r.get("fitness", 0)
            rmse = r.get("rmse", 0) * 1000

            text = [
                f"MISMATCH: cluster {ri}",
                f"GT: {gt_name} (cyan, left)  vs  Matched: {matched_name} (red, right)",
                f"fitness={fitness:.4f}  RMSE={rmse:.2f}mm",
            ]

            fname = f"failure_{ri:02d}_{gt_name}_vs_{matched_name}.png"
            self._save_image(img_combined, fname, text)

    # ================================================================
    # 4. 텍스트 요약
    # ================================================================
    def save_summary(
        self,
        classifications: List[Dict],
        eval_result: Dict,
        metadata: Dict,
    ):
        """텍스트 요약 파일 저장."""
        path = self.output_dir / "summary.txt"
        lines = []

        lines.append(f"E2E Matching Test Visualization Summary")
        lines.append(f"=" * 50)
        lines.append(f"Difficulty: {metadata.get('difficulty', '?')}")
        lines.append(f"Scenario:   {metadata.get('scenario', '?')}")
        lines.append(f"Seed:       {metadata.get('seed', '?')}")
        lines.append(f"")
        lines.append(f"Recognition: {eval_result.get('n_correct', 0)}/{eval_result.get('n_gt_parts', 0)} "
                      f"({eval_result.get('recognition_rate', 0):.0f}%)")
        lines.append(f"Avg RMSE:    {eval_result.get('avg_rmse_mm', 0):.2f}mm")
        lines.append(f"Max RMSE:    {eval_result.get('max_rmse_mm', 0):.2f}mm")
        lines.append(f"Avg Time:    {eval_result.get('avg_match_time', 0):.2f}s")
        lines.append(f"")
        lines.append(f"--- Classification ---")

        for cls in classifications:
            ctype = cls["type"]
            gt_name = cls.get("gt_name", "N/A")
            matched = cls.get("matched_name", "N/A")
            ri = cls.get("cluster_index", "N/A")

            if ctype == "CORRECT":
                lines.append(f"  [CORRECT]   cluster={ri}  GT={gt_name}")
            elif ctype == "MISMATCH":
                r = cls.get("result", {})
                lines.append(f"  [MISMATCH]  cluster={ri}  GT={gt_name}  "
                             f"matched={matched}  fitness={r.get('fitness', 0):.4f}  "
                             f"RMSE={r.get('rmse', 0)*1000:.2f}mm")
            elif ctype == "MISSED":
                lines.append(f"  [MISSED]    cluster={ri}  GT={gt_name}")
            elif ctype == "FALSE_POS":
                lines.append(f"  [FALSE_POS] cluster={ri}  matched={matched}")

        lines.append(f"")
        lines.append(f"--- Files ---")
        lines.append(f"  overview.png — Full scene overview")
        for cls in classifications:
            ri = cls.get("cluster_index")
            gt_name = cls.get("gt_name", "unknown")
            ctype = cls["type"]
            if ri is not None:
                lines.append(f"  cluster_{ri:02d}_{gt_name}_{ctype}.png")
            else:
                lines.append(f"  cluster_XX_{gt_name}_{ctype}.png")

        mismatches = [c for c in classifications if c["type"] == "MISMATCH"]
        for cls in mismatches:
            ri = cls["cluster_index"]
            gt_name = cls["gt_name"]
            matched = cls["matched_name"]
            lines.append(f"  failure_{ri:02d}_{gt_name}_vs_{matched}.png")

        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"    [저장] {path}")

    # ================================================================
    # 통합 실행
    # ================================================================
    def generate_all(
        self,
        scene_pcd: "o3d.geometry.PointCloud",
        results: List[Dict],
        clusters: List,
        ground_truth: List[Dict],
        reference_cache: Dict,
        eval_result: Dict,
        metadata: Dict,
    ):
        """시각화 이미지 전체 생성.

        Args:
            scene_pcd: 합성 씬 포인트 클라우드
            results: run_pipeline() 결과
            clusters: DBSCANSegmenter.segment() 결과 (Cluster 리스트)
            ground_truth: 부품별 정답 정보
            reference_cache: CADLibrary.load_all() 결과
            eval_result: evaluate_results() 결과
            metadata: {difficulty, scenario, seed}
        """
        print(f"\n{'='*60}")
        print(f"  E2E 시각화 생성 → {self.output_dir}/")
        print(f"{'='*60}")

        spacing = metadata.get("spacing", 0.15)

        # GT ↔ 클러스터 매칭
        gt_to_cluster = _match_gt_to_clusters(ground_truth, results, spacing)
        classifications = _classify_results(ground_truth, results, gt_to_cluster)

        # 분류 통계
        n_correct = sum(1 for c in classifications if c["type"] == "CORRECT")
        n_mismatch = sum(1 for c in classifications if c["type"] == "MISMATCH")
        n_missed = sum(1 for c in classifications if c["type"] == "MISSED")
        n_fp = sum(1 for c in classifications if c["type"] == "FALSE_POS")
        print(f"  분류: CORRECT={n_correct} MISMATCH={n_mismatch} "
              f"MISSED={n_missed} FALSE_POS={n_fp}")

        # 1. Overview
        self.render_overview(
            scene_pcd, results, clusters, ground_truth,
            reference_cache, classifications, eval_result, metadata,
        )

        # 2. 클러스터 상세
        self.render_cluster_details(clusters, results, classifications, reference_cache)

        # 3. 실패 비교
        self.render_failure_comparisons(clusters, results, classifications, reference_cache)

        # 4. 텍스트 요약
        self.save_summary(classifications, eval_result, metadata)

        n_images = 1 + len([c for c in classifications if c.get("cluster_index") is not None or c["type"] == "MISSED"])
        n_failures = len([c for c in classifications if c["type"] == "MISMATCH"])
        print(f"\n  완료: overview 1장 + cluster {n_images-1}장 + failure {n_failures}장")
        print(f"  경로: {self.output_dir}/")
