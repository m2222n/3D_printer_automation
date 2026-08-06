#!/usr/bin/env python3
"""입력·출력 게이트 — 학습 분포를 벗어난 장면과 부품이 아닌 예측을 걸러낸다.

⭐⭐ 왜 필요한가 (2026-08-05 cross-session 30장 실측):

  | 조건 | F1 | 위치 P | 유효율 | 진단 |
  |---|---|---|---|---|
  | c1 빈 안·45cm | 0.4070 | 0.971 | 5.6% | 🟡 종류만 붕괴(검출 정상) |
  | c2 58cm·박스 테두리 | 0.0814 | 0.477 | 30.5% | 🟠 **박스를 부품으로 오인** |
  | c3 땅바닥 직접 | 0.0000 | 0.000 | 89.1% | 🔴 **부품 자리를 아예 안 봄** |

  c2·c3의 실패는 **인식 성능이 아니라 입력 조건** 문제다. 학습 데이터는 빈 안 촬영이라
  배경이 거의 무효(depth 0)였는데, 배경이 유효값으로 채워지면 **모델이 처음 보는 분포**가 된다.
  ⇒ **재학습이 아니라 코드로 대응할 부분**이고, 이 파일이 그것이다.

⭐ 게이트는 두 층이다:
  ① **출력 게이트(크기)** = "부품보다 훨씬 큰 예측은 부품이 아니다" — 개별 검출을 버린다
  ② **입력 게이트(유효율)** = "학습 때와 화면 구성이 다르다" — 장면 전체를 신뢰할 수 없다고 알린다

🚨 원칙 = **"조용히 틀리지 말고 크게 실패하라"**. 게이트는 값을 조용히 고치지 않고,
   **버렸다는 사실과 이유를 반드시 남긴다**(`gate` 필드 / `dropped` 목록).

⚠️ 이 파일이 하지 않는 것 = **ROI 크롭**. 빈이 화면에서 차지하는 영역이 정해져야
   좌표를 박을 수 있으므로 **빈 확정 후**에 만든다(8/5에 순서를 거꾸로 제시했다가 정정).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

# ---------------------------------------------------------------------------
# 임계값 — 전부 실측 근거가 있다 (추측값 없음)
# ---------------------------------------------------------------------------

# ⭐ 부품 최대변 상한 (px)
#
# 🚨🚨 **230px이다. 200px이 아니다.** 8/6에 200px으로 잡았다가 실측으로 정정했다:
#   200px에서 **c1(실운영) F1이 0.3882 → 0.3494로 떨어졌다** — 버려진 4건이 전부 진짜 TP였고,
#   주범은 `08_r_guide_a`(STL 실측 **271mm = 27종 중 최대 부품**)로 211~223px로 검출된다.
#   ⭐⭐ **내가 GT bbox만 보고 임계를 정한 것이 실수였다** — 예측 bbox는 마스크 기반이라
#      GT보다 크게 나온다(GT 최대 148px인데 정답 예측은 최대 223px). 판정 대상이 예측이므로
#      **예측 크기 분포로 임계를 정해야 한다.**
#
#   실측 근거(8/5 예측 231건 전수, 진짜 TP 37건 / FP 194건):
#     진짜 TP 예측 = p50 93 · p90 181 · **최대 223px**
#     FP 예측      = p50 166 · p90 475 · 최대 573px
#     임계별 = 200px→**TP 4건 손실**·FP 81 제거 / **230px→TP 0 손실·FP 77(40%) 제거** /
#              280px→TP 0·FP 58 / 400px→TP 0·FP 42
#   ⇒ **230px = TP를 하나도 잃지 않으면서 FP를 가장 많이 잡는 자리**(최대 TP 223px + 여유 7px).
#
#   효과(8/5 예측 재집계) = c2 위치 precision **0.338 → 0.512** · c1 위치 P 0.871 → 0.894,
#   **c1 F1은 떨어지지 않는다**. c3는 FP 96 → 37로 줄지만 🚨**recall이 0 그대로**다
#   = 크기 게이트로 "못 찾는 문제"는 해결되지 않는다(재학습 대상).
#
#   ⭐⭐ 좌표계 = 위 수치는 **모델 입력 좌표계**(320x576)에서 쟀고, 6요소의 `bbox_pixel`은
#      **원본 depth 좌표계**(848x480)로 역변환된 값이다. 실측 스케일 = 크롭 566x320 →
#      입력 576x320 이므로 **x 0.983 · y 1.000** = 실질 1:1이어서 같은 임계를 쓸 수 있다.
#      🚨 단 이것은 현재 center_crop(1/6,5/6)에서 성립하는 것이다. crop이 바뀌면 다시 재라.
MAX_PART_SIDE_PX = 230

# ⭐ 장면 유효 픽셀 비율(depth > 0)의 학습 분포 (원본 848x480 기준)
#   실측 = 학습세션 100장 **2.0 ~ 23.8%** (중앙값 3.1% · p99 8.8%)
#   cross-session = c1 4.3~7.5%(✅학습 분포 안) / c2 24.9~38.2%(🟠경계) / c3 80.0~94.7%(🔴이탈)
#   ⇒ 상한 25%는 **c1을 통과시키고 c2·c3를 잡는** 자리이며 학습 p99(8.8%)보다 넉넉하다.
VALID_RATIO_TRAIN_MIN = 2.0
VALID_RATIO_TRAIN_MAX = 25.0

# 경고만 낼 구간(학습 분포보다 높지만 아직 c3 수준은 아님) — 판단은 호출자에게 남긴다
VALID_RATIO_WARN = 10.0


def scene_valid_ratio_pct(depth: np.ndarray) -> float:
    """장면 유효 픽셀 비율(%) = depth가 0이 아닌 픽셀의 비율.

    ⚠️ raw uint16이든 mm float이든 "0 = 무효"라는 규약은 같으므로 단위 변환이 필요 없다.
       (단위 버그를 닷새에 다섯 번 밟았으므로, 단위에 의존하지 않는 판정만 여기 둔다.)
    """
    a = np.asarray(depth)
    if a.size == 0:
        return 0.0
    return float((a > 0).mean() * 100.0)


def check_scene(
    depth: np.ndarray,
    *,
    ratio_min: float = VALID_RATIO_TRAIN_MIN,
    ratio_max: float = VALID_RATIO_TRAIN_MAX,
    warn_at: float = VALID_RATIO_WARN,
) -> dict[str, Any]:
    """입력 게이트 = 이 장면이 학습 때와 같은 화면 구성인가.

    ⭐ 판정하지 않고 **알린다**. 장면을 버릴지는 운영 정책이므로 호출자가 정한다
       (빈피킹은 "의심되면 사람에게 알리고 멈춘다"가 맞다).

    반환:
      valid_ratio_pct : 유효 픽셀 비율(%)
      verdict         : "in_distribution" | "borderline" | "out_of_distribution"
      trusted         : verdict가 in_distribution일 때만 True
      note            : 사람이 읽을 근거
    """
    r = scene_valid_ratio_pct(depth)

    if r < ratio_min:
        verdict = "out_of_distribution"
        note = (f"유효율 {r:.1f}% < {ratio_min}% — 장면이 거의 비어 있다"
                " (카메라가 빈을 안 보거나 거리가 스펙 밖일 수 있다)")
    elif r > ratio_max:
        verdict = "out_of_distribution"
        note = (f"유효율 {r:.1f}% > {ratio_max}% — 배경이 depth로 채워졌다."
                " 학습은 빈 안 촬영이라 배경이 거의 무효였다"
                " (8/5 c3 = 89.1%에서 TP 0/FP 96으로 완전 실패)")
    elif r > warn_at:
        verdict = "borderline"
        note = (f"유효율 {r:.1f}%가 학습 p99({warn_at}%)를 넘는다 — 빈 밖 물체가"
                " 화면에 들어왔을 수 있다 (8/5 c2 = 30.5%에서 박스를 부품으로 오인)")
    else:
        verdict = "in_distribution"
        note = f"유효율 {r:.1f}% — 학습 분포({ratio_min}~{warn_at}%) 안"

    return {
        "valid_ratio_pct": round(r, 2),
        "verdict": verdict,
        "trusted": verdict == "in_distribution",
        "note": note,
        "thresholds": {"min": ratio_min, "warn": warn_at, "max": ratio_max},
    }


def detection_max_side_px(det: dict) -> Optional[float]:
    """검출 1건의 최대변(px). 판정할 근거가 없으면 None.

    ⭐ 6요소 출력의 실제 키는 `bbox_pixel: {w, h, x1, y1, x2, y2, cx, cy}`다
       (`depth_track_to_6elements.py:270`). ⚠️**키 이름은 추측하지 말고 파일을 열어 확인했다**
       — 7/31 `predictions`/`detections` 오독, 8/4 `camera_3d` dict 오독으로 두 번 밟은 유형이다.
    ⚠️ `edge`(4코너)로도 계산할 수 있으나 회전 OBB라 축정렬 최대변과 다르다.
       크기 게이트는 "화면에서 얼마나 큰가"를 보는 것이므로 `bbox_pixel`이 맞다.
    """
    bp = det.get("bbox_pixel")
    if isinstance(bp, dict):
        w, h = bp.get("w"), bp.get("h")
        if w is not None and h is not None:
            return float(max(float(w), float(h)))
        x1, y1, x2, y2 = bp.get("x1"), bp.get("y1"), bp.get("x2"), bp.get("y2")
        if None not in (x1, y1, x2, y2):
            return float(max(float(x2) - float(x1), float(y2) - float(y1)))

    # 폴백 = edge(4코너)의 축정렬 외접 크기
    edge = det.get("edge")
    if isinstance(edge, (list, tuple)) and len(edge) == 4:
        try:
            xs = [float(p[0]) for p in edge]
            ys = [float(p[1]) for p in edge]
            return float(max(max(xs) - min(xs), max(ys) - min(ys)))
        except (TypeError, IndexError, ValueError):
            return None
    return None


def filter_detections(
    detections: list[dict],
    *,
    max_side_px: float = MAX_PART_SIDE_PX,
) -> tuple[list[dict], list[dict]]:
    """출력 게이트 = 부품보다 훨씬 큰 예측을 버린다.

    ⭐ 근거 = 학습 GT 최대변 166px · cross-session GT 최대 148px → 200px 초과는 부품이 아니다.
    🚨 버린 것을 **조용히 없애지 않고** 이유와 함께 돌려준다(호출자가 로그로 남길 수 있게).

    반환: (통과한 검출, 버려진 검출[reason 포함])

    ⚠️ 크기를 못 구한 검출은 **버리지 않고 통과**시킨다 — 판정 근거가 없을 때 임의로 버리면
       정상 검출을 잃는다. 대신 `gate.size_checked=False`로 판정 못 했음을 남긴다.
    """
    kept: list[dict] = []
    dropped: list[dict] = []

    for det in detections:
        side = detection_max_side_px(det)
        if side is None:
            d = dict(det)
            d["gate"] = {"size_checked": False,
                         "note": "bbox_pixel·edge 둘 다 없음 — 크기 판정 불가, 통과시킴"}
            kept.append(d)
            continue

        if side > max_side_px:
            d = dict(det)
            d["gate"] = {
                "size_checked": True,
                "dropped": True,
                "max_side_px": round(side, 1),
                "reason": (f"최대변 {side:.0f}px > {max_side_px}px — 부품이 아니다"
                           f" (학습 GT 최대 166px · cross-session GT 최대 148px)"),
            }
            dropped.append(d)
        else:
            d = dict(det)
            d["gate"] = {"size_checked": True, "dropped": False,
                         "max_side_px": round(side, 1)}
            kept.append(d)

    return kept, dropped


def apply(
    six: dict,
    depth: Optional[np.ndarray] = None,
    *,
    max_side_px: float = MAX_PART_SIDE_PX,
    drop_untrusted_scene: bool = False,
) -> dict:
    """6요소 결과에 게이트를 적용한다. **원본을 바꾸지 않고 새 dict를 돌려준다.**

    ⭐ 기본값 `drop_untrusted_scene=False` = 장면이 분포를 벗어나도 **검출을 버리지 않고
       표시만 한다**. 빈피킹 운영에서 "의심되면 멈춘다"는 정책은 상위(소켓 서버·운영 코드)가
       정할 일이고, 여기서 조용히 결정하면 원인이 안 보인다.
       🚨 `True`로 주면 검출을 전부 비우고 `gate_scene`에 이유를 남긴다.

    추가되는 필드:
      gate_scene   : check_scene() 결과 (depth를 준 경우)
      gate_dropped : 크기 게이트로 버려진 검출 목록
      detections   : 통과한 검출만 (각 건에 `gate` 필드)
    """
    out = dict(six)
    dets = list(six.get("detections", []))

    kept, dropped = filter_detections(dets, max_side_px=max_side_px)

    scene: Optional[dict] = None
    if depth is not None:
        scene = check_scene(depth)
        out["gate_scene"] = scene
        if drop_untrusted_scene and not scene["trusted"]:
            for d in kept:
                d.setdefault("gate", {})["dropped"] = True
                d["gate"]["reason"] = f"장면 게이트: {scene['note']}"
            dropped = dropped + kept
            kept = []

    out["detections"] = kept
    out["gate_dropped"] = dropped
    out["gate_summary"] = {
        "n_in": len(dets),
        "n_kept": len(kept),
        "n_dropped": len(dropped),
        "max_side_px": max_side_px,
        "scene_verdict": scene["verdict"] if scene else "not_checked",
    }
    return out


__all__ = [
    "MAX_PART_SIDE_PX",
    "VALID_RATIO_TRAIN_MIN",
    "VALID_RATIO_TRAIN_MAX",
    "VALID_RATIO_WARN",
    "scene_valid_ratio_pct",
    "check_scene",
    "filter_detections",
    "apply",
]
