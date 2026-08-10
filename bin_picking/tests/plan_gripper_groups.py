#!/usr/bin/env python3
"""벌림 값을 그리퍼 등록 점수(최대 15점) 안으로 묶는다. (2026-08-10)

⭐ 왜 필요한가 = 두 문제가 같은 해법을 갖는다
------------------------------------------------------------
**문제 ①** 그리퍼(JEGB-4285P-3MA)는 **최대 15점만 등록**되는데
DB의 고유 벌림값은 **19가지**다. 그대로는 티칭을 못 한다.

**문제 ②** 8/7 실측에서 혼동 때문에 **치명 10건**(벌림이 모자라 안 들어감)이 났다.
   → 8/7 결론: **안전여유 +10mm면 치명 10→4건**(헐거움은 13→14로 거의 안 늚).

🚨🚨 **실측 결과 = 이 둘은 같은 조작이 아니다** (2026-08-10에 확인, 내 가설이 틀렸음)
------------------------------------------------------------
처음에 *"위로 묶으면 점수도 줄고 벌림도 커지니 치명도 함께 줄 것"* 이라고 예상했으나
**돌려보니 치명이 10→10으로 하나도 안 줄었다.**

⭐ **원인** = 두 조작이 **다른 값을 건드린다**:
  - **묶기**는 **간격이 좁은 값만** 올린다(최대 +5mm). 대부분의 값은 단독 그룹이라 그대로다.
  - **안전여유**는 **모든 값에 일괄로** 더한다.
  - 그런데 치명 10건의 **부족분은 3~43mm**이고, 그중 8건이 **8mm 이상 모자란다**.
    ⇒ 최대 +5mm짜리 묶기로는 메울 수 없다.

⇒ ⭐ **결론 = 묶기는 "등록 점수 문제"만 푼다. 치명은 안전여유가 푼다.**
   두 문제를 하나로 묶어 설명하려던 것이 잘못이었다.
   ✅ **다만 묶기가 해를 끼치지도 않는다**(치명·헐거움·무해 전부 불변) =
   **파지 성능 손실 0으로 19가지를 15점에 넣을 수 있다**는 것이 이 도구의 결론이다.
   → `--safety` 로 안전여유를 함께 걸어 두 조작의 효과를 각각·동시에 볼 수 있다.

🚨 반드시 위로 묶어야 하는 이유 (방향이 결과를 가른다)
------------------------------------------------------------
벌림이 **모자라면 물리적으로 안 들어간다(치명)**, **남으면 헐겁게라도 잡힌다(경미)**.
⇒ 그룹 대표값은 반드시 **그룹 내 최대값**이어야 한다. 평균이나 중앙값으로 묶으면
   **그룹 최대 부품이 치명이 된다** — 묶기가 새로운 실패를 만든다.

⚠️ 이 도구가 답하지 않는 것
------------------------------------------------------------
- **DB 절대값이 맞는지** — 8/6에 확인했듯 `gripper_width_mm`은 **방향이 섞여
  작성돼 있어**(20종은 중간변+여유, 7종은 최소변+여유) 티칭 때 실물 교정 대상이다.
  ⭐ 그래서 이 도구도 **"몇 mm"가 아니라 "어느 쪽으로 묶이는가"**만 신뢰한다.
- **헐거움이 실제로 미끄러지는지** — 파지력(15~150N)과 마찰의 문제라 실물 시험이 필요하다.
  ⭐ 8/7에 확인된 것은 **+20mm부터 헐거움이 59건으로 폭증**한다는 것뿐이다.

⇒ ⏸️ **DB에 박지 않는다.** 근거만 남기고 실제 반영은 티칭 때 실물 검증 후.
   (8/6 `MANUAL_OVERRIDES` 원칙 = 사람이 내린 결정만 코드에 박는다)

사용법
------------------------------------------------------------
    python tests/plan_gripper_groups.py                 # 기본(15점)
    python tests/plan_gripper_groups.py --max-points 12 # 더 줄여보기
    python tests/plan_gripper_groups.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyze_confusion_impact import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_METRICS,
    LOOSE_MM,
    TIGHT_MM,
    analyze,
    load_db,
    parse_pairs,
    width_of,
)

# 그리퍼 등록 한도 — JEGB-4285P-3MA 사양(협력사 회신, 8/6 확정)
MAX_POINTS = 15

# 스트로크 상한. 그룹 대표값이 이걸 넘으면 물리적으로 벌릴 수 없다.
STROKE_MAX_MM = 85.0


def part_widths(db: dict) -> dict[str, float]:
    """DB에 등재된 부품별 벌림값."""
    parts = db.get("parts", db)
    out = {}
    for label, entry in parts.items():
        if not isinstance(entry, dict):
            continue
        w = width_of(db, label)
        if w is not None:
            out[label] = float(w)
    return out


def group_upward(values: list[float], max_points: int) -> list[list[float]]:
    """정렬된 고유값을 max_points개 그룹으로 묶는다 — **대표값은 그룹 최대값**.

    ⭐ 목적함수 = **올림 폭의 최댓값을 최소화**한다.
       (총합이 아니라 최댓값을 줄인다 — 한 부품이 크게 헐거워지는 것이
        여러 부품이 조금씩 헐거워지는 것보다 위험하기 때문이다)

    구현 = 인접 값 사이 간격이 큰 곳부터 잘라 경계로 삼는다.
    ⭐ 값이 1차원이고 그룹이 연속 구간이어야 하므로 **이 탐욕법이 최적**이다
      (간격이 큰 곳을 자르지 않으면 그 간격만큼의 올림이 반드시 생긴다).
    """
    vals = sorted(set(values))
    if len(vals) <= max_points:
        return [[v] for v in vals]

    # 인접 간격 중 큰 것부터 (max_points - 1)개를 경계로 삼는다
    gaps = [(vals[i + 1] - vals[i], i) for i in range(len(vals) - 1)]
    gaps.sort(reverse=True)
    cuts = sorted(i for _, i in gaps[: max_points - 1])

    groups, start = [], 0
    for c in cuts:
        groups.append(vals[start : c + 1])
        start = c + 1
    groups.append(vals[start:])
    return groups


def build_mapping(widths: dict[str, float], max_points: int) -> tuple[dict, list]:
    """부품 → 그룹 대표값 매핑."""
    groups = group_upward(list(widths.values()), max_points)
    val_to_rep = {}
    for g in groups:
        rep = max(g)  # 🚨 반드시 최대값 — 위 docstring 참조
        for v in g:
            val_to_rep[v] = rep
    mapping = {lbl: val_to_rep[w] for lbl, w in widths.items()}
    return mapping, groups


def judge_with_safety(pairs: list, db: dict, safety: float = 0.0) -> dict:
    """안전여유를 **used(로봇이 실제로 벌리는 값)에만** 더해 재판정한다.

    🚨🚨 **여기가 8/10에 내가 틀렸던 지점이다.**
    처음엔 DB 전체(`gripper_width_mm`)에 여유를 더했는데, 그러면
    **used와 need가 같이 올라가 차이가 그대로**라 판정이 하나도 안 바뀐다(동어반복).
    ⭐ 안전여유의 뜻은 *"예측한 벌림보다 10mm 더 벌려서 집는다"* 이므로
    **로봇이 벌리는 쪽에만** 더해야 한다. need(그 부품에 실제로 필요한 값)는 물리량이라
    우리가 바꿀 수 있는 값이 아니다.

    ⭐ 교훈 = **"무엇을 더하는가"보다 "어느 쪽에 더하는가"가 결과를 가른다.**
       8/6에 파지 판정에서 *"방향이 결과를 가른다"*를 배웠는데 같은 함정을 다시 밟았다.

    🚨🚨 **두 번째 실수 = 라벨이 맞은 건을 여유 적용에서 뺐다.**
    처음엔 `label_ok`면 무조건 무해로 셌는데, **실제 로봇은 예측이 맞았는지 모르는 채로
    +Nmm를 벌린다.** 맞은 건도 똑같이 헐거워진다.
    ⇒ 여유는 **모든 건에 적용해야** 한다. 안 그러면 헐거움이 과소평가된다
      (+20mm에서 26건으로 나왔으나 실제는 **59건** = 8/7 기록이 맞았다).
    ⭐ **+10mm에서 결과가 같았던 것은 우연**이다(여유가 LOOSE 임계 15mm보다 작아
      맞은 건이 헐거움으로 안 넘어갔을 뿐).
    """
    from analyze_confusion_impact import (VERDICT_FATAL, VERDICT_LOOSE,
                                          VERDICT_OK, VERDICT_UNKNOWN, judge)

    counts = {"fatal": 0, "loose": 0, "harmless": 0, "unknown": 0}
    key = {VERDICT_FATAL: "fatal", VERDICT_LOOSE: "loose",
           VERDICT_OK: "harmless", VERDICT_UNKNOWN: "unknown"}

    for p in pairs:
        used = width_of(db, p["pred"])
        need = width_of(db, p["gt"])
        # ⭐ 여유는 라벨이 맞았든 틀렸든 **모든 건에** 적용한다(위 docstring 참조)
        if used is not None:
            used += safety           # ⭐ used에만 더한다
        counts[key[judge(used, need, TIGHT_MM, LOOSE_MM)]] += 1

    total = len(pairs)
    graspable = total - counts["fatal"] - counts["unknown"]
    return {
        "total_matched": total,
        "verdicts": counts,
        "graspable": graspable,
        "graspable_rate": round(graspable / total, 4) if total else 0.0,
    }


def apply_mapping(db: dict, mapping: dict[str, float]) -> dict:
    """DB 사본에 그룹 대표값을 적용한다(원본은 건드리지 않는다)."""
    import copy

    d = copy.deepcopy(db)
    parts = d.get("parts", d)
    for label, rep in mapping.items():
        if label in parts and isinstance(parts[label], dict):
            parts[label]["gripper_width_mm"] = rep
    return d


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    ap.add_argument("--cond", default="c1", help="평가 조건(기본 c1=실운영)")
    ap.add_argument("--max-points", type=int, default=MAX_POINTS)
    ap.add_argument("--safety", type=float, default=0.0,
                    help="안전여유(mm) — 로봇이 **실제로 벌리는 값(used)에만** 더한다. "
                         "8/7 실측 최적점 10mm(치명 10→4). "
                         "🚨DB 전체를 올리는 것이 아니다(그러면 used·need가 같이 올라 무효)")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    db = load_db(args.db)
    widths = part_widths(db)
    uniq = sorted(set(widths.values()))

    print("=" * 72)
    print(f" 벌림 그룹 계획   (등록 한도 {args.max_points}점"
          + (f" · 안전여유 +{args.safety:.0f}mm" if args.safety else "") + ")")
    print("=" * 72)
    print(f"  DB 등재 부품      : {len(widths)}종")
    print(f"  고유 벌림값       : {len(uniq)}가지 → {[int(v) for v in uniq]}")
    if len(uniq) <= args.max_points:
        print(f"  ✅ 이미 {args.max_points}점 이하 — 묶을 필요 없음")
    else:
        print(f"  🚨 {len(uniq)}가지 > {args.max_points}점 — **묶어야 티칭 가능**")

    mapping, groups = build_mapping(widths, args.max_points)

    print()
    print(f"  📦 그룹 {len(groups)}개 (대표값 = 그룹 최대값)")
    for g in groups:
        rep = max(g)
        members = ", ".join(str(int(v)) for v in g)
        up = rep - min(g)
        mark = "" if len(g) == 1 else f"   ← 최대 +{up:.0f}mm 올림"
        over = "  🚨스트로크 초과" if rep > STROKE_MAX_MM else ""
        print(f"     {rep:5.0f}mm  ⟵ [{members}]{mark}{over}")

    # ── 효과 측정: 묶기 전후로 치명/헐거움이 어떻게 변하나
    pairs = parse_pairs(json.loads(args.metrics.read_text()), args.cond)
    grouped_db = apply_mapping(db, mapping)
    before = judge_with_safety(pairs, db, args.safety)
    after = judge_with_safety(pairs, grouped_db, args.safety)

    # ⚠️ 판정 건수는 `verdicts` 아래에 중첩돼 있다 — 최상위에 있을 것이라 **추측했다가
    #    KeyError로 잡혔다**(시그니처 추측 금지, 8/5·8/7·8/10에 이어 일곱 번째).
    bv, av = before["verdicts"], after["verdicts"]

    print()
    print(f"  ⭐ 효과 (조건 {args.cond} · 매칭 {before['total_matched']}건)")
    print(f"     {'':22s} {'묶기 전':>8s} {'묶은 후':>8s}")
    print(f"     {'🔴 치명(안 들어감)':20s} {bv['fatal']:>8d} {av['fatal']:>8d}")
    print(f"     {'🟠 헐거움':20s} {bv['loose']:>8d} {av['loose']:>8d}")
    print(f"     {'🟢 무해':20s} {bv['harmless']:>8d} {av['harmless']:>8d}")
    print(f"     {'⭐파지 가능률':20s} {before['graspable_rate']*100:>7.1f}% "
          f"{after['graspable_rate']*100:>7.1f}%")

    d_fatal = av["fatal"] - bv["fatal"]
    d_rate = (after["graspable_rate"] - before["graspable_rate"]) * 100

    print()
    if d_fatal < 0:
        print(f"  ✅ 치명 {-d_fatal}건 감소 · 파지 가능률 {d_rate:+.1f}%p")
        print("     ⭐ 묶기가 **등록 점수를 줄이면서 동시에 파지를 개선**한다")
        print("        (위로 묶으므로 모자라던 벌림이 채워진다)")
    elif d_fatal == 0:
        print(f"  🟢 치명 변화 없음 · 파지 가능률 {d_rate:+.1f}%p")
        print("     → 등록 점수를 줄이는 데 **파지 성능 손실이 없다**")
    else:
        print(f"  🚨 치명 {d_fatal}건 **증가** — 묶기가 해를 끼쳤다")
        print("     ⭐ 대표값 선택 규칙을 확인할 것(최대값이 아니면 이렇게 된다)")

    if av["loose"] > bv["loose"]:
        print(f"  ⚠️ 헐거움 {av['loose'] - bv['loose']}건 증가 — "
              "8/7 실측상 +20mm부터 폭증하므로 올림 폭을 주시할 것")

    # 스트로크 초과 검사 — 물리적으로 불가능한 대표값이 생기지 않았는가
    over = [max(g) for g in groups if max(g) > STROKE_MAX_MM]
    print()
    if over:
        print(f"  🚨 스트로크 {STROKE_MAX_MM:.0f}mm 초과 대표값: "
              f"{[int(v) for v in over]} — 해당 그룹은 물리적으로 벌릴 수 없다")
    else:
        print(f"  ✅ 모든 대표값이 스트로크 {STROKE_MAX_MM:.0f}mm 이내")

    print()
    print("  ⏸️ **DB에 반영하지 않는다** — `gripper_width_mm`은 방향이 섞여 작성돼 있어")
    print("     절대값이 티칭 때 실물 교정 대상이다(8/6). 여기서는 근거만 남긴다.")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "max_points": args.max_points,
                    "unique_before": len(uniq),
                    "groups": [{"rep": max(g), "members": g} for g in groups],
                    "mapping": mapping,
                    "before": before,
                    "after": after,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"\n  💾 {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
