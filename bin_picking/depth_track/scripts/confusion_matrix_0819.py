#!/usr/bin/env python3
"""예측↔GT를 위치로 짝지어 "무엇을 무엇으로 틀렸나"를 센다.

⭐ 왜 필요한가
   F1 하나로는 **어디를 고쳐야 하는지** 알 수 없다. 위치는 거의 완벽한데
   (위치 F1 0.889) 종류가 57%라면, 남은 일은 **어느 쌍이 서로 헷갈리는가**다.

🔬 판정 방법 — 평가기와 같은 기준으로 짝짓는다
   bbox IoU >= 0.25(평가기 --iou_thresh 와 동일)로 greedy 매칭하고,
   짝지어진 쌍에서만 (GT label, pred label) 을 센다.
   ⚠️ 마스크가 아니라 bbox IoU 를 쓰므로 평가기 TP 와 완전히 같지는 않다.
      목적이 "혼동 구조 파악"이지 지표 재현이 아니라서 이 근사가 타당하다.
      (검산: 대각합이 평가기 TP 와 크게 어긋나면 경고한다)

🚨 혼동쌍을 해석할 때 — bbox 치수차로 판정하지 말 것 (2026-08-19 교훈)
   8/19 에 06↔03(bbox 최대차 3.8mm) · 02↔01(3.3mm) 을 보고 *"450mm 에서 2~3픽셀이라
   원리적으로 구별 불가"* 라고 판정했는데 **틀렸다.**
   태민님 지적 = *"03과 06의 차이는 약간 삐죽 튀어나온 부분이고, 01과 02의 차이는
   가운데 구멍 차이"* → STL top-down 렌더로 확인:
     · 03 vs 06 : 실루엣 자체가 다르다(06 은 왼쪽으로 뻗은 날개 + 세로 슬롯 3개)
     · 01 vs 02 : 02 가운데에 약 7x12px 사각 구멍 + 한 단 낮은 면
   실측도 뒷받침 — 촬영분에서 네 부품 모두 39~47px 로 잡히고 높이 기복 20~36mm.
   ⇒ ⭐⭐ **bbox 는 형상을 세 숫자로 요약하면서 구별 근거를 통째로 버린다.**
      이 혼동들은 원리적 한계가 아니라 **재학습으로 개선될 여지가 있다.**

   🟢 여전히 "원리적 불가"가 맞는 것 = 13_variant ↔ 14_13
      긴변 1.65mm 차인데 **형상·구멍·돌출이 전부 동일**하고 파지 파라미터도 같다.
      (그래서 이 쌍만 평가기 EQUIVALENT_CAD_NAMES 에 넣었다)

사용법:
    python confusion_matrix_0819.py [--eval-dir <dir>] [--top 20]
"""
import argparse
import collections
import glob
import json
import os

DEF_EVAL = "/data/jtm/synth_out/blaze_capture_0818_eval"
DEF_META = "/data/jtm/synth_out/blaze_capture_0818/capture_meta.json"


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


