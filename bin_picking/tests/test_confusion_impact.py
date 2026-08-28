#!/usr/bin/env python3
"""`analyze_confusion_impact` 검증. (2026-08-07)

⭐ 이 테스트가 지키는 것
-----------------------
1. **판정 방향** — 벌림이 모자라면 치명, 남으면 헐거움. 8/5에 방향을 안 보고
   "다르면 실패"로 세어 과대평가한 적이 있다.
2. 🚨 **분모** — 파싱이 한 줄이라도 조용히 빠지면 모든 비율이 틀어진다.
   8/7에 정규식이 빈 라벨(`gt=`) 줄을 건너뛰어 68→67로 줄었다.
   **"코드가 도는가"와 "맞게 세는가"는 다른 질문**이라 대조 검사를 넣는다.
3. **실측 재현** — 기록된 c1 종류 정답률 **48.5%** 가 그대로 나와야 한다.
   숫자가 재현되지 않으면 이 도구의 결론 전체를 믿을 수 없다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bin_picking" / "tests"))

from analyze_confusion_impact import (  # noqa: E402
    ConfusionImpactError,
    PAIR_RE,
    SAFETY_MARGIN_MM,
    VERDICT_FATAL,
    VERDICT_LOOSE,
    VERDICT_OK,
    VERDICT_UNKNOWN,
    analyze,
    judge,
    parse_pairs,
    width_of,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


DB = {
    "defaults": {"gripper_width_mm": 40.0, "gripper_force_N": 30.0},
    "parts": {
        "wide": {"gripper_width_mm": 60.0},
        "narrow": {"gripper_width_mm": 20.0},
        "similar": {"gripper_width_mm": 61.0},
        "no_width": {},
    },
}


def scene(fname: str, pairs: str, tp: int) -> dict:
    return {"file": fname, "spatial_pairs": pairs, "spatial_tp_ignore_label": tp}


def main() -> int:
    print("=" * 66)
    print(" [1] 판정 방향 — 모자라면 치명, 남으면 헐거움")
    print("=" * 66)
    check("벌림 부족 → 치명", judge(used=20.0, need=60.0) == VERDICT_FATAL)
    check("벌림 과다 → 헐거움", judge(used=60.0, need=20.0) == VERDICT_LOOSE)
    check("근소한 차이 → 무해", judge(used=60.0, need=61.0) == VERDICT_OK)
    check("경계(정확히 tight) → 무해",
          judge(used=58.0, need=60.0, tight=2.0) == VERDICT_OK)
    check("경계 바로 아래 → 치명",
          judge(used=57.9, need=60.0, tight=2.0) == VERDICT_FATAL)
    # 🚨 판정 못 하는 것을 무해로 세면 지표가 부풀려진다.
    check("used 없음 → 판정 불가", judge(None, 60.0) == VERDICT_UNKNOWN)
    check("need 없음 → 판정 불가", judge(60.0, None) == VERDICT_UNKNOWN)

    print()
    print("=" * 66)
    print(" [2] 벌림 조회 — 빈 라벨·미등재는 None")
    print("=" * 66)
    check("정상 조회", width_of(DB, "wide") == 60.0)
    check("빈 라벨 → None", width_of(DB, "") is None)
    check("미등재 → None", width_of(DB, "없는부품") is None)
    check("width 없으면 defaults", width_of(DB, "no_width") == 40.0)

    print()
    print("=" * 66)
    print(" [3] 🚨 파싱 — 빈 라벨 줄을 건너뛰지 않는다 (8/7 실제 버그)")
    print("=" * 66)
    raw_empty = ("pred=wide|gt=wide|iou=0.9|ok=1; "
                 "pred=narrow|gt=|iou=0.8|ok=0")
    m = list(PAIR_RE.finditer(raw_empty))
    check("빈 gt 줄도 잡힌다 (2건)", len(m) == 2, f"실제 {len(m)}건")

    metrics = {"per_scene": [scene("a_c1.npy", raw_empty, 2)]}
    pairs = parse_pairs(metrics, "c1")
    check("parse_pairs가 2건 반환", len(pairs) == 2, f"실제 {len(pairs)}건")
    check("빈 gt가 보존된다", any(p["gt"] == "" for p in pairs))

    # 대조 검사가 실제로 걸리는지 — 집계 필드와 다르면 중단해야 한다.
    bad = {"per_scene": [scene("a_c1.npy", raw_empty, 3)]}
    try:
        parse_pairs(bad, "c1")
        check("건수 불일치 시 예외", False, "예외가 안 났다")
    except ConfusionImpactError:
        check("건수 불일치 시 예외", True)

    print()
    print("=" * 66)
    print(" [4] 집계 — 빈 라벨은 unknown이지 무해가 아니다")
    print("=" * 66)
    res = analyze(pairs, DB)
    check("총 매칭 2건", res["total_matched"] == 2)
    check("빈 라벨은 unknown", res["verdicts"][VERDICT_UNKNOWN] == 1,
          str(res["verdicts"]))
    # ⭐ unknown은 파지 가능에서 빼야 한다(근거 없이 낙관 금지).
    check("unknown은 파지가능에서 제외", res["graspable"] == 1,
          f"graspable={res['graspable']}")

    raw_mix = ("pred=narrow|gt=wide|iou=0.9|ok=0; "   # 20 < 60 → 치명
               "pred=wide|gt=narrow|iou=0.9|ok=0; "   # 60 > 20 → 헐거움
               "pred=similar|gt=wide|iou=0.9|ok=0; "  # 61 vs 60 → 무해
               "pred=wide|gt=wide|iou=0.9|ok=1")      # 정답
    mixed = parse_pairs({"per_scene": [scene("b_c1.npy", raw_mix, 4)]}, "c1")
    r2 = analyze(mixed, DB)
    check("치명 1건", r2["verdicts"][VERDICT_FATAL] == 1, str(r2["verdicts"]))
    check("헐거움 1건", r2["verdicts"][VERDICT_LOOSE] == 1)
    check("무해 2건", r2["verdicts"][VERDICT_OK] == 2)
    check("종류 정답률 25%", abs(r2["label_acc"] - 0.25) < 1e-9)
    # 치명 1건만 실패 → 3/4
    check("파지 가능률 75%", abs(r2["graspable_rate"] - 0.75) < 1e-9,
          str(r2["graspable_rate"]))
    check("치명쌍이 보고된다",
          r2["fatal_pairs"] and r2["fatal_pairs"][0]["gt"] == "wide")

    print()
    print("=" * 66)
    print(" [5] ⭐ 실측 재현 — 기록된 c1 종류 정답률 48.5%")
    print("=" * 66)
    real = Path("/data/jtm/synth_out/reports/"
                "crosssession_30shot_eval_0805/eval_real_metrics.json")
    if not real.exists():
        print("  ⏭️  실측 파일 없음 — 건너뜀 (6000 외 환경)")
    else:
        import yaml
        db_path = REPO / "bin_picking" / "config" / "grasp_database.yaml"
        real_db = yaml.safe_load(db_path.read_text(encoding="utf-8"))
        met = json.loads(real.read_text(encoding="utf-8"))
        rp = parse_pairs(met, "c1")
        # 🚨 기록된 48.5%/83.8%는 **여유 0mm**로 잰 값이다 — 여유를 명시하지 않으면
        #   운영 기본값(10mm)이 들어와 재현 검사가 다른 것을 재게 된다.
        rr = analyze(rp, real_db, safety_margin=0.0)
        # 8/5 기록: 종류 48.5%
        check("c1 종류 정답률 = 48.5%",
              abs(rr["label_acc"] - 0.485) < 0.003,
              f"실제 {rr['label_acc']*100:.1f}%")
        # 분모가 집계 필드와 같아야 한다
        exp = sum(s["spatial_tp_ignore_label"] for s in met["per_scene"]
                  if s["file"].endswith("_c1.npy"))
        check(f"분모 = spatial_tp 합({exp})", rr["total_matched"] == exp,
              f"실제 {rr['total_matched']}")
        # ⭐ 핵심 주장 — 파지 가능률이 종류 정답률보다 크게 높다
        check("파지 가능률 > 종류 정답률 + 15%p",
              rr["graspable_rate"] > rr["label_acc"] + 0.15,
              f"파지 {rr['graspable_rate']*100:.1f}% vs 종류 {rr['label_acc']*100:.1f}%")

    print()
    print("=" * 66)
    print(" [6] 🚨🚨 안전여유 — 운영값과 어긋나면 없는 차이로 모델을 고른다 (8/27 사고)")
    print("=" * 66)
    # 🚨 이 검사가 없어서 8/27까지 드러나지 않았다:
    #   도구는 여유 0으로 재고 운영(grasp_plan.py)은 10으로 돌고 있었고,
    #   그 상태로 "치명 10건 vs 5건"이라며 후보 모델을 갈랐다.
    #   운영 조건으로 재면 양쪽 다 치명 0건 = **없는 차이였다.**
    from bin_picking.src.communication.grasp_plan import GRASP_SAFETY_MARGIN_MM
    check("도구 기본 여유 == 운영 grasp_plan 값",
          abs(SAFETY_MARGIN_MM - GRASP_SAFETY_MARGIN_MM) < 1e-9,
          f"도구 {SAFETY_MARGIN_MM} vs 운영 {GRASP_SAFETY_MARGIN_MM}")

    # ⭐ 여유가 실제로 판정을 움직이는지 — 움직이지 않으면 인자가 죽은 것이다.
    #   `narrow`(20) → `wide`(60)는 40mm 부족이라 여유 45mm면 치명이 사라져야 한다.
    tight_case = parse_pairs(
        {"per_scene": [scene("m_c1.npy", "pred=narrow|gt=wide|iou=0.9|ok=0", 1)]},
        "c1")
    r_m0 = analyze(tight_case, DB, safety_margin=0.0)
    r_m45 = analyze(tight_case, DB, safety_margin=45.0)
    check("여유 0mm → 치명 1건", r_m0["verdicts"][VERDICT_FATAL] == 1,
          str(r_m0["verdicts"]))
    check("⭐여유 45mm → 치명 0건 (여유가 판정을 움직인다)",
          r_m45["verdicts"][VERDICT_FATAL] == 0, str(r_m45["verdicts"]))

    # 🚨 여유는 used에만 더한다 — need에도 더하면 동어반복이라 판정이 안 바뀐다(8/10 함정).
    #   라벨이 맞은 건은 여유만큼 헐거워져야 한다(로봇은 맞았는지 모르고 벌린다).
    ok_case = parse_pairs(
        {"per_scene": [scene("k_c1.npy", "pred=wide|gt=wide|iou=0.9|ok=1", 1)]},
        "c1")
    check("라벨 정답 + 여유 0 → 무해",
          analyze(ok_case, DB, safety_margin=0.0)["verdicts"][VERDICT_OK] == 1)
    check("⭐라벨 정답 + 여유 20 → 헐거움(동어반복이 아니다)",
          analyze(ok_case, DB, safety_margin=20.0)["verdicts"][VERDICT_LOOSE] == 1,
          str(analyze(ok_case, DB, safety_margin=20.0)["verdicts"]))

    print()
    print("=" * 66)
    print(f"결과: {PASS} 통과 / {FAIL} 실패")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
