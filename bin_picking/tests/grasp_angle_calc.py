#!/usr/bin/env python3
"""
파지 자세 보정값 계산기 — 현장 관찰 → cam_to_base build 옵션 (2026-09-26 재택)

cam_to_base 의 파지 자세 3값은 문서로 확정할 수 없어 [실측필요]로 남아 있다.
    rz = rz_sign × yaw_close + rz_offset          (cam_to_base.rz_for_grasp)
    z  = 윗면 z + z_offset                        (cam_to_base.det_to_base_pose)
이 스크립트는 **로봇만으로(카메라 없이)** 관찰한 값을 넣으면 세 값을 계산해
`cam_to_base build` 에 그대로 붙일 옵션을 찍는다. 절차 = bin_picking/docs/GRASP_ANGLE_CARD.md

yaw_close = 조우가 열고 닫히는 선(손가락이 오가는 선)이 base +X 와 이루는 각(위에서 본 평면 · [0,180)).
관찰은 "그 선이 +X 테이프와 나란한가(0) · +Y 테이프와 나란한가(90)" 로 충분하다.

사용:
  python bin_picking/tests/grasp_angle_calc.py rz --rz1 -90.03 --yaw1 0 --rz2 -60.03 --sense same
  python bin_picking/tests/grasp_angle_calc.py z  --z-touch 152.4 --z-grip 145.0 --part-height 12
  python bin_picking/tests/grasp_angle_calc.py --self-test
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _mod180_signed(deg: float) -> float:
    """(-90, 90] 로 접는다 — 조우는 180° 대칭이라 rz_offset 은 180 주기."""
    d = (deg + 90.0) % 180.0 - 90.0
    if d <= -90.0 + 1e-9:
        d += 180.0
    return d


def _diff180(a: float, b: float) -> float:
    """두 선 각(180 주기)의 차 절댓값 [0, 90]."""
    d = abs((a - b) % 180.0)
    return min(d, 180.0 - d)


def solve_rz(rz1: float, yaw1: float, rz2: float, sense: str) -> tuple[int, float, float]:
    """관찰 → (rz_sign, rz_offset, rz2 에서 예상되는 yaw).

    sense = 'same'     : rz1→rz2 로 바꿨을 때 조우 선이 "+X 테이프 → +Y 테이프" 쪽(짧은 쪽)으로 돌았다
            'opposite' : 반대로 돌았다
    """
    d_rz = float(rz2) - float(rz1)
    if abs(d_rz) < 5.0 or abs(d_rz) > 60.0:
        raise ValueError(f"rz 변화 {d_rz:+.1f}° — 5~60° 로 바꿔야 회전 방향이 눈에 보이고 180° 대칭에 안 헷갈린다(권장 +30)")
    if sense not in ("same", "opposite"):
        raise ValueError("sense 는 same | opposite")
    yaw_up = sense == "same"                     # 조우 선의 yaw 가 늘었나
    sign = 1 if (yaw_up == (d_rz > 0)) else -1   # rz 가 늘 때 yaw 도 늘면 +1
    offset = _mod180_signed(float(rz1) - sign * float(yaw1))
    yaw2 = (float(yaw1) + sign * d_rz) % 180.0
    return sign, offset, yaw2


def solve_z(z_touch: float, z_grip: float, part_height: float | None) -> float:
    """닫힌 조우 끝을 윗면에 댄 TCP z(z_touch · 3점법과 같은 방식) vs 집는 높이 TCP z(z_grip) → z_offset."""
    zo = float(z_grip) - float(z_touch)
    if zo > 0.5:
        raise ValueError(f"z_offset {zo:+.1f} > 0 — 집는 높이가 윗면보다 위다(허공을 문다). z_touch·z_grip 을 바꿔 적었나")
    if part_height is not None and -zo >= float(part_height):
        raise ValueError(f"파지 깊이 {-zo:.1f} ≥ 부품 높이 {part_height} — 조우 끝이 바닥에 닿는다")
    return zo


def _cmd_rz(a) -> int:
    sign, offset, yaw2 = solve_rz(a.rz1, a.yaw1, a.rz2, a.sense)
    print(f"rz_sign   = {sign:+d}")
    print(f"rz_offset = {offset:.2f}")
    print(f"확인: rz {a.rz2:.2f} 에서 조우 선은 +X 와 약 {yaw2:.0f}° 여야 한다"
          f"(0=+X 와 나란 · 90=+Y 와 나란) — 눈으로 본 것과 다르면 관찰을 다시 한다")
    print(f"\ncam_to_base build 에 붙일 옵션:  --rz-sign {sign} --rz-offset {offset:.2f}")
    return 0


def _cmd_z(a) -> int:
    zo = solve_z(a.z_touch, a.z_grip, a.part_height)
    print(f"z_offset = {zo:.1f} mm (음수 = 윗면보다 {-zo:.1f} mm 아래에서 문다)")
    print(f"\ncam_to_base build 에 붙일 옵션:  --z-offset {zo:.1f}")
    return 0


# ---------------------------------------------------------------- self-test
def _self_test() -> int:
    """관찰을 시뮬레이션해 되찾고, **실제 cam_to_base.rz_for_grasp** 와 맞물리는지 본다(배선 검사)."""
    from bin_picking.src.communication.cam_to_base import GraspFrame, rz_for_grasp
    import numpy as np

    ok = fail = 0

    def check(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print(f"  ❌ {name}")

    def observe(true_sign, true_off, rz):     # 로봇이 실제로 보여줄 조우 선 각
        return (true_sign * (rz - true_off)) % 180.0

    cases = [(s, o, r1, d) for s in (1, -1) for o in (0.0, 90.0, 37.5, -12.0)
             for r1 in (-90.03, 0.0, 173.4) for d in (30.0, -30.0, 12.0)]
    for s, o, r1, d in cases:
        r2 = r1 + d
        y1, y2 = observe(s, o, r1), observe(s, o, r2)
        # 사람이 본 회전 방향: yaw 가 (짧은 쪽으로) 늘었나
        inc = ((y2 - y1 + 90.0) % 180.0 - 90.0) > 0
        sense = "same" if inc else "opposite"
        sign, off, y2p = solve_rz(r1, y1, r2, sense)
        tag = f"s{s} o{o} r1{r1} d{d}"
        check(f"sign {tag}", sign == s)
        check(f"offset {tag}", _diff180(off, o) < 1e-6)
        check(f"yaw2 예측 {tag}", _diff180(y2p, y2) < 1e-6)
        # 🥇 배선: 되찾은 값으로 실제 코드가 같은 rz 를 내는가
        g = GraspFrame(rz_ref_deg=r1, rz_sign=sign, rz_offset_deg=off)
        calib = SimpleNamespace(R=np.eye(3), grasp=g)
        angle_img = (y2 - 90.0) % 180.0        # R=I 이면 yaw_long = angle_img · yaw_close = +90
        rz_code = rz_for_grasp(calib, angle_img)
        check(f"rz_for_grasp 일치 {tag}", _diff180(rz_code, r2) < 1e-6)

    # 거부
    for bad in [dict(rz1=0, yaw1=0, rz2=2, sense="same"), dict(rz1=0, yaw1=0, rz2=90, sense="same"),
                dict(rz1=0, yaw1=0, rz2=30, sense="cw")]:
        try:
            solve_rz(**bad)
            check(f"거부 {bad}", False)
        except ValueError:
            check("거부", True)
    check("z 정상", abs(solve_z(152.4, 145.0, 12) - (-7.4)) < 1e-9)
    for bad in [(145.0, 152.4, 12), (152.4, 138.0, 12)]:
        try:
            solve_z(*bad)
            check(f"z 거부 {bad}", False)
        except ValueError:
            check("z 거부", True)

    print(f"self-test {ok}/{ok + fail}" + (" ✅" if fail == 0 else " 🔴"))
    return 0 if fail == 0 else 1


def main(argv=None) -> int:
    try:                                        # IPC(cp949) 에서 ✅🔴 출력이 죽지 않게 (8/28·9/18)
        from bin_picking.src.utils.console_utf8 import enable_utf8_console
        enable_utf8_console()
    except ImportError:
        pass
    if "--self-test" in (argv if argv is not None else sys.argv[1:]):
        return _self_test()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rz", help="회전 부호·오프셋")
    r.add_argument("--rz1", type=float, required=True, help="첫 자세 펜던트 RZ (base 좌표 표시)")
    r.add_argument("--yaw1", type=float, required=True, help="첫 자세 조우 선 각: +X 와 나란=0 · +Y 와 나란=90")
    r.add_argument("--rz2", type=float, required=True, help="RZ 만 바꾼 두 번째 자세 (권장 rz1+30)")
    r.add_argument("--sense", required=True, choices=("same", "opposite"),
                   help="조우 선이 +X→+Y 쪽으로 돌았으면 same · 반대면 opposite")
    r.set_defaults(func=_cmd_rz)
    z = sub.add_parser("z", help="파지 깊이")
    z.add_argument("--z-touch", type=float, required=True, help="닫힌 조우 끝을 부품 윗면에 댄 TCP Z")
    z.add_argument("--z-grip", type=float, required=True, help="열린 조우로 집을 높이까지 내린 TCP Z")
    z.add_argument("--part-height", type=float, help="부품 높이(mm · 바닥 충돌 검사)")
    z.set_defaults(func=_cmd_z)
    # argparse 가 '-90.03' 을 옵션으로 오해하지 않게 붙인다(9/17·9/18 함정)
    raw = list(argv if argv is not None else sys.argv[1:])
    fixed = []
    i = 0
    while i < len(raw):
        if raw[i].startswith("--") and "=" not in raw[i] and i + 1 < len(raw) and raw[i + 1].startswith("-") \
                and raw[i + 1][1:2].isdigit():
            fixed.append(f"{raw[i]}={raw[i + 1]}")
            i += 2
        else:
            fixed.append(raw[i])
            i += 1
    a = ap.parse_args(fixed)
    try:
        return a.func(a)
    except ValueError as e:
        print(f"🔴 {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