def canon(name):
    """cad_id 의 해시 접미사를 떼어 GT label 과 같은 형태로 만든다."""
    n = str(name).replace(".stl", "")
    return n.split("__", 1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", default=DEF_EVAL)
    ap.add_argument("--meta", default=DEF_META)
    ap.add_argument("--iou", type=float, default=0.25)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    meta = {}
    if os.path.exists(args.meta):
        meta = json.load(open(args.meta, encoding="utf-8"))["shots"]

    files = sorted(glob.glob(os.path.join(args.eval_dir, "predictions", "*.json")))
    if not files:
        raise SystemExit(f"🔴 predictions 없음: {args.eval_dir}")

    conf = collections.Counter()        # (gt, pred) -> n
    gt_total = collections.Counter()
    missed = collections.Counter()      # 짝이 없는 GT (FN)
    spurious = collections.Counter()    # 짝이 없는 예측 (FP)
    per_group = collections.defaultdict(lambda: collections.Counter())

    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        stem = os.path.splitext(os.path.basename(f))[0]
        grp = meta.get(stem, {}).get("group", "?")
        preds = d.get("predictions", [])
        gts = d.get("ground_truth", [])

        # greedy: IoU 큰 쌍부터
        cand = []
        for gi, g in enumerate(gts):
            for pi, p in enumerate(preds):
                v = iou(g["bbox_xyxy"], p["bbox_xyxy"])
                if v >= args.iou:
                    cand.append((v, gi, pi))
        cand.sort(reverse=True)
        ug, up = set(), set()
        for v, gi, pi in cand:
            if gi in ug or pi in up:
                continue
            ug.add(gi); up.add(pi)
            gl = canon(gts[gi].get("cad_name") or gts[gi].get("raw_label"))
            pl = canon(preds[pi].get("cad_id"))
            conf[(gl, pl)] += 1
            per_group[grp][("hit" if gl == pl else "miss")] += 1

        for gi, g in enumerate(gts):
            gl = canon(g.get("cad_name") or g.get("raw_label"))
            gt_total[gl] += 1
            if gi not in ug:
                missed[gl] += 1
                per_group[grp]["unmatched_gt"] += 1
        for pi, p in enumerate(preds):
            if pi not in up:
                spurious[canon(p.get("cad_id"))] += 1
                per_group[grp]["unmatched_pred"] += 1

    matched = sum(conf.values())
    correct = sum(n for (g, p), n in conf.items() if g == p)
    print(f"검사 {len(files)}장 · 위치로 짝지어진 쌍 {matched} · 종류 일치 {correct} "
          f"({100*correct/matched:.1f}%)\n")

    # ── 부품별 정답률 (낮은 것부터) ──────────────────────────────
    print("=" * 74)
    print(" 부품별 — 위치는 찾았는데 종류를 맞췄나 (낮은 것부터)")
    print("=" * 74)
    print(f"  {'부품':<30}{'GT':>4}{'매칭':>6}{'정답':>6}{'정답률':>8}  주된 오인")
    rows = []
    for lab, tot in gt_total.items():
        m = sum(n for (g, _), n in conf.items() if g == lab)
        c = conf.get((lab, lab), 0)
        wrong = [(n, p) for (g, p), n in conf.items() if g == lab and p != lab]
        wrong.sort(reverse=True)
        rows.append((c / m if m else -1, lab, tot, m, c, wrong))
    rows.sort()
    for acc, lab, tot, m, c, wrong in rows:
        w = ", ".join(f"{p}×{n}" for n, p in wrong[:2]) if wrong else "-"
        a = f"{100*acc:.0f}%" if m else "  -"
        print(f"  {lab:<30}{tot:>4}{m:>6}{c:>6}{a:>8}  {w}")

    # ── 혼동쌍 ──────────────────────────────────────────────────
    print()
    print("=" * 74)
    print(f" 혼동쌍 상위 {args.top} (GT → 예측)")
    print("=" * 74)
    wrong = [((g, p), n) for (g, p), n in conf.items() if g != p]
    wrong.sort(key=lambda x: -x[1])
    for (g, p), n in wrong[:args.top]:
        back = conf.get((p, g), 0)
        mark = "  ⇄ 양방향" if back else ""
        print(f"  {n:>3}회  {g:<28} → {p}{mark}")
    if not wrong:
        print("  (없음)")

    # ── 못 찾은 것 / 헛 검출 ────────────────────────────────────
    print()
    print("=" * 74)
    print(" 아예 못 찾은 GT (위치 매칭 실패 = FN)")
    print("=" * 74)
    for lab, n in missed.most_common(12):
        print(f"  {n:>3}개  {lab}   (GT {gt_total[lab]}개 중 {100*n/gt_total[lab]:.0f}%)")
    print()
    print("=" * 74)
    print(" 대응 GT 없는 예측 (헛 검출 = FP)")
    print("=" * 74)
    for lab, n in spurious.most_common(12):
        print(f"  {n:>3}개  {lab}")

    print()
    print("=" * 74)
    print(" 그룹별")
    print("=" * 74)
    for grp in ("B", "C", "A", "?"):
        c = per_group.get(grp)
        if not c:
            continue
        m = c["hit"] + c["miss"]
        print(f"  {grp}: 매칭 {m} · 종류정답 {c['hit']} ({100*c['hit']/m:.0f}%) "
              f"· 못찾음 {c['unmatched_gt']} · 헛검출 {c['unmatched_pred']}")


if __name__ == "__main__":
    main()
