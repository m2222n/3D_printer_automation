#!/usr/bin/env python3
"""재학습 판별 — 조건별 결과를 모아 "진짜 올랐는가"를 판정한다.

🚨 왜 필요한가 — 숫자 하나로 배포를 결정하면 안 된다
   c1 은 10장(TP 35~39)뿐이라 4건 차이가 우연일 수 있다. 그래서
   ①**조건 3개(c1/c2/c3)가 같은 방향으로 움직이는가**
   ②**train 성적과 반대로 가는가**(과적합 신호)
   ③**위치와 종류 중 어디가 변했나**
   를 함께 본다. 하나만 오르고 나머지가 내리면 우연일 가능성이 높다.

⚠️ c3 는 기준선이 0.0000 이라 F1 로는 변화가 안 보인다 → **FP 감소**로 본다
   (부품 자리를 안 보고 배경을 잡던 것이 줄었는가).

사용법:  python compare_retrain_0819.py --log <V0819_master.log>
"""
import argparse
import re
from collections import defaultdict

BASE = {"c1": 0.4070, "c2": 0.0814, "c3": 0.0000}


def parse(path):
    """master 로그 → {tag: {cond: dict}}"""
    res = defaultdict(dict)
    tag = None
    tag_re = re.compile(r"\[([A-Za-z0-9_]+)\] 조건별 평가")
    row_re = re.compile(
        r"(c1|c2|c3|0818)\s+F1 ([\d.]+)\s+P ([\d.]+)\s+R ([\d.]+)\s+"
        r"\(TP (\d+) FP (\d+) FN (\d+)\)")
    for line in open(path, encoding="utf-8"):
        m = tag_re.search(line)
        if m:
            tag = m.group(1)
            continue
        m = row_re.search(line)
        if m and tag:
            c, f1, p, r, tp, fp, fn = m.groups()
            res[tag][c] = dict(f1=float(f1), p=float(p), r=float(r),
                               tp=int(tp), fp=int(fp), fn=int(fn))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    args = ap.parse_args()
    res = parse(args.log)
    if "BASE" not in res:
        raise SystemExit("🔴 BASE(기준선)가 로그에 없다 — 비교 불가")
    base = res["BASE"]

    print("=" * 78)
    print(" 조건별 F1 (기준선 대비 증감)")
    print("=" * 78)
    print(f"  {'모델':<18}{'c1(실운영)':>16}{'c2(테두리)':>16}{'c3(바닥)':>14}{'0818(train)':>14}")
    for tag, d in res.items():
        row = f"  {tag:<18}"
        for c in ("c1", "c2", "c3", "0818"):
            if c not in d:
                row += f"{'-':>16}"
                continue
            v = d[c]["f1"]
            if tag == "BASE":
                row += f"{v:>16.4f}"
            else:
                dv = v - base.get(c, {}).get("f1", 0)
                mark = "+" if dv > 0 else ""
                row += f"{v:>10.4f}({mark}{dv:.3f})"[-16:].rjust(16)
        print(row)

    print()
    print("=" * 78)
    print(" 🚨 판정 — 우연이 아니려면 여러 조건이 같은 방향이어야 한다")
    print("=" * 78)
    for tag, d in res.items():
        if tag == "BASE":
            continue
        ups = sum(1 for c in ("c1", "c2")
                  if c in d and d[c]["f1"] > base[c]["f1"] + 1e-9)
        downs = sum(1 for c in ("c1", "c2")
                    if c in d and d[c]["f1"] < base[c]["f1"] - 1e-9)
        c3fp = d.get("c3", {}).get("fp")
        c3base = base.get("c3", {}).get("fp")
        c3note = ""
        if c3fp is not None and c3base:
            c3note = f" · c3 헛검출 {c3base}→{c3fp}"
            if c3fp < c3base:
                c3note += " 🟢"
        train = d.get("0818", {}).get("f1", 0)
        over = " ⚠️train↑인데 실측↓ = 과적합" if (train > base["0818"]["f1"] + 0.2
                                                and ups == 0) else ""
        verdict = ("🟢 개선(c1·c2 동반)" if ups == 2 else
                   "🟡 c1만 개선(표본 작아 확정 못함)" if ups == 1 and downs == 0 else
                   "🔴 악화" if downs else "⬜ 변화 없음")
        print(f"  {tag:<18}{verdict}{c3note}{over}")

    print()
    print("  ⭐ c1 은 10장(TP 35 전후)이라 4~5건 차이는 우연일 수 있다.")
    print("     **c1 과 c2 가 함께 올라야** 진짜 개선으로 본다.")
    print("  ⚠️ c3 는 기준선 0.0000 이라 F1 로는 안 보인다 → FP 감소로 판단.")


if __name__ == "__main__":
    main()
