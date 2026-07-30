"""예측 마스크 → 회전각(angle) + 회전 edge 산출.

⭐ 왜 필요한가
--------------
로봇이 부품을 집으려면 **그리퍼를 어느 방향으로 돌릴지**를 알아야 한다. 그것이 `angle`.

7/29 6요소 출력은 `angle=0.0`으로 **고정**돼 있었다(`notes`에 `angle=0_mask_not_saved`).
0은 "회전 없음"이 아니라 **"모른다"** 는 뜻이다.

🔴 7/30 조사 결과 = **27종 중 22종(81%), 검출 건수 654/801(82%)이 종횡비 1.5 초과**
   (`tests/survey_rotation_asymmetry.py`). `top_inner_sheet` 19:1, `17_mks_holder` 11.9:1.
   각도 없이 집을 수 있는 것은 `brkt_switch`(20.4×20.0mm) **1종뿐**.
   → 각도는 "있으면 좋은 것"이 아니라 **없으면 82%를 못 집는 것**.

🚨 왜 모델이 각도를 안 주나 (KAIST 설계와의 관계)
--------------------------------------------------
`depth_track`(KAIST 자산)은 **회전 불변(rotation invariant)** 으로 설계됐다.
`model/cad_pointcloud_dataset.py:48 _random_z_rotation`이 CAD를 무작위로 돌려 학습시킨다.
목적 = "어느 방향으로 놓여 있어도 같은 부품으로 인식" → **종류 식별 F1을 올리는 설계**.

KAIST 지표(F1)에는 맞지만, **로봇에게 필요한 각도를 일부러 버린 것**이다.
그래서 모델을 재학습하지 않고 **마스크 모양에서 기하학적으로 복구**한다(모델 밖 우회로).

방식
----
`cv2.minAreaRect`로 마스크의 **최소 회전 사각형**을 구한다. 축정렬 bbox는 부품이 비스듬히
놓이면 실제보다 정사각형처럼 보여 각도를 못 준다(7/29에 `edge`가 축정렬이라 겪은 문제).

⚠️ 한계 (로봇 연결 전 알아야 할 것)
  - 이것은 **부품 겉모양의 방향**이다. 실제 파지 방향은 `grasp_database.yaml`의
    `approach_axis`·`grasp_center`와 결합해야 하며, 그 값들은 "STL bbox 추정치,
    로봇 티칭 후 실측 교정 필요"로 명시돼 있다(`grasp_database.yaml:22-23`).
  - **180° 모호성**: 길쭉한 부품의 긴 축은 θ와 θ+180°가 구분되지 않는다. 평행 그리퍼는
    보통 무관하지만(양쪽에서 물므로), **비대칭 부품의 앞뒤 구분이 필요하면 부족**하다.
  - 마스크가 깨져 있으면(ToF 구멍) 각도가 흔들린다 → `angle_confidence`로 노출한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# 이 이하 면적의 마스크는 각도를 신뢰하지 않는다.
# 근거: yolo_track/pipeline/detect_and_output.py:288이 같은 목적으로 10px을 씀.
# depth_track 마스크는 320×576 입력 기준이라 조금 크게 잡는다.
MIN_CONTOUR_AREA = 20

# 종횡비가 이 값 미만이면 "거의 정사각형"이라 각도가 물리적으로 무의미하다.
# 근거: tests/survey_rotation_asymmetry.py의 T_SQUARE와 동일 기준.
ASPECT_MEANINGFUL = 1.15


def _normalize_angle(rect: tuple) -> float:
    """cv2.minAreaRect 각도 → [0, 360) 긴 축 기준.

    ⭐ `yolo_track/pipeline/detect_and_output.py:299-307`과 **같은 규약**을 쓴다.
       두 트랙이 다른 각도 규약을 쓰면 로봇 쪽에서 혼동이 생긴다.
    """
    angle_raw = rect[2]
    w, h = rect[1]
    if w < h:            # minAreaRect는 [-90,0)을 주므로 긴 축 기준으로 보정
        angle_raw += 90.0
    return float(angle_raw % 360.0)


def angle_from_mask(
    mask: np.ndarray,
    offset_xy: Tuple[float, float] = (0.0, 0.0),
    scale_xy: Tuple[float, float] = (1.0, 1.0),
) -> Optional[Dict[str, Any]]:
    """마스크 1개 → 각도·회전 edge·품질 지표.

    Args:
        mask: bool/uint8 2D. **모델 입력 좌표계**(crop·resize된 320×576).
        offset_xy, scale_xy: 원본 depth 좌표계로 되돌리는 변환.
            ⚠️ 7/29 교훈 = 이 역변환을 빼먹으면 좌표가 141px 밀린다.
            `depth_track_to_6elements.py`가 쓰는 것과 같은 값을 넘겨야 한다.

    Returns:
        None이면 각도 산출 실패(마스크가 비었거나 너무 작음).
        `angle_reliable=False`면 값은 있으나 **로봇에 쓰기 전 검토 필요**.
    """
    if mask is None:
        return None
    m = np.asarray(mask)
    if m.ndim != 2 or m.size == 0:
        return None

    m8 = (m > 0).astype(np.uint8)
    if int(m8.sum()) == 0:
        return None

    contours, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(largest))
    if area < MIN_CONTOUR_AREA:
        return None

    rect = cv2.minAreaRect(largest)
    angle = _normalize_angle(rect)

    (cx, cy), (rw, rh), _ = rect
    long_side, short_side = max(rw, rh), min(rw, rh)
    aspect = float(long_side / max(short_side, 1e-6))

    # 회전 사각형 4점 → 원본 좌표계로 복원
    box = cv2.boxPoints(rect)
    ox, oy = offset_xy
    sx, sy = scale_xy
    edge = [[int(round(p[0] * sx + ox)), int(round(p[1] * sy + oy))] for p in box]

    # ⭐ 각도를 믿을 수 있나 = 두 가지로 판정
    #   ① 종횡비가 1.15 미만이면 거의 정사각형 → 각도가 물리적으로 무의미
    #   ② 마스크가 회전 사각형을 얼마나 채우나(fill) — ToF 구멍으로 깨진 마스크 걸러냄
    fill = area / max(long_side * short_side, 1e-6)
    reliable = bool(aspect >= ASPECT_MEANINGFUL and fill >= 0.45)

    reasons = []
    if aspect < ASPECT_MEANINGFUL:
        reasons.append(f"aspect={aspect:.2f}<{ASPECT_MEANINGFUL}(거의 정사각형=각도 무의미)")
    if fill < 0.45:
        reasons.append(f"fill={fill:.2f}<0.45(마스크 깨짐 의심)")

    return {
        "angle": round(angle, 2),
        "edge": edge,
        "angle_reliable": reliable,
        "aspect": round(aspect, 3),
        "fill": round(fill, 3),
        "obb_center_xy": [round(cx * sx + ox, 1), round(cy * sy + oy, 1)],
        "obb_size_px": [round(long_side * max(sx, sy), 1), round(short_side * max(sx, sy), 1)],
        "mask_area_px": int(m8.sum()),
        "angle_note": "; ".join(reasons) if reasons else "obb_minAreaRect",
    }


def angles_from_masks(
    masks: np.ndarray,
    offset_xy: Tuple[float, float] = (0.0, 0.0),
    scale_xy: Tuple[float, float] = (1.0, 1.0),
) -> List[Optional[Dict[str, Any]]]:
    """검출 N건의 마스크 배열 → 각도 결과 N건 (실패는 None)."""
    if masks is None:
        return []
    out = []
    for i in range(len(masks)):
        out.append(angle_from_mask(masks[i], offset_xy, scale_xy))
    return out


def summarize(results: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """진단용 집계 — 각도가 실제로 얼마나 나왔나."""
    total = len(results)
    ok = [r for r in results if r is not None]
    reliable = [r for r in ok if r["angle_reliable"]]
    return {
        "total": total,
        "angle_computed": len(ok),
        "angle_reliable": len(reliable),
        "failed": total - len(ok),
        "reliable_pct": round(100.0 * len(reliable) / max(total, 1), 1),
    }


__all__ = ["angle_from_mask", "angles_from_masks", "summarize",
           "MIN_CONTOUR_AREA", "ASPECT_MEANINGFUL"]
