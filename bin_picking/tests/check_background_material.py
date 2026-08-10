#!/usr/bin/env python3
"""배경재 판정 — 이 바닥재를 깔고 찍은 화면이 학습 때와 같은 구성인가.

⭐ 왜 이게 필요한가 (2026-08-10)
------------------------------------------------------------
8/7 재학습이 실패해서(c1 7장 추가 → holdout F1 0.4231→0.2917 과적합)
**모델을 손보는 경로가 막혔고 재촬영만 남았다.** 재촬영은 "학습 때와 같은
화면 구성"을 만들어야 의미가 있고, 그 화면을 만드는 것이 **배경재**다.

🚨 **눈으로는 고를 수 없다.** 가시광 차광 ≠ 850nm 흡수다. 검게 보여도
근적외선을 반사하면 배경이 depth로 채워져 c3(F1 0.0000)가 된다.
⇒ **깔고 찍어서 수치로 판정**하는 것이 유일한 방법이고, 이 스크립트가 그것이다.

무엇을 재나 = 유효 픽셀 비율(depth > 0)
------------------------------------------------------------
8/5 cross-session 30장 실측(재현 확인 완료, 2026-08-10):

  c1 (택배상자 안)    4.27 ~  7.50%  (중앙 5.44)  F1 0.4070  ✅ 학습 분포 안
  c2 (상자 테두리)   24.90 ~ 38.25%  (중앙 30.20) F1 0.0814  🟠 박스를 부품으로 오인
  c3 (흰 테이블)     80.04 ~ 94.74%  (중앙 91.05) F1 0.0000  🔴 부품 자리를 안 봄

⭐ **배경재가 하는 일** = 배경을 depth상 "안 보이게" 만들어 c1 상태를 재현하는 것.
   c1이 잘 됐던 이유는 상자 밖 바닥이 depth를 거의 안 돌려줬기 때문이고,
   그것이 곧 학습 조건이었다.

🚨 유효율은 "높으면 나쁘다"가 아니다
------------------------------------------------------------
8/5에 *"유효율이 결정 변수(c1 5.6%→c3 89%)"* 라고 썼던 것은 **결과적 상관이지
인과가 아니었다.** 진짜 변수는 **"학습 때와 같은 화면 구성인가"**이고,
유효율은 그것을 재는 대리 지표다.
  → 실제로 ROI로 부품만 꽉 채우면 c1도 31.5%까지 올라간다(그래도 좋은 화면이다).
  → 그래서 이 스크립트는 **전체 프레임**을 기준으로 재고, 크롭하지 않는다.
     학습이 본 화면이 전체 프레임이기 때문이다.

⚠️ 이 스크립트가 답하지 않는 것
------------------------------------------------------------
- **F1이 얼마나 나오는가** — 그건 라벨링을 해야 안다. 여기서는
  "학습 분포 안에 들어오는가"만 판정한다. 통과가 곧 성능 보장은 아니다.
- **부품이 잘 보이는가** — 배경이 사라져도 부품이 안 잡히면 소용없다.
  그래서 부품 대역(400~600mm) 픽셀 수를 함께 낸다. ⭐이게 0이면 통과여도 실패다.

사용법
------------------------------------------------------------
  # 후보 하나 판정 (해당 폴더의 .npy 전부)
  python tests/check_background_material.py /path/to/차광용지_촬영/

  # 후보 여러 개 비교
  python tests/check_background_material.py 후보A/ 후보B/ --labels 차광용지 무광시트

  # 기준선(c1/c2/c3)을 같이 보고 싶을 때
  python tests/check_background_material.py 후보A/ --with-baseline
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.acquisition.depth_units import raw_to_mm  # noqa: E402
from src.pipeline.input_gate import (  # noqa: E402
    VALID_RATIO_TRAIN_MAX,
    VALID_RATIO_TRAIN_MIN,
    VALID_RATIO_WARN,
    check_scene,
)

# 8/5 실측 기준선 — 2026-08-10에 원본 30장으로 재현 확인함
BASELINE = {
    "c1 (택배상자 안·학습조건)": (4.27, 5.44, 7.50, "F1 0.4070 ✅"),
    "c2 (상자 테두리 노출)": (24.90, 30.20, 38.25, "F1 0.0814 🟠"),
    "c3 (흰 테이블 직접)": (80.04, 91.05, 94.74, "F1 0.0000 🔴"),
}
BASELINE_DIR = "/data/jtm/blaze_crosssession_0731"

# 부품 대역 — 평가 파이프라인의 --depth_keep_range 0.40,0.60 과 같은 값을 쓴다.
# 🚨 이 범위 밖이면 평가에서 부품 픽셀이 전부 버려져 검출 0건이 된다.
PART_RANGE_M = (0.40, 0.60)


def part_band_pct(depth_raw: np.ndarray) -> float:
    """부품 대역(400~600mm)에 들어오는 픽셀 비율(%).

    ⚠️ 단위 — 입력은 Blaze raw uint16이고 변환은 `depth_units.raw_to_mm` 하나만 쓴다.
       (단위를 손으로 계산했다가 닷새에 다섯 번 틀린 이력이 있어 단일 출처를 강제한다.
        🚨 이 파일에서도 처음에 `raw_to_m`이라는 없는 이름을 추측해 썼다가 잡았다.)
    """
    mm = raw_to_mm(np.asarray(depth_raw))
    lo_mm, hi_mm = PART_RANGE_M[0] * 1000.0, PART_RANGE_M[1] * 1000.0
    return float(((mm >= lo_mm) & (mm <= hi_mm)).mean() * 100.0)


def load_shots(path: str) -> list[tuple[str, np.ndarray]]:
    if os.path.isfile(path):
        return [(os.path.basename(path), np.load(path))]
    files = sorted(glob.glob(os.path.join(path, "*.npy")))
    return [(os.path.basename(f), np.load(f)) for f in files]


def summarize(name: str, shots: list[tuple[str, np.ndarray]]) -> dict:
    ratios = [check_scene(d)["valid_ratio_pct"] for _, d in shots]
    parts = [part_band_pct(d) for _, d in shots]
    verdicts = [check_scene(d)["verdict"] for _, d in shots]

    n_in = verdicts.count("in_distribution")
    return {
        "name": name,
        "n": len(shots),
        "ratio_min": min(ratios),
        "ratio_med": float(np.median(ratios)),
        "ratio_max": max(ratios),
        "part_med": float(np.median(parts)),
        "n_in": n_in,
        "pass_pct": 100.0 * n_in / len(shots) if shots else 0.0,
        "verdicts": verdicts,
    }


def verdict_line(s: dict) -> str:
    """판정 = 학습 분포 통과율 + 부품이 실제로 보이는가.

    ⭐ 두 조건을 모두 봐야 한다. 배경이 완벽히 사라져도(유효율 낮음)
       부품까지 안 잡히면 촬영 자체가 실패다.
    """
    if s["part_med"] < 0.5:
        return ("🔴 실패 — 부품 대역 픽셀이 거의 없다"
                f"({s['part_med']:.2f}%). 배경 이전에 카메라가 부품을 못 보고 있다"
                " (거리·화각 확인)")
    if s["pass_pct"] >= 80:
        return f"🟢 통과 — {s['n_in']}/{s['n']}장이 학습 분포 안. 이 배경재를 쓸 수 있다"
    if s["pass_pct"] >= 50:
        return (f"🟡 경계 — {s['n_in']}/{s['n']}장만 통과."
                " 조명·각도를 바꿔 재촬영하거나 다른 후보와 비교할 것")
    return (f"🔴 부적합 — {s['n_in']}/{s['n']}장만 통과."
            " 배경이 depth로 채워지고 있다(c2·c3 조건)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="촬영 .npy 파일 또는 폴더")
    ap.add_argument("--labels", nargs="*", default=None, help="후보 이름(순서대로)")
    ap.add_argument("--with-baseline", action="store_true",
                    help=f"기준선 c1/c2/c3를 실제로 다시 계산해 함께 표시 ({BASELINE_DIR})")
    args = ap.parse_args()

    labels = args.labels or [os.path.basename(p.rstrip("/")) for p in args.paths]
    if len(labels) != len(args.paths):
        print(f"🚨 --labels 개수({len(labels)})가 경로 개수({len(args.paths)})와 다르다")
        return 2

    print("=" * 78)
    print("배경재 판정 — 학습 때와 같은 화면 구성인가")
    print("=" * 78)
    print(f"판정 기준: 유효율 {VALID_RATIO_TRAIN_MIN}~{VALID_RATIO_TRAIN_MAX}% "
          f"(경고 {VALID_RATIO_WARN}%) · 부품 대역 "
          f"{PART_RANGE_M[0]*1000:.0f}~{PART_RANGE_M[1]*1000:.0f}mm")
    print()
    print("📌 8/5 실측 기준선 (문서값)")
    for k, (lo, med, hi, f1) in BASELINE.items():
        print(f"   {k:24s} {lo:5.2f} ~ {hi:5.2f}%  (중앙 {med:5.2f})  {f1}")
    print()

    rows = []

    if args.with_baseline:
        if not os.path.isdir(BASELINE_DIR):
            print(f"⚠️ 기준선 원본이 없다: {BASELINE_DIR} — --with-baseline 건너뜀\n")
        else:
            for cond in ("c1", "c2", "c3"):
                files = sorted(glob.glob(os.path.join(BASELINE_DIR, f"shot_*_{cond}.npy")))
                if files:
                    shots = [(os.path.basename(f), np.load(f)) for f in files]
                    rows.append(summarize(f"[기준선] {cond}", shots))

    for path, label in zip(args.paths, labels):
        shots = load_shots(path)
        if not shots:
            print(f"🚨 {label}: .npy가 없다 — {path}")
            continue
        rows.append(summarize(label, shots))

    if not rows:
        print("🚨 판정할 촬영이 없다")
        return 1

    print(f"{'후보':<24} {'n':>3} {'유효율 min~max':>18} {'중앙':>7} "
          f"{'부품대역':>8} {'통과':>9}")
    print("-" * 78)
    for s in rows:
        rng = f"{s['ratio_min']:.2f}~{s['ratio_max']:.2f}%"
        print(f"{s['name']:<24} {s['n']:>3} {rng:>18} {s['ratio_med']:>6.2f}% "
              f"{s['part_med']:>7.2f}% {s['n_in']:>4}/{s['n']:<4}")

    print()
    for s in rows:
        if s["name"].startswith("[기준선]"):
            continue
        print(f"  {s['name']}: {verdict_line(s)}")

    print()
    print("⚠️ 이 판정은 '학습 분포 안에 들어오는가'까지만 답한다.")
    print("   F1이 얼마나 나오는지는 라벨링을 해야 알 수 있다(통과 ≠ 성능 보장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
