#!/usr/bin/env python3
"""치명 파지 실패를 **원인별로 분해**한다 — "DB 값 문제인가, 진짜 형상 혼동인가". (2026-08-20)

⭐ 왜 이 도구가 필요한가
------------------------
8/19에 파지 가능률 **87.4%**(치명 65건)를 측정하고 *"92% 미달"*로 판정했다. 그때 남긴
다음 수가 **"치명 65건을 왜 부족한가로 분해(DB 값 문제 vs 진짜 형상 혼동)"** 였고,
이 갈래가 **RGB 융합(1~2주) 진입 여부를 가른다**고 적어두었다. 이 파일이 그 분해다.

🚨🚨 분해 결과가 8/19 판정을 뒤집는다 — 판정에 쓴 DB 필드가 틀렸다
-------------------------------------------------------------------
`analyze_confusion_impact.py`는 `gripper_width_mm`으로 판정한다. 그런데
`grasp_database.yaml` 헤더가 이미 경고하고 있었다:

    ⚠️ `gripper_width_mm`은 **방향이 섞여 작성돼 있다**
       (20종은 중간변+여유, 7종은 최소변+여유).
       눕힘 전제와 어긋나는 7종은 티칭 때 실물로 교정할 것 —
       **`grip_span_flat_mm`가 눕힘 기준 값이다.**

⭐ 8/6에 확정한 물리 전제 = **부품은 빈에 눕는다.** 그러면
     조우가 무는 변 = **중간변**(sorted(dims)[1]) = `grip_span_flat_mm`
     눕혔을 때 높이 = 최소변       = `lying_height_mm`
  ⇒ **최소변+여유로 적힌 7종은 "두께를 문다"는 뜻**이고, 그건 8/6 전제에서
     **존재하지 않는 경로**다(19x19x1mm 판을 1mm 면으로 세울 수 없다).

✅ 전수 검산(`--verify`) = `grip_span_flat_mm`이 description의 중간변과
   **29/29 일치**. 반면 `gripper_width_mm`은 21종만 중간변 기준이다.
   ⇒ ⭐ **판정에 써야 할 값은 `grip_span_flat_mm`이다.**

🚨 그런데 필드를 바꾸면 파지율이 **떨어진다**(87.4% → 84.4%). 낙관적으로 바뀌지 않는다.
   이유 = `01_sol_block_a`처럼 **작게 적힌** 값은 "안 들어간다"(치명)를 만들지만
   동시에 그 부품이 **GT일 때는 need를 낮춰** 다른 혼동을 무해로 만들고 있었다.
   ⇒ ⭐⭐ **"DB가 틀렸다"가 "결과가 좋아진다"를 뜻하지 않는다.** 두 방향 모두 틀렸을 뿐이다.

⭐⭐⭐ 진짜 결론은 안전여유와 함께 봐야 나온다
-----------------------------------------------
올바른 필드(span_flat)로 재면 **안전여유의 효율이 완전히 달라진다**:

    여유    width(현행)          span_flat(올바름)
    +0mm    치명 65 · 87.4%      치명 80 · 84.4%
    +10mm   치명 51 · 90.1%      치명 23 · **95.5%**   ← 🎯 92% 돌파
    +15mm   치명 43 · 91.6%      치명  7 · 98.6%
    +20mm   치명 19 · 96.3%      치명  3 · 99.4%  (단 헐거움 466건)

⇒ 🎯 **+10mm에서 95.5%** = 8/7에 이미 최적점으로 잡아둔 그 여유값에서 92%를 넘는다.
   틀린 필드로 쟀기 때문에 90.1%로 보였던 것이다.

📌 분류 규칙 (Δspan = span_flat 기준 부족량)
    A. DB값 문제   : Δspan >= -2mm       → span_flat 로는 애초에 치명이 아니다
    B. 혼합        : |Δspan| < |Δwidth|-5 → DB가 과장했으나 형상차도 실재
    C. 진짜 형상혼동: 그 외              → 두 기준 모두 부족 = 인식으로 풀어야 함

사용법:
    python tests/decompose_fatal_grasp_0820.py --verify        # DB 필드 검산만
    python tests/decompose_fatal_grasp_0820.py                 # 분해 + 스윕
    python tests/decompose_fatal_grasp_0820.py --json out.json
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

DEFAULT_METRICS = Path(
    "/data/jtm/synth_out/blaze_capture_0818_eval/eval_real_metrics.json")

# 🚨 8/19 실측 기록 — 재현되지 않으면 도구나 데이터가 바뀐 것이므로 중단한다.
#    (8/10에 "8/7 기록값 4개 재현" 검사가 조용한 버그를 잡아낸 전례를 따른다.)
RECORDED_0819 = {0: (65, 31, 87.4), 10: (51, 46, 90.1),
                 15: (43, 107, 91.6), 20: (19, 450, 96.3)}

DIMS_RE = re.compile(r"\((\d+\.?\d*)[×x](\d+\.?\d*)[×x](\d+\.?\d*)mm\)")


def load_impact_module():
    """8/7 도구를 그대로 재사용한다 — 판정 로직을 복제하지 않는다.

    🚨 복제하면 두 파일이 조용히 갈라진다. `judge`/`parse_pairs`는 원본을 import 한다.
    """
    spec = importlib.util.spec_from_file_location(
        "analyze_confusion_impact", HERE / "analyze_confusion_impact.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify_db_fields(parts: dict) -> dict:
    """어느 필드가 '눕힘 기준 중간변'과 일치하는지 전수 검산한다.

    ⭐ 이 검산이 이 도구의 근거 전체다 — 필드 선택이 틀리면 아래 결론이 전부 틀린다.
    """
    span_ok, width_mid, width_thin, width_other, no_dims = 0, 0, 0, 0, []
    rows = []
    for name, v in parts.items():
        m = DIMS_RE.search(str(v.get("description", "")))
        if not m:
            no_dims.append(name)
            continue
        dims = sorted(float(x) for x in m.groups())
        thin, mid = dims[0], dims[1]
        w = float(v["gripper_width_mm"])
        s = float(v["grip_span_flat_mm"])
        agree = abs(s - mid) < 0.6
        span_ok += int(agree)
        if abs(w - mid) <= 12 and w >= mid - 1:
            kind = "mid+여유"
            width_mid += 1
        elif abs(w - thin) <= 12 and w >= thin - 1:
            kind = "thin+여유"
            width_thin += 1
        else:
            kind = "기타"
            width_other += 1
        rows.append({"part": name, "dims": dims, "span_flat": s,
                     "span_matches_mid": agree, "width": w, "width_kind": kind})
    return {"n_parts": len(parts), "span_matches_mid": span_ok,
            "width_mid": width_mid, "width_thin": width_thin,
            "width_other": width_other, "no_dims": no_dims, "rows": rows}


def sweep(pairs, parts, mod, field: str, safety: float,
          tight: float = 2.0, loose: float = 15.0):
    """안전여유를 걸고 재판정한다.

    🚨🚨 8/10 규칙 두 가지를 그대로 지킨다 (여기를 틀리면 조용히 어긋난다):
      ① 여유는 **used(로봇이 벌리는 값)에만** 더한다 — need에도 더하면 동어반복이다.
      ② 여유는 **label_ok 인 건에도** 적용한다 — 로봇은 예측이 맞았는지 모르는 채로
         +Nmm를 벌리므로 맞은 건도 똑같이 헐거워진다.
         (2026-08-20: 나도 ②를 한 번 빠뜨려 +20mm 헐거움이 137로 나왔다. 실제는 450.)
    """
    def w(label: str) -> Optional[float]:
        if not label or label not in parts:
            return None
        return float(parts[label][field])

    counts = collections.Counter()
    fatal_pairs = collections.Counter()
    for p in pairs:
        used, need = w(p["pred"]), w(p["gt"])
        if used is not None:
            used += safety
        v = mod.judge(used, need, tight, loose)
        counts[v] += 1
        if v == mod.VERDICT_FATAL:
            fatal_pairs[(p["gt"], p["pred"])] += 1
    total = len(pairs)
    graspable = total - counts[mod.VERDICT_FATAL] - counts[mod.VERDICT_UNKNOWN]
    return {"fatal": counts[mod.VERDICT_FATAL],
            "loose": counts[mod.VERDICT_LOOSE],
            "harmless": counts[mod.VERDICT_OK],
            "unknown": counts[mod.VERDICT_UNKNOWN],
            "rate": graspable / total if total else 0.0,
            "fatal_pairs": fatal_pairs}


def classify(pairs, parts, mod, tight: float = 2.0) -> dict:
    """현행 필드에서 치명인 건을 span_flat 기준으로 다시 보고 원인을 가른다."""
    def w(l): return float(parts[l]["gripper_width_mm"])
    def s(l): return float(parts[l]["grip_span_flat_mm"])

    buckets = collections.defaultdict(list)
    for p in pairs:
        if p["label_ok"] or p["pred"] not in parts or p["gt"] not in parts:
            continue
        if not (w(p["pred"]) < w(p["gt"]) - tight):
            continue  # 현행 기준으로 치명이 아닌 건은 대상이 아니다
        d_w = w(p["pred"]) - w(p["gt"])
        d_s = s(p["pred"]) - s(p["gt"])
        if d_s >= -tight:
            cat = "A_db_only"
        elif abs(d_s) < abs(d_w) - 5:
            cat = "B_mixed"
        else:
            cat = "C_real_shape"
        buckets[cat].append({"gt": p["gt"], "pred": p["pred"],
                             "d_width": round(d_w, 1), "d_span": round(d_s, 1)})
    return buckets


def main() -> int:
    ap = argparse.ArgumentParser(description="치명 파지 실패의 원인 분해")
    ap.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    ap.add_argument("--verify", action="store_true", help="DB 필드 검산만 하고 종료")
    ap.add_argument("--tight", type=float, default=2.0)
    ap.add_argument("--loose", type=float, default=15.0)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    mod = load_impact_module()
    db = mod.load_db()
    parts = db["parts"]

    # ── 1. DB 필드 검산 ────────────────────────────────────────────────
    ver = verify_db_fields(parts)
    print("=" * 78)
    print(" ① DB 필드 검산 — 어느 값이 '눕힘 기준(중간변)'인가")
    print("=" * 78)
    print(f"  grip_span_flat_mm == 중간변 : {ver['span_matches_mid']}/{ver['n_parts']}"
          f"  {'✅ 전수 일치' if ver['span_matches_mid'] == ver['n_parts'] else '❌'}")
    print(f"  gripper_width_mm  내역      : 중간변+여유 {ver['width_mid']}종 · "
          f"최소변+여유 {ver['width_thin']}종 · 기타 {ver['width_other']}종")
    print("  ⇒ ⭐ 판정에 써야 할 값은 grip_span_flat_mm 이다"
          " (8/6 '부품은 눕는다' 전제와 일치하는 유일한 필드)")
    if ver["no_dims"]:
        print(f"  ⚠️ description에 치수 없는 종: {ver['no_dims']}")
    if args.verify:
        return 0

    if not args.metrics.exists():
        print(f"🔴 평가 결과 없음: {args.metrics}", file=sys.stderr)
        return 1
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    pairs = mod.parse_pairs(metrics, None)   # 🚨 --cond "" 상당 = 전체 90장
    print(f"\n  매칭 쌍 {len(pairs)}건 (spatial TP · 전체 조건)")

    # ── 2. 8/19 기록 재현 검사 ────────────────────────────────────────
    print()
    print("=" * 78)
    print(" ② 8/19 기록값 재현 검사 (gripper_width_mm 기준)")
    print("=" * 78)
    all_ok = True
    for sf, (ef, el, er) in sorted(RECORDED_0819.items()):
        r = sweep(pairs, parts, mod, "gripper_width_mm", sf, args.tight, args.loose)
        ok = (r["fatal"] == ef and r["loose"] == el
              and round(r["rate"] * 100, 1) == er)
        all_ok &= ok
        print(f"  +{sf:2d}mm  치명 {r['fatal']:3d}(기록 {ef:3d}) · "
              f"헐거움 {r['loose']:3d}(기록 {el:3d}) · "
              f"파지 {r['rate']*100:5.1f}%(기록 {er:5.1f}) {'✅' if ok else '❌'}")
    if not all_ok:
        print("  🔴 재현 실패 — 데이터나 DB가 8/19 이후 바뀌었다. 결론 내지 말 것.",
              file=sys.stderr)
        return 2
    print("  ✅ 4행 전부 재현 — 도구·데이터가 8/19와 동일하다")

    # ── 3. 두 필드 × 안전여유 ─────────────────────────────────────────
    print()
    print("=" * 78)
    print(" ③ 올바른 필드로 다시 재기 (안전여유 스윕)")
    print("=" * 78)
    print(f"  {'여유':>6s} | {'gripper_width_mm (현행·틀림)':^32s} | "
          f"{'grip_span_flat_mm (올바름)':^32s}")
    print(f"  {'':>6s} | {'치명':>5s} {'헐거움':>6s} {'파지율':>9s}      | "
          f"{'치명':>5s} {'헐거움':>6s} {'파지율':>9s}")
    sweep_out = {}
    for sf in (0, 5, 10, 15, 20):
        a = sweep(pairs, parts, mod, "gripper_width_mm", sf, args.tight, args.loose)
        b = sweep(pairs, parts, mod, "grip_span_flat_mm", sf, args.tight, args.loose)
        sweep_out[sf] = {"width": {k: a[k] for k in ("fatal", "loose", "rate")},
                         "span_flat": {k: b[k] for k in ("fatal", "loose", "rate")}}
        mark = "  🎯" if b["rate"] >= 0.92 and a["rate"] < 0.92 else "    "
        print(f"  {sf:4d}mm | {a['fatal']:5d} {a['loose']:6d} {a['rate']*100:8.1f}%      | "
              f"{b['fatal']:5d} {b['loose']:6d} {b['rate']*100:8.1f}%{mark}")
    print("  🎯 = 현행 필드로는 미달인데 올바른 필드로는 92%를 넘는 지점")

    # ── 4. 치명 65건 원인 분해 ────────────────────────────────────────
    buckets = classify(pairs, parts, mod, args.tight)
    n_total = sum(len(v) for v in buckets.values())
    labels = {"A_db_only": "A. DB값 문제 (span_flat 로는 치명 아님)",
              "B_mixed": "B. 혼합 (DB가 과장했으나 형상차도 실재)",
              "C_real_shape": "C. 진짜 형상 혼동 (두 기준 모두 부족)"}
    print()
    print("=" * 78)
    print(f" ④ 치명 {n_total}건의 원인 분해")
    print("=" * 78)
    for k in ("A_db_only", "B_mixed", "C_real_shape"):
        n = len(buckets[k])
        print(f"  {labels[k]:44s} {n:3d}건 ({n/n_total*100:3.0f}%)")
    print()
    for k in ("A_db_only", "B_mixed", "C_real_shape"):
        if not buckets[k]:
            continue
        print(f"  ── {labels[k]}")
        agg = collections.Counter(
            (r["gt"], r["pred"], r["d_width"], r["d_span"]) for r in buckets[k])
        for (gt, pr, dw, ds), n in agg.most_common():
            print(f"     {n:2d}건  GT {gt:28s} → {pr:26s} "
                  f"Δwidth {dw:+7.1f}  Δspan {ds:+7.1f}")
        print()

    # ── 5. 결론 ───────────────────────────────────────────────────────
    b10 = sweep_out[10]["span_flat"]
    print("=" * 78)
    print(" ⑤ 결론")
    print("=" * 78)
    print(f"  · 올바른 필드 + 8/7이 정한 최적 여유 +10mm ⇒ 파지 가능률 "
          f"**{b10['rate']*100:.1f}%** (치명 {b10['fatal']}건 · 헐거움 {b10['loose']}건)")
    if b10["rate"] >= 0.92:
        print("  · 🎯 **92% 판정선을 넘는다** ⇒ 8/19의 '미달' 판정은 필드 오류였다.")
        print("  · ⇒ RGB 융합(1~2주)은 이 근거로는 **진입 불필요**.")
    else:
        print("  · 92% 미달 유지 ⇒ RGB 융합 진입을 검토할 것.")
    nc = len(buckets["C_real_shape"])
    print(f"  · 인식으로만 풀리는 진짜 형상 혼동 = **{nc}건**"
          f" (전체 {len(pairs)}쌍의 {nc/len(pairs)*100:.1f}%)")
    print("  ⚠️ 전제 = DB 값은 STL 계산치다. 실물 티칭 때 교정하면 건수는 바뀐다.")
    print("  ⚠️ 이 수치는 **치수 대조 계산값이고 실물 파지 시험이 아니다**(그리퍼 미장착).")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"verify": {k: v for k, v in ver.items()},
                   "n_pairs": len(pairs),
                   "sweep": {str(k): v for k, v in sweep_out.items()},
                   "fatal_decomposition": {k: buckets[k] for k in buckets},
                   "source_metrics": str(args.metrics)}
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"\n  📄 저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
