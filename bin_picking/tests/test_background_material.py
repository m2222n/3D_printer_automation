#!/usr/bin/env python3
"""`check_background_material.py` 검증.

⭐⭐ 8/7 교훈을 그대로 적용한다 — **손으로 만든 입력만으로는 부족하다.**
그날 게이트 키 이름을 `valid_pct`로 추측해 쓴 버그를 테스트가 못 잡았는데,
이유는 **가짜 dict가 코드와 같은 오타를 공유**했기 때문이다
(테스트와 코드가 같이 틀리면 통과한다).

⇒ 그래서 이 파일은 **진짜 촬영 데이터(c1/c2/c3 30장)를 돌려 교차 검증**한다.
   ⭐ 판정 기준이 실제 F1 결과와 일치하는지가 이 도구의 존재 이유이므로
   그것을 직접 확인하는 것이 유일하게 의미 있는 검사다.

🚨 이 파일을 만들면서 실제로 잡은 버그 = `raw_to_m`이라는 **없는 함수 이름을 추측**해 썼다.
   실제는 `raw_to_mm`. 시그니처는 추측하지 말고 확인하라는 원칙(8/5 세 번·8/7 두 번)의
   여섯 번째 사례다.

실행: /data/jtm/depth_venv/bin/python tests/test_background_material.py
"""

from __future__ import annotations

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_background_material import (  # noqa: E402
    BASELINE,
    BASELINE_DIR,
    PART_RANGE_M,
    load_shots,
    part_band_pct,
    summarize,
    verdict_line,
)
from src.acquisition.depth_units import raw_to_mm  # noqa: E402
from src.pipeline.input_gate import scene_valid_ratio_pct  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def load_cond(cond: str) -> list[tuple[str, np.ndarray]]:
    files = sorted(glob.glob(os.path.join(BASELINE_DIR, f"shot_*_{cond}.npy")))
    return [(os.path.basename(f), np.load(f)) for f in files]


def main() -> int:
    print("=" * 66)
    print("배경재 판정 도구 검증")
    print("=" * 66)

    # ── 1. 단위 변환 — 물리 검산 (아는 값으로 왕복 대조)
    print("\n[1] 단위 변환")
    # raw = 65535일 때 10m = 10000mm 라는 규약
    check("raw 65535 → 10000mm",
          abs(float(raw_to_mm(np.array([65535]))[0]) - 10000.0) < 1.0)
    # 450mm는 학습 대역 한가운데 → raw로 약 2949
    raw_450 = 450.0 / 1000.0 / 10.0 * 65535.0
    back = float(raw_to_mm(np.array([raw_450]))[0])
    check("450mm 왕복 대조", abs(back - 450.0) < 1.0, f"실제 {back:.1f}mm")

    # ── 2. 부품 대역이 실제로 400~600mm를 재는가
    print("\n[2] 부품 대역 계산")
    lo_raw = int(0.45 / 10.0 * 65535)      # 450mm = 대역 안
    hi_raw = int(1.50 / 10.0 * 65535)      # 1500mm = 대역 밖
    inside = np.full((10, 10), lo_raw, dtype=np.uint16)
    outside = np.full((10, 10), hi_raw, dtype=np.uint16)
    check("450mm 전면 → 100%", abs(part_band_pct(inside) - 100.0) < 0.01)
    check("1500mm 전면 → 0%", abs(part_band_pct(outside) - 0.0) < 0.01)
    check("PART_RANGE_M이 평가 파이프라인과 같다(0.40,0.60)",
          PART_RANGE_M == (0.40, 0.60), f"실제 {PART_RANGE_M}")

    # ── 3. ⭐⭐ 실데이터 교차 검증 — 이 도구의 존재 이유
    print("\n[3] ⭐ 실데이터 30장 교차 검증 (손으로 만든 입력이 아님)")
    if not os.path.isdir(BASELINE_DIR):
        print(f"  ⚠️ 원본이 없어 건너뜀: {BASELINE_DIR}")
    else:
        summ = {}
        for cond in ("c1", "c2", "c3"):
            shots = load_cond(cond)
            check(f"{cond} 10장 로드", len(shots) == 10, f"실제 {len(shots)}장")
            if shots:
                summ[cond] = summarize(cond, shots)

        # 문서에 기록된 수치를 정확히 재현하는가
        # 🚨 이 재현이 없으면 판정이 바뀌었을 때 도구 탓인지 데이터 탓인지 못 가른다
        print("\n  [3-1] 문서값 재현 (기준선이 살아있는가)")
        for key, (lo, med, hi, _) in BASELINE.items():
            cond = key.split()[0]
            if cond not in summ:
                continue
            s = summ[cond]
            check(f"{cond} min {lo:.2f}%", abs(s["ratio_min"] - lo) < 0.05,
                  f"실제 {s['ratio_min']:.2f}%")
            check(f"{cond} max {hi:.2f}%", abs(s["ratio_max"] - hi) < 0.05,
                  f"실제 {s['ratio_max']:.2f}%")

        # ⭐⭐ 핵심 주장 = 판정이 실제 F1 결과와 일치하는가
        print("\n  [3-2] ⭐ 판정이 실제 F1과 일치하는가 (도구의 존재 이유)")
        if "c1" in summ:
            check("c1(F1 0.4070)은 10/10 통과",
                  summ["c1"]["n_in"] == 10, f"실제 {summ['c1']['n_in']}/10")
            check("c1 판정이 🟢 통과", "🟢" in verdict_line(summ["c1"]),
                  verdict_line(summ["c1"]))
        if "c2" in summ:
            check("c2(F1 0.0814)는 0/10 통과",
                  summ["c2"]["n_in"] == 0, f"실제 {summ['c2']['n_in']}/10")
        if "c3" in summ:
            check("c3(F1 0.0000)은 0/10 통과",
                  summ["c3"]["n_in"] == 0, f"실제 {summ['c3']['n_in']}/10")

        # 🚨 부품이 안 보이면 통과여도 실패로 잡는가
        print("\n  [3-3] 부품 대역 — '배경만 깨끗하고 부품이 없는' 화면을 거르는가")
        if "c1" in summ:
            check("c1은 부품 대역이 실재한다(>1%)",
                  summ["c1"]["part_med"] > 1.0, f"실제 {summ['c1']['part_med']:.2f}%")

    # ── 4. 부품이 안 보이는 화면은 통과여도 🔴
    print("\n[4] '유효율은 통과인데 부품이 없는' 화면")
    # 유효율 5%(=c1 대역)지만 전부 1500mm → 부품 대역 0%
    empty = np.zeros((100, 100), dtype=np.uint16)
    empty[:5, :] = hi_raw            # 5% 유효, 전부 대역 밖
    s = summarize("가짜", [("f.npy", empty)])
    check("유효율은 학습 분포 안", 2.0 <= s["ratio_med"] <= 25.0,
          f"실제 {s['ratio_med']:.2f}%")
    check("⭐ 그래도 🔴 실패로 판정", "🔴" in verdict_line(s), verdict_line(s))

    # ── 5. 빈 입력에서 죽지 않는가
    print("\n[5] 경계 입력")
    check("빈 배열 → 0%", scene_valid_ratio_pct(np.array([])) == 0.0)
    check("전부 0(무효) → 0%",
          scene_valid_ratio_pct(np.zeros((10, 10), dtype=np.uint16)) == 0.0)

    print()
    print("=" * 66)
    print(f"결과: {PASS} 통과 / {FAIL} 실패")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
