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

from pathlib import Path
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

# ---------------------------------------------------------------------------
# ⭐⭐ 공정 대상 화이트리스트 (2026-08-21 신설) — "빈에 없는 부품 이름"을 버린다
# ---------------------------------------------------------------------------
#
# 🎯 근거 = **모델은 27종을 학습했지만 빈에는 21종만 들어온다**(8/14 제외 6종 확정).
#    제외 6종으로 나온 예측은 **GT에 존재할 수 없으므로 100% 오답**이다.
#
#    ✅ 8/18 90장 실측으로 확인(8/21):
#      - GT 630개에 제외 6종이 **0건** — "빈에 물리적으로 안 넣는다"가 라벨로 증명됨
#      - 예측 527건 중 **22건(4.2%)** 이 제외종 = 전부 FP
#      - 효과(thr 0.45) = FP 212 → 190, **F1 0.5445 → 0.5551** (P 0.598→0.624)
#      - ⭐ 치명 오인 23건 중 **6건(26%)** 이 여기서 사라진다
#        (`brkt_switch→11_sw_block` 5건 · `18_button_function_niro→main_body` 1건)
#
# 🚨🚨 recall은 오르지 않는다 — 평가기 TP는 **라벨이 일치해야** 성립하므로
#    (`eval_real_depth_vq_detector.py:281` `g["label"] != p["label"]` → continue)
#    이름이 틀린 예측은 애초에 TP가 아니었다. ⇒ **이 게이트는 precision 전용**이다.
#    📌 *"5건이 정답으로 돌아온다"* 는 표현은 틀리다. **오답이 사라지는 것**이고,
#       로봇 입장에서는 **"없는 부품을 집으러 가지 않는다"** 가 진짜 이득이다.
#
# 🚨 되돌릴 수 있게 만든 이유 = 이 게이트는 **"제외 6종이 빈에 없다"에 전부 의존**한다.
#    사출 전환이 미뤄져 하나라도 빈에 들어오면 **그 부품을 영구히 못 찾는다**
#    = 8/14 표의 **B 함정**(빈엔 있는데 학습만 뺌 → 다른 부품으로 오인)으로 되돌아간다.
#    ⇒ **DB의 `pickability`에서 읽어** 사람이 yaml 한 줄로 되돌릴 수 있게 했다.
#    ⭐ 8/6 원칙과 같은 방식 = *"사람 결정을 코드에 박되 사유와 함께"*.
#
# ⚠️ 하지 않는 것 = **not_pickable을 파지 계획에서 거부하는 것**. 그건 별건이다
#    (8/20 발견 = `pickability`를 `src/` 어디서도 읽지 않는다). 여기서는
#    **"인식 결과에서 버릴지"** 만 다루고, 파지 거부는 `grasp_plan` 쪽 결정으로 남긴다.

# 공정 대상에서 제외된 부품 = 빈에 물리적으로 넣지 않는다 (8/14 확정)
#
# ⭐⭐ **DB(`grasp_database.yaml`의 `pickability`)에서 읽는다 — 여기에 목록을 박지 않는다.**
#    🚨 이유 = 8/20에 *"주석은 정확히 옳았는데 코드가 그 필드를 안 읽어 8/19까지
#       아무도 대조하지 않은"* 사고를 겪었다([[deprecated-design-must-be-marked]]).
#       목록을 두 곳에 두면 **반드시 갈라진다.** DB가 유일한 정본이다.
#    ⇒ 되돌리는 방법 = **yaml에서 `pickability`를 `pickable`로 바꾸면 끝**(재배포 불필요).
#
# ⚠️ 아래 폴백은 **DB를 못 읽을 때만** 쓴다. 폴백이 조용히 쓰이면 위험하므로
#    `excluded_parts_source()`가 어디서 읽었는지를 반드시 알린다.
_FALLBACK_EXCLUDED: frozenset[str] = frozenset({
    "11_sw_block",        # 무는 변 7.1mm — 너무 작다 (태민님 실물 확인 8/14)
    "17_mks_holder",      # 무는 변 82.5mm — 스트로크 85mm에 여유 2.5mm뿐 (8/14)
    "bracket_sensor2",    # 높이 2.5mm (계산 8/6)
    "bracket_case",       # 높이 4.8mm (계산 8/6)
    "main_body",          # 높이 6.0mm (계산은 경계선이나 사람이 제외 확정, 8/6)
    "top_inner_sheet",    # 높이 1.0mm (계산 8/6)
})

_GRASP_DB_PATH = Path(__file__).resolve().parents[2] / "config" / "grasp_database.yaml"


