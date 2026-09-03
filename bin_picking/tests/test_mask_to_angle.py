#!/usr/bin/env python3
"""회전각 산출 회귀 검사 — `mask_to_angle.py` + 러너의 각도 주입.

🚨🚨 **왜 이 파일이 필요한가 (2026-09-01)**
`mask_to_angle.py`는 7/30에 만들어졌는데 **테스트가 0건이었다.**
그런데 8/28 IPC E2E 산출물은 `angle = 0.0` 전건이었고, 그 원인을 우리는
`angle=0_mask_not_saved` 라는 문구 그대로 *"마스크가 저장되지 않아서"* 로 읽고 있었다.

⭐⭐ **9/1 실측으로 그 해석이 틀렸음이 드러났다:**
  - 추론기는 `predicted_masks.npz` 로 **마스크를 이미 저장하고 있었다**(`infer_...:349`)
  - 각도 산출 코드도 **이미 있었다**(`mask_to_angle.py`)
  - 🔴 **없던 것은 둘을 잇는 호출이었다** — 각도 주입이 **평가 스크립트에만** 있었고
    러너는 **추론기**를 부르므로 그 경로를 안 탔다.
⇒ 📌 8/21 *"평가 스크립트만 고쳤고 운영 추론은 옛 값이었다"* 와 **같은 계열.**
⇒ 📌 ***"미착수"와 "실물 검증 0회"는 다르다.*** 세어보지 않아서 3주를 오해했다.

🔴 **각도가 왜 필수인가** = 27종 중 **22종(81%)·검출 82%가 종횡비 1.5 초과**
   (`tests/survey_rotation_asymmetry.py`). 각도 없이 집을 수 있는 것은 `brkt_switch` 1종뿐.
   ⇒ `angle=0.0` 은 "회전 없음"이 아니라 **"모른다"** 이고, 그대로 집으면 어긋난 방향으로 문다.

실행: /data/jtm/depth_venv/bin/python bin_picking/tests/test_mask_to_angle.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from bin_picking.src.pipeline.mask_to_angle import (  # noqa: E402
    ASPECT_MEANINGFUL,
    angle_from_mask,
    angles_from_masks,
)

_pass = 0
_fail = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  🟢 {label}")
    else:
        _fail += 1
        print(f"  🔴 {label}" + (f"  — {detail}" if detail else ""))


def make_rect(angle_deg: float, L: float = 80, W: float = 20,
              size=(200, 200)) -> np.ndarray:
    """알려진 각도의 회전 사각형 마스크를 만든다."""
    m = np.zeros(size, np.uint8)
    box = cv2.boxPoints(((size[1] / 2, size[0] / 2), (L, W), angle_deg))
    cv2.fillPoly(m, [np.int32(box)], 1)
    return m


def angle_err(out: float, truth: float) -> float:
    """긴 축은 θ와 θ+180°가 구분되지 않는다(모듈 문서에 명시된 한계) ⇒ 180 주기로 잰다."""
    d = abs(out - truth) % 180.0
    return min(d, 180.0 - d)


# ---------------------------------------------------------------------------
print("① ⭐ 알려진 각도를 되읽는다 — 이것이 통과해야 나머지가 의미 있다")
# ---------------------------------------------------------------------------
worst = 0.0
for a in [0, 15, 30, 45, 60, 75, 90, 120, 150, 170]:
    r = angle_from_mask(make_rect(a))
    if r is None:
        check(f"{a}° 산출", False, "None 이 나왔다")
        continue
    e = angle_err(r["angle"], a)
    worst = max(worst, e)
    check(f"{a:>3}° → {r['angle']:>6.2f}° (오차 {e:.2f}°)", e <= 1.5,
          "오차 1.5° 초과")
check(f"⭐ 최대 오차 {worst:.2f}° ≤ 1.5°", worst <= 1.5)

# ---------------------------------------------------------------------------
print("\n② 🚨 정사각형 = 각도가 물리적으로 무의미하므로 reliable=False 여야 한다")
# ---------------------------------------------------------------------------
# 실제 사례 = brkt_switch 20.4×20.0mm (aspect 1.02) · 13_variant·14_13 (42.24mm 폭 쌍둥이)
r = angle_from_mask(make_rect(20, 40, 40))
check("정사각형은 reliable=False", r["angle_reliable"] is False)
check("사유를 note 에 남긴다", "정사각형" in r["angle_note"])
r = angle_from_mask(make_rect(20, 40, 30))          # aspect 1.33
check("aspect 1.33 은 reliable=True", r["angle_reliable"] is True)
check(f"경계값 상수 = {ASPECT_MEANINGFUL}", ASPECT_MEANINGFUL == 1.15)

# ---------------------------------------------------------------------------
print("\n③ 🚨🚨 마스크 결손(ToF 구멍) — 각도가 완전히 틀리는데 걸러내야 한다")
# ---------------------------------------------------------------------------
m = make_rect(30, 80, 20)
full = angle_from_mask(m)
holed = m.copy()
ys, xs = np.nonzero(holed)
idx = np.random.default_rng(0).choice(len(ys), int(len(ys) * 0.6), replace=False)
holed[ys[idx], xs[idx]] = 0
h = angle_from_mask(holed)
check(f"온전한 마스크는 정확 ({full['angle']}°, fill {full['fill']})",
      angle_err(full["angle"], 30) <= 1.5 and full["angle_reliable"])
# ⭐ 이 검사의 핵심 = 결손 마스크는 각도가 **틀린다**(30°→150°대). 값을 믿으면 안 된다.
check(f"60% 결손은 reliable=False (fill {h['fill']})",
      h["angle_reliable"] is False,
      "결손 마스크의 각도를 신뢰하면 엉뚱한 방향으로 집는다")
check("결손 사유를 note 에 남긴다", "fill" in h["angle_note"])

# ---------------------------------------------------------------------------
print("\n④ 빈/초소형/None 입력 = 값을 지어내지 말고 None")
# ---------------------------------------------------------------------------
check("빈 마스크 → None", angle_from_mask(np.zeros((50, 50), np.uint8)) is None)
check("3x3 초소형 → None", angle_from_mask(make_rect(0, 3, 3, (50, 50))) is None)
check("None 입력 → None", angle_from_mask(None) is None)
check("1D 배열 → None", angle_from_mask(np.ones(10, np.uint8)) is None)

# ---------------------------------------------------------------------------
print("\n⑤ 🚨 좌표 역변환 — 7/29 에 141px 밀린 그 부분")
# ---------------------------------------------------------------------------
r = angle_from_mask(make_rect(0, 80, 20), offset_xy=(100, 200), scale_xy=(2.0, 2.0))
cx, cy = r["obb_center_xy"]
check(f"중심이 원본 좌표로 변환된다 ({cx}, {cy})",
      abs(cx - 300.0) < 1.0 and abs(cy - 400.0) < 1.0,
      "기대 = (100 + 100*2, 200 + 100*2) = (300, 400)")
check("edge 4점이 모두 offset 이후 좌표", all(p[0] >= 100 and p[1] >= 200
                                          for p in r["edge"]))
r0 = angle_from_mask(make_rect(0, 80, 20))
check("⭐ 역변환이 각도를 바꾸지 않는다(등방 배율)",
      angle_err(r["angle"], r0["angle"]) < 0.01)

# ---------------------------------------------------------------------------
print("\n⑥ angles_from_masks — 순서가 보존되어야 한다 (짝이 밀리면 엉뚱한 부품에 붙는다)")
# ---------------------------------------------------------------------------
masks = np.stack([make_rect(0, 80, 20), make_rect(45, 80, 20),
                  make_rect(20, 40, 40)])          # 3번째는 정사각형
out = angles_from_masks(masks)
check("입력 개수 == 출력 개수", len(out) == 3)
check("1번 ≈ 0°/180°", angle_err(out[0]["angle"], 0) <= 1.5)
check("2번 ≈ 45°", angle_err(out[1]["angle"], 45) <= 1.5)
check("3번은 정사각형이라 reliable=False", out[2]["angle_reliable"] is False)

# ---------------------------------------------------------------------------
print("\n⑦ 🥇 러너 연결 — step_angle 이 실제로 예측 JSON 을 갱신하나")
#    🚨 이것이 9/1에 비어 있던 그 구멍이다. 여기가 통과해야 파지가 가능하다.
# ---------------------------------------------------------------------------
import json  # noqa: E402
import tempfile  # noqa: E402

from bin_picking.src.run_binpick_e2e import step_angle  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # 모델 입력 좌표계(=crop 안)에 놓인 마스크 2개
    masks = np.stack([make_rect(30, 80, 20, (100, 100)),
                      make_rect(20, 40, 40, (100, 100))])
    np.savez_compressed(td / "predicted_masks.npz", masks=masks.astype(np.uint8))
    pj = td / "predictions.json"
    pj.write_text(json.dumps({
        "crop_bbox_yxyx": [0, 0, 100, 100],
        "input_shape_hw": [100, 100],
        "predictions": [{"cad_id": "A"}, {"cad_id": "B"}],
    }), encoding="utf-8")

    info = step_angle(pj)
    got = json.loads(pj.read_text(encoding="utf-8"))["predictions"]
    check("주입 2건", info["injected"] == 2, str(info))
    check("실패 0건", info["failed"] == 0)
    check("skip 사유 없음", info["skipped_reason"] is None, str(info["skipped_reason"]))
    check("⭐ angle_deg 가 실제로 박힌다", got[0].get("angle_deg") is not None)
    check("obb_edge 가 박힌다", got[0].get("obb_edge") is not None)
    check("1번 각도 ≈ 30°", angle_err(got[0]["angle_deg"], 30) <= 1.5)
    check("2번(정사각형)은 reliable=False", got[1]["angle_reliable"] is False)
    check("신뢰 건수 = 1", info["reliable"] == 1, str(info))

    # 🚨 마스크 개수 불일치 = 조용히 zip 하지 말고 중단해야 한다
    pj2 = td / "p2.json"
    pj2.write_text(json.dumps({
        "crop_bbox_yxyx": [0, 0, 100, 100], "input_shape_hw": [100, 100],
        "predictions": [{"cad_id": "A"}, {"cad_id": "B"}, {"cad_id": "C"}],
    }), encoding="utf-8")
    np.savez_compressed(td / "predicted_masks.npz", masks=masks.astype(np.uint8))
    info2 = step_angle(pj2)
    check("🚨 마스크≠예측 개수면 중단한다",
          info2["injected"] == 0 and "밀릴" in (info2["skipped_reason"] or ""),
          "조용히 zip 하면 엉뚱한 부품에 각도가 붙는다")

    # npz 가 없으면 = 예외를 던지지 말고 사유를 남긴다
    pj3 = td / "sub" / "p3.json"
    pj3.parent.mkdir()
    pj3.write_text(json.dumps({"predictions": [{"cad_id": "A"}]}), encoding="utf-8")
    info3 = step_angle(pj3)
    check("npz 없으면 예외 없이 사유만 남긴다",
          info3["injected"] == 0 and info3["skipped_reason"] is not None)

# ---------------------------------------------------------------------------
print("\n⑧ 🚨🚨 러너가 step_angle 을 *실제로 호출하나* — 9/1 구멍의 본체")
#    ⭐ ⑦은 step_angle 을 직접 불러서 검사한다. 그것만으로는
#      **러너가 그 함수를 부르는지**를 검사하지 못한다(호출을 지워도 ⑦은 통과한다).
#      🚨 이것이 정확히 9/1까지 3주간 숨어 있던 형태다:
#         "함수는 있는데 아무도 부르지 않는다."
#    📌 8/13 원칙 = *"통과하는 테스트"와 "실패할 수 있는 테스트"는 다르다.*
# ---------------------------------------------------------------------------
import inspect  # noqa: E402

from bin_picking.src import run_binpick_e2e as RUNNER  # noqa: E402

src_run_one = inspect.getsource(RUNNER.run_one)
check("run_one 이 step_angle 을 호출한다",
      "step_angle(" in src_run_one,
      "🚨 함수만 있고 호출이 없으면 angle 은 전건 0.0 으로 남는다")
check("호출이 step_six 보다 먼저다(6요소가 각도를 읽어야 한다)",
      src_run_one.find("step_angle(") < src_run_one.find("step_six("),
      "순서가 뒤바뀌면 6요소가 각도 없는 예측을 읽는다")
check("요약에 각도 현황이 실린다",
      "angle_injected" in src_run_one and "angles" in src_run_one,
      "안 보이면 또 '0.0 인데 왜?' 를 반복한다")

# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"  통과 {_pass} / 실패 {_fail}")
if _fail == 0:
    print("  ✅ 회전각 산출 검증 통과")
    print("  🚨 단 이것은 **합성 마스크 + 실데이터 재현성**까지다.")
    print("     실제 파지 성공은 로봇·그리퍼로만 확인된다(9/2 현장).")
else:
    print("  🔴 실패 있음 — 현장에 들고 가기 전에 고칠 것")
print("=" * 62)
sys.exit(0 if _fail == 0 else 1)
