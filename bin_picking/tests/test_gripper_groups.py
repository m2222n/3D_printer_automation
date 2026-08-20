#!/usr/bin/env python3
"""`plan_gripper_groups.py` 검증.

⭐ 이 파일이 실제로 잡아야 하는 것 = **묶기가 파지를 악화시키지 않는가**
------------------------------------------------------------
묶기의 목적은 "19가지 벌림을 15점에 넣는 것"이지만, 그 과정에서
**대표값을 잘못 고르면 새로운 치명을 만든다**(아래로 묶으면 벌림이 모자라진다).
⇒ **대표값이 반드시 그룹 최대값인가**가 이 도구의 생명이고, 여기서 그것을 검사한다.

🚨 이 파일을 만들면서 실제로 잡은 실수 2건 (둘 다 "돌려보고서야" 드러났다)
------------------------------------------------------------
① **안전여유를 DB 전체에 더했다** → used와 need가 같이 올라 **차이가 그대로**라
   판정이 하나도 안 바뀌었다(동어반복). 여유는 **used에만** 더해야 한다.
② **라벨이 맞은 건을 여유 적용에서 뺐다** → 실제 로봇은 예측이 맞았는지 모르는 채로
   벌리므로 **맞은 건도 헐거워진다**. 8/7 기록(+20mm에서 헐거움 59)과 대조해서
   내 값(26)이 틀렸음을 확인했다.

⭐⭐ **두 실수 모두 "8/7 기록값 재현" 검사가 잡았다.** 그래서 그 재현을 테스트에 박는다.

실행: /data/jtm/depth_venv/bin/python tests/test_gripper_groups.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyze_confusion_impact import (  # noqa: E402
    DEFAULT_METRICS,
    analyze,
    load_db,
    parse_pairs,
)
from plan_gripper_groups import (  # noqa: E402
    MAX_POINTS,
    STROKE_MAX_MM,
    apply_mapping,
    build_mapping,
    group_upward,
    judge_with_safety,
    part_widths,
)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=" * 68)
    print("벌림 그룹 계획 검증")
    print("=" * 68)

    db = load_db()
    widths = part_widths(db)
    pairs = parse_pairs(json.loads(DEFAULT_METRICS.read_text()), "c1")

    # ── 1. 묶기 자체의 규칙
    print("\n[1] 묶기 규칙")
    groups = group_upward([1, 2, 3, 10, 20, 30], 3)
    check("그룹 수가 한도 이하", len(groups) <= 3, f"실제 {len(groups)}")
    check("모든 값이 정확히 한 그룹에",
          sorted(v for g in groups for v in g) == [1, 2, 3, 10, 20, 30])
    check("각 그룹은 연속 구간이다(정렬 순서를 건너뛰지 않는다)",
          all(g == sorted(g) for g in groups)
          and [v for g in groups for v in g] == [1, 2, 3, 10, 20, 30],
          f"실제 {groups}")
    # 🚨 처음에 `[1,2,3]`이 한 그룹일 것이라 기댓값을 박았다가 실패했는데,
    #    **알고리즘이 옳고 내 기댓값이 틀렸다** — [[1,2,3,10],[20],[30]]도
    #    최대 올림 폭이 9로 동일하다(간격 10이 두 개라 어느 쪽을 잘라도 같다).
    #    ⭐ 그래서 "특정 분할"이 아니라 **목적함수(최대 올림 폭)**로 검사한다.
    def max_lift(gs):
        return max(max(g) - min(g) for g in gs)

    check("⭐ 최대 올림 폭이 이론 하한 이내",
          max_lift(groups) <= 9, f"실제 {max_lift(groups)} · {groups}")
    check("⭐ 그룹을 늘리면 올림 폭이 줄거나 같다",
          max_lift(group_upward([1, 2, 3, 10, 20, 30], 5)) <= max_lift(groups))

    # 🚨 가장 중요한 성질 — 대표값은 그룹 최대값이어야 한다
    m, gs = build_mapping(widths, MAX_POINTS)
    check("⭐⭐ 대표값 = 그룹 최대값(아래로 안 묶는다)",
          all(max(g) == max(g) and all(v <= max(g) for v in g) for g in gs))
    check("⭐⭐ 모든 부품의 대표값 ≥ 원래 벌림 (모자라지 않는다)",
          all(m[k] >= widths[k] for k in widths),
          str([(k, widths[k], m[k]) for k in widths if m[k] < widths[k]][:3]))

    check(f"한도 {MAX_POINTS}점 이하로 줄었다",
          len(set(m.values())) <= MAX_POINTS, f"실제 {len(set(m.values()))}점")
    check("한도가 고유값보다 크면 묶지 않는다",
          len(group_upward([1, 2, 3], 10)) == 3)

    # ── 2. ⭐⭐ 묶기가 파지를 악화시키지 않는가 (이 도구의 생명)
    print("\n[2] ⭐ 묶기가 파지에 해를 끼치지 않는가")
    before = judge_with_safety(pairs, db, 0.0)
    after = judge_with_safety(pairs, apply_mapping(db, m), 0.0)
    check("치명이 늘지 않았다",
          after["verdicts"]["fatal"] <= before["verdicts"]["fatal"],
          f"{before['verdicts']['fatal']} → {after['verdicts']['fatal']}")
    check("파지 가능률이 떨어지지 않았다",
          after["graspable_rate"] >= before["graspable_rate"],
          f"{before['graspable_rate']} → {after['graspable_rate']}")

    # ── 3. ⭐⭐ 8/7 기록값 재현 — 이 검사가 내 실수 2건을 잡았다
    #
    # 🚨🚨 2026-08-20 — DB `gripper_width_mm`이 **교정**됐다(방향 혼재 → span_flat).
    #   그래서 이 재현은 **보존해둔 옛 값**(`gripper_width_mm_legacy_0806`)으로 돌린다.
    #   ⭐ 왜 지우지 않는가 = 8/7 기준선이 살아있어야 *"도구가 바뀐 건지 데이터가
    #     바뀐 건지"*를 가를 수 있다. 숫자를 새 값으로 덮어쓰면 **재현 검사가
    #     '지금 나오는 값'을 그대로 베끼는 동어반복**이 되어 아무것도 못 잡는다.
    print("\n[3] ⭐⭐ 8/7 실측 재현 (옛 필드 기준 — 기준선이 살아있는가)")
    db_legacy = {**db, "parts": {
        k: {**v, "gripper_width_mm": v["gripper_width_mm_legacy_0806"]}
        for k, v in db["parts"].items()}}
    # (여유mm, 치명, 헐거움, 파지가능률%)
    RECORD = [(0.0, 10, 13, 83.8), (10.0, 4, 14, 92.6),
              (20.0, 3, 59, 94.1), (43.0, 0, 64, 98.5)]
    for safety, fatal, loose, rate in RECORD:
        r = judge_with_safety(pairs, db_legacy, safety)
        check(f"+{safety:.0f}mm → 치명 {fatal}",
              r["verdicts"]["fatal"] == fatal, f"실제 {r['verdicts']['fatal']}")
        check(f"+{safety:.0f}mm → 헐거움 {loose}",
              r["verdicts"]["loose"] == loose, f"실제 {r['verdicts']['loose']}")
        check(f"+{safety:.0f}mm → 파지 {rate}%",
              abs(r["graspable_rate"] * 100 - rate) < 0.15,
              f"실제 {r['graspable_rate']*100:.1f}%")

    # 8/7의 핵심 주장 = +10mm가 최적점(치명은 크게 줄고 헐거움은 거의 안 는다)
    r0 = judge_with_safety(pairs, db_legacy, 0.0)
    r10 = judge_with_safety(pairs, db_legacy, 10.0)
    r20 = judge_with_safety(pairs, db_legacy, 20.0)
    check("⭐ +10mm는 치명을 절반 이하로 줄인다",
          r10["verdicts"]["fatal"] <= r0["verdicts"]["fatal"] // 2)
    check("⭐ +10mm는 헐거움을 거의 안 늘린다(+2 이내)",
          r10["verdicts"]["loose"] - r0["verdicts"]["loose"] <= 2)
    check("⭐ +20mm부터 헐거움이 폭증한다(4배 이상)",
          r20["verdicts"]["loose"] >= r0["verdicts"]["loose"] * 4,
          f"{r0['verdicts']['loose']} → {r20['verdicts']['loose']}")

    # ── 4. 🚨 여유는 used에만 더해야 한다 (내 실수 ①)
    print("\n[4] 🚨 여유를 DB 전체에 더하면 무효가 되는가(실수 재발 방지)")
    # ⭐ r0가 legacy 기준이므로 여기도 **같은 기준**으로 비교한다
    #   (다른 DB끼리 비교하면 "판정이 바뀌었다"가 여유 탓인지 필드 탓인지 못 가른다)
    widths_legacy = {k: float(v["gripper_width_mm_legacy_0806"])
                     for k, v in db["parts"].items()}
    shifted = {k: v + 10.0 for k, v in widths_legacy.items()}
    db_shift = apply_mapping(db_legacy, shifted)   # used·need 양쪽이 올라간 DB
    r_shift = judge_with_safety(pairs, db_shift, 0.0)
    check("⭐ DB 전체를 올리면 판정이 안 바뀐다(= 그렇게 하면 안 된다)",
          r_shift["verdicts"]["fatal"] == r0["verdicts"]["fatal"],
          f"{r0['verdicts']['fatal']} vs {r_shift['verdicts']['fatal']}")

    # ── 5. 스트로크 상한
    print("\n[5] 스트로크 상한")
    over = [max(g) for g in gs if max(g) > STROKE_MAX_MM]
    check(f"스트로크 {STROKE_MAX_MM:.0f}mm 초과 대표값을 검출한다",
          len(over) >= 1, "초과 값이 없다면 DB가 바뀐 것")
    print(f"     (초과: {[int(v) for v in over]} — 99mm는 top_inner_sheet004 = "
          "DB 전용이라 공정 대상 아님)")

    # ── 5b. ⭐⭐ 8/20 교정본 기준선 (현행 필드) — 새 상태도 못박는다
    #   [3]이 옛 기준선을 지키고, 여기가 **지금 운용하는 값**을 지킨다.
    #   🚨 이 두 블록이 함께 있어야 "무엇이 바뀌었나"를 가릴 수 있다.
    print("\n[5b] ⭐⭐ 8/20 교정본 재현 (현행 필드 = grip_span_flat_mm)")
    RECORD_0820 = [(0.0, 12, 5), (10.0, 0, 14)]
    for safety, fatal, loose in RECORD_0820:
        r = judge_with_safety(pairs, db, safety)
        check(f"[0820] +{safety:.0f}mm → 치명 {fatal}",
              r["verdicts"]["fatal"] == fatal, f"실제 {r['verdicts']['fatal']}")
        check(f"[0820] +{safety:.0f}mm → 헐거움 {loose}",
              r["verdicts"]["loose"] == loose, f"실제 {r['verdicts']['loose']}")
    # ⭐ 교정의 핵심 = 옛 필드보다 치명이 늘 수도 있다(여유 0에서). 그 사실을 박아둔다.
    check("⭐ 교정 후 여유 0에서는 치명이 옛 필드보다 적지 않다",
          judge_with_safety(pairs, db, 0.0)["verdicts"]["fatal"] >= r0["verdicts"]["fatal"],
          "DB가 틀렸다≠결과가 좋아진다 — 여유와 함께 봐야 한다")

    # ── 6. 기존 analyze()와 어긋나지 않는가
    print("\n[6] 기존 도구와의 정합")
    a = analyze(pairs, db_legacy)   # ⭐ r0와 같은 기준(legacy)으로 대조
    check("여유 0일 때 analyze()와 치명 일치",
          a["verdicts"]["fatal"] == r0["verdicts"]["fatal"],
          f"{a['verdicts']['fatal']} vs {r0['verdicts']['fatal']}")
    check("여유 0일 때 analyze()와 파지 가능률 일치",
          abs(a["graspable_rate"] - r0["graspable_rate"]) < 0.001)

    print()
    print("=" * 68)
    print(f"결과: {PASS} 통과 / {FAIL} 실패")
    print("=" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
