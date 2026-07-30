#!/usr/bin/env python3
"""pick_encoder 단위테스트 — 로봇·카메라 없이 실행 가능.

실행: python3 bin_picking/tests/test_pick_encoder.py

⭐ 검증의 핵심은 "정상 케이스가 되는가"가 아니라 **"틀린 입력이 조용히
   통과하지 않는가"** 다. 실물 로봇에서 잘못된 좌표는 충돌로 이어진다.
"""
from __future__ import annotations
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bin_picking.src.communication.pick_encoder import (  # noqa: E402
    PickEncodeError, encode_pick, decode_pick, decode_int16,
    build_part_id_map, REG_PICK_X, REG_PICK_Z, REG_PICK_ANGLE,
)

REAL_DIR = "/data/jtm/synth_out/6elements_100"
_pass = _fail = 0


def check(name: str, cond: bool, detail: str = ""):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ✅ {name}")
    else:
        _fail += 1; print(f"  ❌ {name}  {detail}")


def expect_raise(name: str, fn):
    global _pass, _fail
    try:
        fn()
    except PickEncodeError as e:
        _pass += 1; print(f"  ✅ {name} → 거부됨: {str(e)[:70]}")
    except Exception as e:
        _fail += 1; print(f"  ❌ {name} → 엉뚱한 예외 {type(e).__name__}: {e}")
    else:
        _fail += 1; print(f"  ❌ {name} → 통과해버림 (조용히 틀리는 경로!)")


def det(xc=-94.3, yc=-4.1, zc=457.6, angle=31.4, **kw):
    d = {"camera_3d": {"Xc": xc, "Yc": yc, "Zc": zc}, "angle": angle}
    d.update(kw)
    return d


print("\n=== 1. 기본 인코딩 + 왕복 ===")
regs = encode_pick(det(), part_id=3, gripper_width_mm=50.0)
back = decode_pick(regs)
check("Xc 음수 왕복 (-94.3)", abs(back["Xc"] - (-94.3)) < 0.05, f"got {back['Xc']}")
check("Zc 왕복 (457.6)", abs(back["Zc"] - 457.6) < 0.05, f"got {back['Zc']}")
check("angle 왕복 (31.4)", abs(back["angle"] - 31.4) < 0.05, f"got {back['angle']}")
check("gripper 왕복 (50.0)", abs(back["gripper_width_mm"] - 50.0) < 0.05)
check("part_id 보존", back["part_id"] == 3)

print("\n=== 2. 음수 = 2의 보수 (와이어 표현) ===")
# -94.3mm → -943 → 0xFC51 = 64593. UINT16 와이어에 담기는지.
check("음수가 UINT16 범위로 담김", 0 <= regs[REG_PICK_X] <= 65535, f"got {regs[REG_PICK_X]}")
check("음수 raw 값 정확", regs[REG_PICK_X] == (-943 & 0xFFFF), f"got {regs[REG_PICK_X]}")
check("decode가 음수로 복원", decode_int16(regs[REG_PICK_X]) == -94.3)

print("\n=== 3. 조용히 틀리면 안 되는 것들 (핵심) ===")
# 🔴 기존 mm_to_int16은 이걸 max/min으로 잘라서 통과시켰다.
expect_raise("z 3276.7mm 초과 → 클램프 대신 예외",
             lambda: encode_pick(det(zc=5000.0), 1, 50.0))
expect_raise("7/29 버그 재현: z=3136mm(uint16 미변환)",
             lambda: encode_pick(det(zc=3136.0), 1, 50.0))
expect_raise("nan (7/28 IPPE 조용한 오염)",
             lambda: encode_pick(det(zc=float("nan")), 1, 50.0))
expect_raise("camera_3d 누락",
             lambda: encode_pick({"angle": 10.0}, 1, 50.0))
expect_raise("angle=0 고정 (마스크 미저장)",
             lambda: encode_pick(det(angle=0.0), 1, 50.0))
expect_raise("part_id 0 (1-based 위반)",
             lambda: encode_pick(det(), 0, 50.0))
expect_raise("그리퍼 벌림 음수",
             lambda: encode_pick(det(), 1, -5.0))
expect_raise("Xc 범위 밖(2000mm)",
             lambda: encode_pick(det(xc=2000.0), 1, 50.0))

print("\n=== 4. angle=0 예외 허용 (대칭 부품) ===")
r = encode_pick(det(angle=0.0), 1, 50.0, require_angle=False)
check("require_angle=False면 통과", r[REG_PICK_ANGLE] == 0)

print("\n=== 5. part_id 맵 ===")
m = build_part_id_map(["r_guide_a_r", "03_sol_block_front", "r_guide_a_r"])
check("1-based 시작", min(m.values()) == 1)
check("중복 제거", len(m) == 2)
check("정렬 고정(재현성)", m["03_sol_block_front"] == 1, str(m))

print("\n=== 6. 실측 801건 전수 인코딩 (7/29 산출물) ===")
files = sorted(glob.glob(f"{REAL_DIR}/*.json"))
if not files:
    print(f"  ⏭️  {REAL_DIR} 없음 — 건너뜀")
else:
    total = ok = rejected = 0
    reasons = {}
    zs = []
    for f in files:
        data = json.load(open(f))
        labels = [d["label"] for d in data["detections"]]
        pmap = build_part_id_map(labels)
        for d in data["detections"]:
            total += 1
            try:
                # angle이 전부 0이므로 실측 검증은 require_angle=False로.
                # (angle=0 자체는 위 3번에서 별도로 거부 확인함)
                rr = encode_pick(d, pmap[d["label"]], 50.0, require_angle=False)
                bb = decode_pick(rr)
                assert abs(bb["Zc"] - d["camera_3d"]["Zc"]) < 0.06, "왕복 오차"
                zs.append(bb["Zc"]); ok += 1
            except PickEncodeError as e:
                rejected += 1
                reasons[str(e)[:45]] = reasons.get(str(e)[:45], 0) + 1
    print(f"  검출 {total}건 → 인코딩 성공 {ok} / 거부 {rejected}")
    if reasons:
        for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:5]:
            print(f"    · {v}건: {k}")
    check("801건 전수 인코딩 (7/29 기록과 일치)", total == 801, f"got {total}")
    check("전건 왕복 성공", rejected == 0, f"{rejected}건 거부")
    if zs:
        in_band = sum(1 for z in zs if 400 <= z <= 600)
        pct = 100.0 * in_band / len(zs)
        print(f"  z 400~600mm: {in_band}/{len(zs)} ({pct:.1f}%)")
        check("z 99% 이상이 부품 대역 (7/29 기록 재확인)", pct >= 99.0, f"{pct:.1f}%")

print(f"\n{'='*46}\n결과: {_pass} 통과 / {_fail} 실패\n{'='*46}")
sys.exit(1 if _fail else 0)
