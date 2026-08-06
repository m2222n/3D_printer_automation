#!/usr/bin/env python3
"""labelme 라벨의 `linestrip`/`points` 를 `polygon` 으로 되살린다.

🚨 왜 필요한가
   평가기(`real_labelme.py:129-137`)가 마스크로 만드는 것은 **`polygon`과
   `rectangle`뿐**이다. `linestrip`(열린 선)·`points`(점)는 면적이 없어
   **그 부품이 통째로 무시된다** → GT에서 빠지므로 모델이 맞게 찾아도
   **FP(오검출)로 집계되어 precision이 억울하게 떨어진다.**

⭐ 무엇을 하나
   labelme에서 폴리곤을 그리다 **첫 점으로 닫지 않고 Enter를 누르면** 선으로
   확정된다. 점들은 이미 부품 외곽을 따라가고 있으므로 **닫아주면 폴리곤이 된다.**

🔬 조용히 틀리지 않기 위한 검산 (핵심)
   점 3개 미만은 면적이 없어 복구 불가 → **버리지 않고 이름을 남겨 보고**한다.
   그리고 복구한 폴리곤의 면적을 **같은 부품의 정상 폴리곤 면적과 대조**해서
   말이 안 되면(1/5 미만 또는 5배 초과) **경고**한다. 선을 잘못 닫으면 면적이
   엉뚱해지는데, 그걸 모르고 넘어가면 F1이 조용히 왜곡된다.

사용법:
    python fix_labelme_shapes.py --dir <labelme_json 폴더>          # 검사만
    python fix_labelme_shapes.py --dir <labelme_json 폴더> --apply  # 실제 수정
"""

import argparse
import glob
import json
import os
from collections import defaultdict


def poly_area(pts: list) -> float:
    """신발끈 공식. 점 순서가 시계/반시계 어느 쪽이든 절댓값."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--apply", action="store_true", help="실제로 파일을 고친다")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        raise SystemExit(f"🔴 json 없음: {args.dir}")

    # ① 먼저 정상 폴리곤의 부품별 면적 분포를 모은다(검산 기준)
    ref = defaultdict(list)
    for f in files:
        for sh in json.load(open(f))["shapes"]:
            if sh["shape_type"] == "polygon" and len(sh["points"]) >= 3:
                ref[sh["label"]].append(poly_area(sh["points"]))

    fixed = dropped = suspicious = 0
    print(f"검사 대상 {len(files)}장  (모드: {'수정' if args.apply else '검사만'})\n")

    for f in files:
        d = json.load(open(f))
        out, changed = [], False
        for sh in d["shapes"]:
            st, pts, lab = sh["shape_type"], sh["points"], sh["label"]

            if st in ("polygon", "rectangle"):
                out.append(sh)
                continue

            # 복구 시도 — 점 3개 이상이면 닫아서 폴리곤으로
            if len(pts) >= 3:
                area = poly_area(pts)
                note = ""
                if ref.get(lab):
                    med = sorted(ref[lab])[len(ref[lab]) // 2]
                    if med > 0 and not (med / 5 <= area <= med * 5):
                        note = f"  ⚠️ 면적 {area:.0f} vs 같은부품 중앙값 {med:.0f}"
                        suspicious += 1
                sh["shape_type"] = "polygon"
                out.append(sh)
                fixed += 1
                changed = True
                print(f"  {os.path.basename(f)}: {st}({len(pts)}pts) → polygon  "
                      f"{lab}{note}")
            else:
                dropped += 1
                print(f"  🔴 {os.path.basename(f)}: {st}({len(pts)}pts) 복구불가 "
                      f"— 버림  {lab}  ⭐이 부품은 다시 그려야 함")
                changed = True

        if changed and args.apply:
            d["shapes"] = out
            json.dump(d, open(f, "w"), ensure_ascii=False)

    print(f"\n{'='*58}")
    print(f"  복구 {fixed}개 / 버림 {dropped}개 / 면적 의심 {suspicious}개")
    if suspicious:
        print("  ⚠️ 면적 의심 = 선을 잘못 닫아 모양이 엉뚱할 수 있음 → 육안 확인 권장")
    if not args.apply:
        print("  ⏭️ 실제로 고치려면 --apply 를 붙일 것")
    print(f"{'='*58}")


if __name__ == "__main__":
    main()
