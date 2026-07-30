#!/usr/bin/env python3
"""cross-session 촬영 스크립트 오프라인 검증 — 카메라 없이.

⭐ 왜 필요한가
--------------
내일(7/31) 공장에서 이 스크립트가 터지면 **촬영을 못 하고, 촬영을 못 하면 그날
전체가 무의미해진다**(cross-session 검증의 유일한 전제). 카메라는 맥에 있어 여기서
실행 검증이 안 되므로, **카메라가 필요 없는 부분을 실측 npy로 전부 검증**한다.

7/29 교훈 = "값이 자연스러워 보여도 물리 검산할 것". 게이지가 그럴싸한 숫자를
띄우면서 틀리면 현장에서 잘못 찍고도 모른다.

실행: .venv/binpick/bin/python bin_picking/tests/test_capture_crosssession_offline.py
"""
from __future__ import annotations
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "bin_picking/depth_track/scripts/blaze_capture_crosssession.py"
REAL_NPY = Path("/data/jtm/synth_out/real_capture100/npy")

_pass = _fail = 0


def check(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ✅ {name}")
    else:
        _fail += 1; print(f"  ❌ {name}  {detail}")


# 스크립트를 모듈로 로드 (pypylon import는 실패해도 되게 스텁을 넣는다)
class _Stub:
    def __getattr__(self, k):
        return _Stub()

    def __call__(self, *a, **kw):
        return _Stub()


if "pypylon" not in sys.modules:
    sys.modules["pypylon"] = _Stub()
    sys.modules["pypylon.pylon"] = _Stub()

spec = importlib.util.spec_from_file_location("cap", SCRIPT)
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)

print("\n=== 0. 학습셋과 일치해야 하는 상수 ===")
# 근거: reproduce_f1_0684.sh:54 --depth_keep_range '0.40,0.60'
check("KEEP_RANGE_MM = (400,600)", cap.KEEP_RANGE_MM == (400, 600), str(cap.KEEP_RANGE_MM))
# 근거: reproduce_f1_0684.sh:53 --center_crop '1/6,5/6'
check("CENTER_CROP = (1/6,5/6)",
      abs(cap.CENTER_CROP[0] - 1/6) < 1e-9 and abs(cap.CENTER_CROP[1] - 5/6) < 1e-9,
      str(cap.CENTER_CROP))

print("\n=== 1. center_crop = 평가와 동일 영역인가 ===")
d = np.zeros((480, 848), np.uint16)
crop, (x0, y0, x1, y1) = cap.center_crop_view(d)
check("crop 좌표 (141,80)~(706,400)", (x0, y0) == (141, 80) and (x1, y1) == (706, 400),
      f"({x0},{y0})~({x1},{y1})")
# ⚠️ 7/29에 이 역변환을 빼먹으면 141px 밀린다는 것을 확인했다. 같은 값이어야 한다.
check("crop 크기 = 565x320", crop.shape == (320, 565), str(crop.shape))

print("\n=== 2. keep_range_stats — 합성 케이스로 물리 검산 ===")
# 🔴 입력은 **raw uint16**이다(mm가 아님). raw = mm / 1000 * 65535 / 10
#    ⚠️ 이 테스트를 처음엔 raw=mm로 잘못 썼다가 실패했고, 그게 스크립트의 실제
#       단위 버그를 잡아냈다. 검산: raw 3022 → 461mm.
mm2raw = lambda mm: int(round(mm / 1000.0 * 65535 / 10.0))  # noqa: E731
check("mm2raw 검산 (461mm ≈ raw 3022)", abs(mm2raw(461) - 3022) <= 2, str(mm2raw(461)))

# ⭐ 부품이 대역 안(500mm) + crop 안
d = np.zeros((480, 848), np.uint16)
d[200:300, 300:500] = mm2raw(500)
n, pct, allp, med = cap.keep_range_stats(d)
check("대역 내 픽셀 수 = 20000", n == 20000, str(n))
check("중앙값 ≈500mm", abs(med - 500) <= 2, str(med))

# 🔴 부품이 crop 밖에만 있는 경우 → 평가에서 잘리므로 0으로 나와야 한다
d2 = np.zeros((480, 848), np.uint16)
d2[10:60, 10:100] = mm2raw(500)    # 좌상단 = crop 밖
n2, _, _, _ = cap.keep_range_stats(d2)
check("crop 밖 부품은 0으로 셈 (평가와 일치)", n2 == 0, str(n2))

# 🔴 7/29 재택 실패 재현: 물체가 4.1m(커튼)에 있는 경우
d3 = np.full((480, 848), mm2raw(4100), np.uint16)
n3, _, _, med3 = cap.keep_range_stats(d3)
check("z=4100mm이면 대역 픽셀 0 (7/29 실패 감지)", n3 == 0, str(n3))
check("중앙값이 ≈4100mm로 보고됨", abs(med3 - 4100) <= 5, str(med3))

