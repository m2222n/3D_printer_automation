#!/usr/bin/env python3
"""`gripper_width_mm`을 **눕힘 기준 + 안전여유**로 교정한다. (2026-08-20)

⭐ 근거 = [[grasp-field-correction-0820]] / `decompose_fatal_grasp_0820.py`
------------------------------------------------------------------------
기존 `gripper_width_mm`은 **방향이 섞여** 있었다(21종 중간변+여유 / 7종 최소변+여유 / 1종 기타).
8/6 전제(**부품은 빈에 눕는다** ⇒ 무는 변 = 중간변)와 맞는 필드는 `grip_span_flat_mm`
하나뿐이고, 이 값은 description 중간변과 **29/29 일치**한다.

교정식:  **gripper_width_mm = grip_span_flat_mm**  (여유는 넣지 않는다)

🚨🚨 여유를 DB에 넣지 않는 이유 — 처음에 여기서 틀렸다 (8/20)
---------------------------------------------------------------
처음엔 `span_flat + 10mm`를 DB에 박으려 했고 *"그러면 95.5%가 나온다"*고 기대했다.
**틀렸다. 84.4%가 나왔다.** 이유는 8/10에 이미 적어둔 그것이다 —
**모든 부품에 같은 상수를 더하면 `used`와 `need`가 같이 올라가 차이가 그대로**다(동어반복).

  ⇒ ⭐⭐ **안전여유는 DB 값이 아니라 "런타임에 한 번 더 벌리는 동작"이다.**
     DB에 박으면 (a) 판정에 아무 효과가 없고 (b) 런타임 여유와 **이중 가산**된다.

  ✅ 올바른 분리:
     DB          = **부품의 진짜 무는 변**(span_flat) — 물리량, 우리가 못 바꾸는 값
     런타임 여유  = `GRASP_SAFETY_MARGIN_MM = 10.0` — 로봇이 실제로 더 벌리는 양

  실측(90장 514쌍) — 교정된 DB 기준 런타임 여유별:
     +0mm  치명 80 · 84.4%   |  +10mm  치명 23 · **95.5%** 🎯
     +5mm  치명 46 · 91.1%   |  +15mm  치명  7 · 98.6%
     +20mm는 99.4%지만 헐거움 466건으로 폭증(미끄러짐) ⇒ **+10mm가 최적점**(8/7과 동일).

🚨🚨 왜 옛 값을 지우지 않고 남기는가
------------------------------------
이번 사고의 본질은 *"값이 틀린 것"*이 아니라 **"어떤 기준으로 쓴 값인지 아무도 몰랐던 것"**이다.
덮어쓰고 끝내면 **똑같은 상태를 다시 만든다**. 그래서 각 부품에 다음을 남긴다:

    gripper_width_mm             : 교정된 값 (= grip_span_flat_mm, 여유 미포함)
    gripper_width_mm_legacy_0806 : 옛 값 (참조용 · 🚫사용 금지)
    width_basis                  : "grip_span_flat_mm" ← ⭐ 근거를 값 옆에 박는다

⇒ [[feedback-deprecated-design-must-be-marked]] = *"주석만 달면 코드는 계속 옛 값을 로드한다."*
   이번엔 **값 자체를 바꾸고 옛 값에 폐기 표기**를 한다.

⚠️ 물리 한계 확인 (교정 전 반드시)
-----------------------------------
✅ 실제 그리퍼 JEGB-4285P-3MA **스트로크 85mm**. 교정값(span_flat)은 최대 89.0
   (`top_inner_sheet004`)이고 **85mm 초과는 그 1종뿐이며 이미 `not_pickable`** 이라
   로봇에 좌표가 안 나간다 ⇒ 실사용 영향 없음.
   ⚠️ 단 **런타임 여유 +10mm를 걸면** `17_mks_holder`(82.5→92.5)도 넘는데, 이 역시
   `not_pickable`이다. **pickable 20종은 여유 포함 최대 77.5mm로 안전**하다.
🚨 다만 `grasp_plan.py:105`의 `GRIPPER_WIDTH_RANGE_MM = (0.0, 110.0)`은
   **실제 스트로크 85mm와 어긋난다**(별건 이슈로 기록). 이 스크립트는 그 상수를
   건드리지 않는다 — 한 번에 한 가지만 바꾼다.

사용법:
    python tests/apply_grasp_width_fix_0820.py --dry-run     # 변경 미리보기(기본)
    python tests/apply_grasp_width_fix_0820.py --apply       # 실제 반영(백업 생성)
    python tests/apply_grasp_width_fix_0820.py --verify      # 반영 결과 검증만
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parents[0] / "config" / "grasp_database.yaml"

# ⭐ 런타임 여유 — **DB에 박지 않는다**(위 docstring 참조). 검증용으로만 쓴다.
RUNTIME_SAFETY_MM = 10.0
REAL_STROKE_MM = 85.0          # JEGB-4285P-3MA 확정 사양
BASIS_TAG = "grip_span_flat_mm"

# 🚨 기대값 — 재현되지 않으면 중단한다(조용히 어긋나지 않게).
#   교정된 DB + **런타임 여유 10mm** 에서 나와야 하는 값.
EXPECTED_GRASP_RATE = 0.955
EXPECTED_FATAL = 23
EXPECTED_RATE_NO_MARGIN = 0.844   # 여유 0일 때(= DB 값 그대로)


def load_yaml(path: Path):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def plan_changes(parts: dict) -> list[dict]:
    """부품별 교정 계획을 만든다. 🚨 계산만 하고 파일은 건드리지 않는다."""
    rows = []
    for name, v in parts.items():
        old = float(v["gripper_width_mm"])
        span = float(v["grip_span_flat_mm"])
        new = round(span, 1)      # ⭐ 여유를 더하지 않는다
        rows.append({
            "part": name,
            "old": old,
            "span_flat": span,
            "new": new,
            "delta": round(new - old, 1),
            "pickability": v.get("pickability", "?"),
            "over_stroke": new > REAL_STROKE_MM,
        })
    return rows


def edit_yaml_text(text: str, rows: list[dict]) -> tuple[str, int]:
    """YAML을 **텍스트로** 편집한다 — 주석·순서·서식을 보존하기 위해서다.

    🚨 yaml.dump로 재작성하면 이 파일의 **주석 전체(판정 근거·경고)가 날아간다.**
       그 주석이 이번 사고를 잡아낸 근거였다. 따라서 정규식 치환으로 최소 침습.
    """
    n = 0
    for r in rows:
        # 해당 부품 블록을 찾는다 (2칸 들여쓴 `  <name>:` ~ 다음 부품 전까지)
        # 🚨 키가 **따옴표로 감싸져 있을 수 있다** (`"14_13":`).
        #    8/6에 정규식이 이 키를 놓쳐 **28/29만 조용히 처리**된 전례가 있다
        #    ([[gripper-jegb4285]]). 그래서 따옴표를 선택적으로 허용하고,
        #    아래 전수 대조(29/29)로 누락을 반드시 잡는다.
        block_re = re.compile(
            rf"(^  \"?{re.escape(r['part'])}\"?:\n)((?:^(?:    .*|\s*)\n)*)",
            re.MULTILINE)
        m = block_re.search(text)
        if not m:
            raise RuntimeError(f"부품 블록을 못 찾음: {r['part']}")
        head, body = m.group(1), m.group(2)

        # gripper_width_mm 줄을 교체 + 옛 값·근거를 함께 남긴다
        w_re = re.compile(r"^(    )gripper_width_mm:\s*([\d.]+)(.*)$", re.MULTILINE)
        wm = w_re.search(body)
        if not wm:
            raise RuntimeError(f"gripper_width_mm 줄을 못 찾음: {r['part']}")
        old_txt = wm.group(2)
        replacement = (
            f"    gripper_width_mm: {r['new']:g}"
            f"            # ⭐0820 교정 = {BASIS_TAG} (여유 미포함)\n"
            f"    width_basis: \"{BASIS_TAG}\"\n"
            f"    gripper_width_mm_legacy_0806: {old_txt}"
            f"   # 🚫폐기 — 방향 혼재(최소변/중간변). 판정에 쓰지 말 것"
        )
        new_body = body[:wm.start()] + replacement + body[wm.end():]
        text = text[:m.start()] + head + new_body + text[m.end():]
        n += 1

    # 🚨 양방향 검증 — "몇 개 바꿨나"가 아니라 "빠진 게 없나"를 센다.
    #   8/6 교훈 = 정규식 누락은 **실패가 아니라 조용한 미처리**로 나타난다.
    if n != len(rows):
        raise RuntimeError(f"처리 {n}종 ≠ 대상 {len(rows)}종 — 누락이 있다")
    tags = text.count(f'width_basis: "{BASIS_TAG}"')
    legacy = text.count("gripper_width_mm_legacy_0806:")
    if tags != len(rows) or legacy != len(rows):
        raise RuntimeError(
            f"태그 수 불일치: width_basis {tags} · legacy {legacy} "
            f"vs 대상 {len(rows)}종")
    return text, n


def verify(db_path: Path) -> int:
    """교정 후 실제로 95.5%가 나오는지 **측정 도구로** 확인한다.

    ⭐ 직접 계산해서 자기 자신을 검증하면 같은 실수를 공유한다
      ([[feedback-test-must-be-able-to-fail]]) ⇒ 상류 도구를 그대로 돌린다.
    """
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location(
        "dec", HERE / "decompose_fatal_grasp_0820.py")
    dec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dec)

    mod = dec.load_impact_module()
    db = mod.load_db(db_path)
    parts = db["parts"]
    metrics = json.loads(dec.DEFAULT_METRICS.read_text(encoding="utf-8"))
    pairs = mod.parse_pairs(metrics, None)

    # ⭐ 두 지점을 **모두** 확인한다 — 하나만 보면 동어반복을 또 놓친다.
    r0 = dec.sweep(pairs, parts, mod, "gripper_width_mm", 0.0)
    r10 = dec.sweep(pairs, parts, mod, "gripper_width_mm", RUNTIME_SAFETY_MM)
    print(f"  ① DB 값 그대로 (런타임 여유 0)")
    print(f"     치명 {r0['fatal']:3d} · 헐거움 {r0['loose']:3d} · "
          f"파지 {r0['rate']*100:5.1f}%  (기대 {EXPECTED_RATE_NO_MARGIN*100:.1f}%)")
    print(f"  ② + 런타임 여유 {RUNTIME_SAFETY_MM:g}mm  ⭐실제 운용 조건")
    print(f"     치명 {r10['fatal']:3d} · 헐거움 {r10['loose']:3d} · "
          f"파지 {r10['rate']*100:5.1f}%  (기대 {EXPECTED_GRASP_RATE*100:.1f}%)")

    ok0 = round(r0["rate"], 3) == EXPECTED_RATE_NO_MARGIN
    ok = (r10["fatal"] == EXPECTED_FATAL
          and round(r10["rate"], 3) == EXPECTED_GRASP_RATE)
    print(f"     {'✅ 두 지점 모두 일치' if (ok and ok0) else '❌ 불일치'}")
    ok = ok and ok0

    # 물리 한계 검사 — **런타임 여유를 포함한 최악값**으로 본다
    worst = {k: float(v["gripper_width_mm"]) + RUNTIME_SAFETY_MM
             for k, v in parts.items()}
    over = [k for k, w in worst.items() if w > REAL_STROKE_MM]
    bad = [k for k in over if parts[k].get("pickability") == "pickable"]
    print(f"  스트로크 {REAL_STROKE_MM:g}mm 초과(여유 포함): {len(over)}종 {over}")
    print(f"    그 중 pickable: {len(bad)}종 {bad}  "
          f"{'✅ 없음' if not bad else '🔴 로봇에 나갈 수 있다'}")
    pk = [w for k, w in worst.items()
          if parts[k].get("pickability") == "pickable"]
    print(f"    pickable 최대 벌림(여유 포함) = {max(pk):.1f}mm "
          f"{'✅' if max(pk) <= REAL_STROKE_MM else '🔴'}")

    # 근거 태그가 전 종에 박혔는가
    tagged = sum(1 for v in parts.values() if v.get("width_basis") == BASIS_TAG)
    print(f"  width_basis 태그: {tagged}/{len(parts)} "
          f"{'✅' if tagged == len(parts) else '❌'}")

    return 0 if (ok and not bad and tagged == len(parts)) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="파지 벌림 DB 교정")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--apply", action="store_true", help="실제 파일에 반영")
    ap.add_argument("--verify", action="store_true", help="반영 결과 검증만")
    args = ap.parse_args()

    if args.verify:
        print("=" * 72)
        print(" 교정 결과 검증")
        print("=" * 72)
        return verify(args.db)

    db = load_yaml(args.db)
    parts = db["parts"]
    rows = plan_changes(parts)

    print("=" * 78)
    print(f" gripper_width_mm 교정 계획 — {BASIS_TAG}")
    print("=" * 78)
    print(f"  {'부품':28s} {'옛값':>7s} {'span':>7s} {'새값':>7s} {'Δ':>7s}  비고")
    for r in sorted(rows, key=lambda x: x["delta"]):
        note = []
        if r["over_stroke"]:
            note.append(f"⚠️{REAL_STROKE_MM:g}mm초과")
        if r["pickability"] != "pickable":
            note.append(f"({r['pickability']})")
        print(f"  {r['part']:28s} {r['old']:7.1f} {r['span_flat']:7.1f} "
              f"{r['new']:7.1f} {r['delta']:+7.1f}  {' '.join(note)}")

    inc = sum(1 for r in rows if r["delta"] > 0)
    dec_ = sum(1 for r in rows if r["delta"] < 0)
    over = [r for r in rows if r["over_stroke"]]
    over_pick = [r for r in over if r["pickability"] == "pickable"]
    print()
    print(f"  총 {len(rows)}종 — 증가 {inc} · 감소 {dec_} · 동일 {len(rows)-inc-dec_}")
    print(f"  ⚠️ 스트로크 {REAL_STROKE_MM:g}mm 초과 {len(over)}종 "
          f"{[r['part'] for r in over]}")
    print(f"     그 중 pickable = {len(over_pick)}종 "
          f"{'✅ 없음(로봇에 안 나간다)' if not over_pick else '🔴 위험'}")

    if not args.apply:
        print("\n  ℹ️ --dry-run(기본). 실제 반영은 --apply")
        return 0

    if over_pick:
        print("\n  🔴 pickable 부품이 스트로크를 넘는다 — 중단한다.", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = args.db.with_suffix(f".yaml.bak_{stamp}")
    shutil.copy2(args.db, backup)
    print(f"\n  💾 백업: {backup}")

    text = args.db.read_text(encoding="utf-8")
    new_text, n = edit_yaml_text(text, rows)
    args.db.write_text(new_text, encoding="utf-8")
    print(f"  ✅ {n}종 반영")

    # 🚨 쓰고 나서 반드시 파싱된다는 것을 확인한다
    check = load_yaml(args.db)
    if len(check["parts"]) != len(parts):
        print("  🔴 재파싱 후 부품 수가 달라졌다 — 백업에서 되돌릴 것", file=sys.stderr)
        return 1
    print(f"  ✅ 재파싱 정상 ({len(check['parts'])}종)")
    print()
    return verify(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
