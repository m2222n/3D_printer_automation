#!/usr/bin/env python3
"""8/24 동시촬영 90장 라벨 내용 검사 — 정답지(group_labels_0824.json) 대조.

⭐ `check_labels_0819.py` 와 무엇이 다른가
   로직은 같다(8/19 것이 잘 작동했다). 달라진 것은 **세 가지**:
     ① 경로가 `/data/jtm/dual_capture_0824/`
     ② 그룹 배치가 6구간(20/20/20/10/10/10) — 8/18은 3구간(30/30/30)
     ③ ⭐⭐ **세션 A(학습) / B(시험지) 진행률을 따로 보여준다**
        → 시험지를 먼저 라벨링하는 것이 이번 방침이라 그 진행이 보여야 한다

⭐ `fix_labelme_shapes.py` 와 무엇이 다른가
   저것은 **"그린 모양이 유효한가"**(polygon 인가)를 본다.
   이것은 **"맞는 것을 그렸는가"**(개수·이름·그룹)를 본다. 둘 다 필요하다.

🔬 무엇을 잡나 — 전부 "조용히 틀리는" 유형이다
   ① 장당 개수 ≠ 7        → 빠뜨렸거나 겹쳐 그린 것. GT 누락은 FN, 중복은 FP.
   ② labels.txt 에 없는 이름 → 평가기가 건너뛰어 **GT에서 사라진다**(8/5 유형).
   ③ 그 그룹에 없는 부품    → 다른 그룹 이름을 잘못 고른 것.
   ④ 13_variant 개수 ≠ 2 (B그룹) → 병합 규칙 미적용.
   ⑤ 14_13 이 등장          → 병합 확정이라 이 라벨은 존재하면 안 된다.

🚨 이 스크립트는 "통과"를 쉽게 주지 않도록 짰다.
   라벨이 하나도 없으면 통과가 아니라 **에러**다(빈 폴더를 초록으로 읽는 사고 방지).

사용법:
    python check_labels_0825.py
    python check_labels_0825.py --json-dir <경로> --key <정답지>
    python check_labels_0825.py --session B     # 시험지만 검사
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

SESSION_DIR = "/data/jtm/dual_capture_0824"
DEF_JSON = os.path.join(SESSION_DIR, "label_png", "labelme_json")
DEF_KEY = os.path.join(SESSION_DIR, "group_labels_0824.json")
DEF_LABELS = os.path.join(SESSION_DIR, "label_png", "labels.txt")

PARTS_PER_SHOT = 7


def load_key(path):
    """정답지 → shot 번호별 (세션, 그룹, 기대 카운트)."""
    key = json.load(open(path, encoding="utf-8"))
    merge = {}
    for m in key.get("label_rules", {}).get("merge_pairs", []):
        for c in m["classes"]:
            merge[c] = m["label_as"]

    shot2rule = {}
    for r in key["ranges"]:
        lo, hi = r["range"]
        # 병합 적용 후의 기대 카운트 (13_variant 가 2개가 되는 것이 여기서 나온다)
        expect = Counter(merge.get(p, p) for p in r["parts"])
        for n in range(lo, hi + 1):
            shot2rule[n] = (r["session"], r["group"], expect)

    # ⭐ 장별 예외 — 정답지에 근거가 적힌 것만 인정한다
    # 🚨 여기에 넣는 순간 그 장은 검사를 통과하므로, 정답지에 **실측 근거**가
    #    없으면 넣지 않는다(예외가 쌓이면 검사기가 무의미해진다).
    exceptions = {}
    for k, v in (key.get("shot_exceptions") or {}).items():
        n = int(k)
        if n not in shot2rule:
            continue
        sess, group, expect = shot2rule[n]
        expect = Counter(expect)
        miss = v.get("missing")
        if miss:
            miss = merge.get(miss, miss)
            if expect.get(miss):
                expect[miss] -= 1
                if expect[miss] == 0:
                    del expect[miss]
        shot2rule[n] = (sess, group, expect)
        exceptions[n] = v
    return shot2rule, merge, key, exceptions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", default=DEF_JSON)
    ap.add_argument("--key", default=DEF_KEY)
    ap.add_argument("--labels", default=DEF_LABELS)
    ap.add_argument("--session", choices=["A", "B"], default=None,
                    help="이 세션만 검사 (A=학습 60장 / B=시험지 30장)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    if not files:
        raise SystemExit(
            f"🔴 라벨 JSON이 한 장도 없다: {args.json_dir}\n"
            f"   ⭐ '문제 없음'이 아니라 '아직 라벨링을 안 했다'는 뜻이다."
        )

    shot2rule, merge, key, exceptions = load_key(args.key)
    official = {l.strip() for l in open(args.labels, encoding="utf-8") if l.strip()}

    bad_count = bad_name = bad_group = bad_merge = 0
    seen = {"A": [], "B": []}
    all_labels = Counter()

    scope = f" · 세션 {args.session}만" if args.session else ""
    print(f"검사 대상 {len(files)}장  (정답지: {os.path.basename(args.key)}{scope})\n")

    for f in files:
        base = os.path.splitext(os.path.basename(f))[0]
        m = re.match(r"shot_(\d+)", base)
        if not m:
            print(f"  🔴 {base}: 파일명에서 shot 번호를 못 읽음")
            bad_name += 1
            continue
        num = int(m.group(1))

        if num not in shot2rule:
            print(f"  🔴 {base}: 정답지 범위 밖 shot")
            bad_group += 1
            continue
        sess, group, expect = shot2rule[num]

        if args.session and sess != args.session:
            continue
        seen[sess].append(num)

        shapes = json.load(open(f, encoding="utf-8"))["shapes"]
        got = Counter(s["label"].replace(".stl", "") for s in shapes)
        all_labels.update(got)
        n = sum(got.values())

        msgs = []
        # ⭐ 예외 장은 기대 개수가 다르다(정답지 shot_exceptions 근거)
        want_n = sum(expect.values())
        if n != want_n:
            msgs.append(f"개수 {n} ≠ {want_n}")
            bad_count += 1
        elif num in exceptions:
            ex = exceptions[num]
            print(f"  ⚠️ {base} [s{sess}/{group}]  예외 인정 {n}개 "
                  f"— {ex.get('missing')} 누락: {ex.get('reason', '')[:40]}")
        for lab, c in sorted(got.items()):
            if lab not in official:
                msgs.append(f"🚨미지라벨 '{lab}' (labels.txt 없음 → GT에서 사라진다)")
                bad_name += 1
            elif lab == "14_13":
                msgs.append("🚨'14_13' 등장 — 병합 확정이라 '13_variant'로 써야 한다")
                bad_merge += 1
            elif lab not in expect:
                msgs.append(f"🚨'{lab}' 은 {group}그룹에 없는 부품")
                bad_group += 1
            elif c != expect[lab]:
                msgs.append(f"'{lab}' {c}개 (기대 {expect[lab]}개)")
                bad_merge += 1
        for lab, c in sorted(expect.items()):
            if lab not in got:
                msgs.append(f"'{lab}' 누락 (기대 {c}개)")
                bad_count += 1

        if msgs:
            print(f"  🔴 {base} [s{sess}/{group}]  " + " / ".join(msgs))

    # ── 세션별 진행률 ──────────────────────────────────────────
    total = {"A": 0, "B": 0}
    for _n, (s, _g, _e) in shot2rule.items():
        total[s] += 1

    print(f"\n{'='*62}")
    for s in ("B", "A"):          # ⭐ 시험지(B)를 먼저 보여준다 — 이번 방침이 B 우선
        if args.session and s != args.session:
            continue
        done = sorted(seen[s])
        role = "시험지" if s == "B" else "학습"
        todo = [n for n in sorted(shot2rule)
                if shot2rule[n][0] == s and n not in set(done)]
        line = f"  세션 {s} ({role:3s}) : {len(done):2d} / {total[s]:2d} 장"
        if todo:
            rng = f"{todo[0]:03d}~{todo[-1]:03d}" if len(todo) > 1 else f"{todo[0]:03d}"
            line += f"   남은 shot {rng}"
        else:
            line += "   ✅ 완료"
        print(line)

    n_done = len(seen["A"]) + len(seen["B"])
    # 기대 총계 = 장별 expect 합(예외 반영). PARTS_PER_SHOT × 장수가 아니다.
    want_total = sum(sum(shot2rule[n][2].values())
                     for s in ("A", "B") for n in seen[s])
    ex_note = f" · 예외 {len(exceptions)}장 반영" if exceptions else ""
    print(f"  총 인스턴스   : {sum(all_labels.values())}  (기대 {want_total}{ex_note})")
    print(f"  개수 이상 {bad_count} / 이름 이상 {bad_name} / "
          f"그룹 이상 {bad_group} / 병합 이상 {bad_merge}")

    bad = bad_count + bad_name + bad_group + bad_merge
    if bad:
        print(f"  🔴 {bad}건 — 고치기 전에는 F1 을 믿지 말 것")
    else:
        print("  ✅ 내용 검사 통과")
        print("  ⏭️ 형식 검사(fix_labelme_shapes.py)도 돌렸는지 확인할 것 — 다른 검사다")
        if not args.session and len(seen["B"]) == total["B"]:
            print("  🎯 세션 B 완료 → 새 시험지로 F1 측정 가능 (학습 불필요)")
    print(f"{'='*62}")

    # 🚨 세션 B 오염 경고 — 학습에 쓰이면 안 된다는 것을 매번 상기시킨다
    if seen["B"]:
        print("🚨 세션 B(061~090)는 시험지다 — 재학습 데이터에 절대 포함하지 말 것")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