# depth가 전부 0(무효)인 경우 죽지 않아야 한다
n4, pct4, allp4, med4 = cap.keep_range_stats(np.zeros((480, 848), np.uint16))
check("전부 무효여도 예외 없음", n4 == 0 and med4 == 0)

print("\n=== 3. 실측 npy로 검증 (어제 찍은 100장) ===")
if not REAL_NPY.exists():
    print(f"  ⏭️  {REAL_NPY} 없음 — 건너뜀")
else:
    files = sorted(REAL_NPY.glob("shot*.npy"))[:20]
    oks = 0
    meds = []
    for f in files:
        depth = np.load(f)
        n, pct, allp, med = cap.keep_range_stats(depth)
        ok = (n > 8000) and (400 <= med <= 900)
        oks += 1 if ok else 0
        meds.append(med)
    print(f"  20장 중 OK 판정: {oks}장 / 중앙값 범위 {min(meds)}~{max(meds)}mm")
    # ⭐ 학습셋은 400~600mm에서 찍은 것이므로 대부분 OK여야 한다.
    #    OK가 0장이면 게이지 임계가 잘못된 것 = 내일 현장에서 전부 ".." 로 보임
    check("학습셋이 OK로 판정됨 (임계값 타당)", oks >= 15, f"{oks}/20")
    check("중앙값이 부품 대역", all(300 <= m <= 900 for m in meds), f"{min(meds)}~{max(meds)}")

    # colorize가 실측에서 죽지 않는지 + 대역 강조가 실제로 되는지
    depth = np.load(files[0])
    vis = cap.colorize(depth)
    check("colorize 출력 형상 (H,W,3)", vis.shape == (*depth.shape, 3), str(vis.shape))
    band = (depth >= 400) & (depth <= 600)
    if band.any():
        # 대역은 컬러(채널별로 다름), 대역 밖은 회색(3채널 동일)이어야 한다
        bp = vis[band]
        colored = (bp.max(axis=1) != bp.min(axis=1)).mean()
        check("대역 픽셀이 컬러로 강조됨", colored > 0.5, f"{colored:.2f}")

print("\n=== 4. next_index — 이어찍기 ===")
with tempfile.TemporaryDirectory() as td:
    check("빈 폴더면 1부터", cap.next_index(td) == 1)
    for nm in ("shot_001_c1.npy", "shot_002_c1.npy", "shot_007_c2.npy"):
        np.save(Path(td) / nm, np.zeros((4, 4), np.uint16))
    check("마지막 번호 다음 (7→8)", cap.next_index(td) == 8, str(cap.next_index(td)))

print("\n=== 5. 조건 메모 JSON — 유실 방지 ===")
with tempfile.TemporaryDirectory() as td:
    p = str(Path(td) / "capture_meta.json")
    m = cap.load_meta(p)
    check("없으면 기본 구조 생성", "conditions" in m and "shots" in m)
    m["conditions"]["1"] = "형광등만, 높이 55cm"
    m["shots"]["shot_001_c1"] = {"condition": 1, "median_mm": 490, "ok": True}
    cap.save_meta(p, m)
    m2 = cap.load_meta(p)
    check("저장·복원 왕복", m2["conditions"]["1"] == "형광등만, 높이 55cm")
    check("한글 보존 (ensure_ascii=False)", "형광등" in Path(p).read_text(encoding="utf-8"))
    check("shots 기록 보존", m2["shots"]["shot_001_c1"]["median_mm"] == 490)

print("\n=== 6. 🔴 현장 중단 위험 점검 ===")
src = SCRIPT.read_text(encoding="utf-8")
# ⚠️ OpenCV 창이 떠 있는 상태에서 input()을 쓰면 터미널에 포커스를 옮겨야 한다.
#    현장에서 "화면이 멈췄다"로 오인할 수 있어 경고 문구가 있어야 한다.
n_input = src.count("input(")
print(f"  input() 호출 {n_input}곳 (조건 메모 입력)")
check("조건 입력 시 터미널 안내 문구 있음",
      "조건 메모 입력" in src or "조건 >" in src)
check("ShortRange 불일치 시 sys.exit (경고 아님)",
      "sys.exit(" in src and "ShortRange 아님" in src)
check("프레임 스킵 방어 (7/28 유실 사고 대응)", "프레임 스킵" in src)
check("매 장 즉시 메타 저장 (유실 방지)", src.count("save_meta(meta_path, meta)") >= 3)
check("내부 IP 하드코딩 없음", "192.168." not in src)

print(f"\n{'='*50}\n결과: {_pass} 통과 / {_fail} 실패\n{'='*50}")
if _fail == 0:
    print("→ 카메라 없이 검증 가능한 부분은 전부 통과.")
    print("⚠️ 남은 미검증 = pypylon 실제 연결·ShortRange 설정·키 입력 루프(현장에서만 가능)")
sys.exit(1 if _fail else 0)