def load_excluded_parts(db_path: Optional[Path] = None) -> tuple[frozenset[str], str]:
    """공정 제외 부품 집합을 DB에서 읽는다. 반환 = (집합, 출처 문자열).

    ⭐ 출처를 함께 돌려주는 이유 = 폴백이 조용히 쓰이면 목록이 낡아도 모른다.
       호출자가 `gate_summary`에 남길 수 있게 한다("조용히 틀리지 말고 크게 실패하라").
    """
    p = Path(db_path) if db_path is not None else _GRASP_DB_PATH
    try:
        import yaml  # 지연 import — 이 모듈의 다른 기능은 yaml이 없어도 동작해야 한다
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        parts = raw.get("parts", raw) if isinstance(raw, dict) else {}
        got = {k for k, v in parts.items()
               if isinstance(v, dict) and v.get("pickability") == "not_pickable"}
        if not got:
            return _FALLBACK_EXCLUDED, f"fallback(DB에 not_pickable 0건: {p})"
        return frozenset(got), f"db({p})"
    except Exception as exc:  # 파일 없음·yaml 없음·파싱 실패
        return _FALLBACK_EXCLUDED, f"fallback({type(exc).__name__}: {exc})"


PROCESS_EXCLUDED_PARTS, PROCESS_EXCLUDED_SOURCE = load_excluded_parts()

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


def detection_part_name(det: dict) -> Optional[str]:
    """검출 1건의 부품 이름. 판정할 근거가 없으면 None.

    ⭐ 6요소의 `label`은 `cad_id`에서 해시를 뗀 것(`depth_track_to_6elements.py:163`).
       `cad_id`만 있는 원본 예측도 받을 수 있게 둘 다 본다.
    ⚠️ `class_N` 같은 폴백 라벨은 부품 이름이 아니므로 None으로 본다(판정 불가 → 통과).
    """
    for key in ("label", "cad_id"):
        v = det.get(key)
        if v:
            name = str(v).split("__")[0]
            if name and not name.startswith("class_") and name != "unknown":
                return name
    return None


def filter_excluded_parts(
    detections: list[dict],
    *,
    excluded: Optional[frozenset[str]] = None,
) -> tuple[list[dict], list[dict]]:
    """공정 화이트리스트 게이트 = **빈에 없는 부품 이름으로 나온 예측을 버린다.**

    🚨 이 게이트는 **precision 전용**이다 — 평가기 TP는 라벨이 일치해야 성립하므로
       이름이 틀린 예측은 애초에 TP가 아니었다. recall은 변하지 않는다.
       ⭐ 진짜 이득은 F1이 아니라 **로봇이 없는 부품을 집으러 가지 않는 것**이다.

    반환: (통과, 버려진 것[gate에 이유 포함])

    ⚠️ 이름을 못 구한 검출은 **버리지 않고 통과**시킨다(크기 게이트와 같은 원칙 —
       판정 근거가 없을 때 임의로 버리면 정상 검출을 잃는다).
    """
    excl = PROCESS_EXCLUDED_PARTS if excluded is None else excluded
    kept: list[dict] = []
    dropped: list[dict] = []

    for det in detections:
        name = detection_part_name(det)
        d = dict(det)
        g = dict(d.get("gate") or {})
        if name is None:
            g["part_checked"] = False
            g["note"] = "label·cad_id 둘 다 없음 — 공정 대상 판정 불가, 통과시킴"
            d["gate"] = g
            kept.append(d)
            continue

        g["part_checked"] = True
        if name in excl:
            g["dropped"] = True
            g["excluded_part"] = name
            g["reason"] = (
                f"'{name}'은 공정 제외 6종 — 빈에 물리적으로 넣지 않는 부품이므로"
                " 이 예측은 오답이다 (8/14 확정 · 8/18 90장 GT에 0건으로 확인)"
            )
            d["gate"] = g
            dropped.append(d)
        else:
            d["gate"] = g
            kept.append(d)

    return kept, dropped


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
    drop_excluded_parts: bool = True,
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

    # ⭐ 공정 화이트리스트는 **크기 게이트 다음**에 적용한다 — 순서가 결과를 바꾸지는
    #    않지만(두 조건은 독립), `gate_dropped`에서 "왜 버려졌나"가 한 건에 하나로
    #    남아야 원인 추적이 된다. 크기로 이미 버린 것은 여기서 다시 보지 않는다.
    n_excluded = 0
    if drop_excluded_parts:
        kept, excl_dropped = filter_excluded_parts(kept)
        n_excluded = len(excl_dropped)
        dropped = dropped + excl_dropped

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
        # ⭐ 화이트리스트가 켜졌는지·몇 건 버렸는지·목록을 **어디서 읽었는지**를 남긴다.
        #   🚨 출처를 안 남기면 폴백이 쓰여 목록이 낡아도 알 수 없다(8/20 교훈).
        "excluded_parts_dropped": n_excluded,
        "excluded_parts_enabled": drop_excluded_parts,
        "excluded_parts_source": PROCESS_EXCLUDED_SOURCE if drop_excluded_parts else "disabled",
    }
    return out


__all__ = [
    "MAX_PART_SIDE_PX",
    "PROCESS_EXCLUDED_PARTS",
    "PROCESS_EXCLUDED_SOURCE",
    "load_excluded_parts",
    "detection_part_name",
    "filter_excluded_parts",
    "VALID_RATIO_TRAIN_MIN",
    "VALID_RATIO_TRAIN_MAX",
    "VALID_RATIO_WARN",
    "scene_valid_ratio_pct",
    "check_scene",
    "filter_detections",
    "apply",
]
