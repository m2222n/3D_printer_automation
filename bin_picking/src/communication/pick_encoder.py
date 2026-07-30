"""
6요소 좌표 → HCR Modbus INT16 인코더
=====================================

`depth_track_to_6elements.py`가 뽑는 **mm 단위 float**을 HCR Modbus가 받는
**INT16 · 1/10mm**로 바꾼다. 레지스터 번호와 무관한 순수 변환이라
예승님 회신(레지스터 배치 확정) 전에도 검증 가능하다.

⭐ 왜 별도 모듈인가
--------------------
이 변환에 프로젝트에서 가장 위험한 종류의 버그가 산다. **틀려도 예외가 안 나고
그럴싸한 숫자가 나오기 때문**이다. 7/29에 잡은 버그 2건이 정확히 그 종류였다:

  - uint16을 mm로 착각 → z가 6~7배 과대(3136mm). 실내 거리로 그럴싸해 보였다.
  - 중심 5×5가 depth 구멍에 걸림 → z 실패 114건이 조용히 지나갔다.

실물 로봇에서 이게 터지면 **엉뚱한 좌표로 움직인다**. 그래서 이 모듈의 원칙은
**"조용히 틀리지 말고 크게 실패하라"** 다.

🔴 기존 `modbus_server.py`의 `mm_to_int16`을 쓰지 않는 이유
------------------------------------------------------------
그 함수는 범위를 벗어나면 `max(-32768, min(32767, raw))`로 **조용히 클램프**한다.
좌표가 3276.7mm를 넘으면 값이 잘려서 **로봇이 엉뚱한 데로 가는데 에러는 없다.**
빈피킹 z는 400~600mm라 실사용에서 안 넘지만, 넘는 상황은 **센서 고장이나 단위
착오**이므로 그때는 반드시 멈춰야 한다. → 여기서는 `PickEncodeError`를 던진다.

또한 그 파일의 레지스터 맵(131~137에 좌표)은 **7/27 매뉴얼 확정판과 충돌**한다
(확정판은 131~135가 이송 파라미터). 그래서 맵은 여기서 새로 정의한다.

⚠️ 레지스터 번호는 예승님 회신 대기 중 (2026-07-30 발송)
--------------------------------------------------------
아래 `REG_*`는 **우리 제안값**이며 확정이 아니다. 코드 검색상 140~149가 비어
있어 제안했다. 회신이 오면 **이 상수 블록만 고치면 된다** — 인코딩 로직은 번호와
무관하게 그대로다.

단위 규약 (HCR 매뉴얼 확정판 기준)
-----------------------------------
  거리: 1/10mm  → `492.6mm` → `4926`
  각도: 1/10deg → `31.4°`   → `314`
  음수: INT16 2의 보수. Modbus 레지스터는 UINT16 와이어라 `& 0xFFFF`로 담고
        읽는 쪽에서 32767 초과를 음수로 되돌린다.
        ⚠️ 빈피킹 좌표는 카메라 중심 기준이라 **Xc가 음수로 흔하다**
           (실측 예: `Xc=-94.3`). 부호 처리가 실사용 경로다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 레지스터 맵 — ⚠️ 제안값, 예승님 회신 후 확정 (여기만 고치면 됨)
# ============================================================
# 확정분 (7/27 매뉴얼, 예승님 운영 코드 `sequence_service` 일치)
REG_COMMAND = 130        # 명령 코드
REG_PARAM_START = 131    # 131~135 = 이송 파라미터 (빈피킹 아님)
REG_SEND_TRIGGER = 150   # 1=명령 전송 / 0=완료·초기화
REG_PC_READY = 151       # 1=제어 의사 표시(선점) / 0=해제
REG_ROBOT_READY = 200    # 로봇→PC: 1=수신 가능(IDLE)
REG_ROBOT_MOVED = 206    # 로봇→PC: 1=동작 완료

# 제안분 (140~149 = 코드 검색상 비어 있음)
REG_PICK_X = 140         # INT16, 1/10mm
REG_PICK_Y = 141
REG_PICK_Z = 142
REG_PICK_ANGLE = 143     # INT16, 1/10deg
REG_PICK_PART_ID = 144   # UINT16, 1-based (0 = 미상)
REG_PICK_GRIP_W = 145    # UINT16, 1/10mm

# 빈피킹 명령값 — ⚠️ 130번은 0/1/2/100이 이미 쓰이므로 새 값 필요 (예승님 확인 중)
CMD_BIN_PICK = 10

INT16_MIN, INT16_MAX = -32768, 32767
UINT16_MAX = 65535

# 물리 sanity 범위. 벗어나면 인식·단위 오류를 의심해야 하는 값.
# 근거: reproduce_f1_0684.sh:54 `--depth_keep_range 0.40,0.60` (부품 z = 400~600mm)
#       + 7/29 실측 100장에서 z 99%가 400~600mm
Z_PLAUSIBLE_MM = (200.0, 1500.0)
XY_PLAUSIBLE_MM = 1500.0


class PickEncodeError(ValueError):
    """인코딩 실패. **조용히 틀린 값을 내보내지 않기 위해** 예외로 만든다."""


def _to_int16_reg(value: float, unit_per_mm: float, name: str) -> int:
    """물리값 → INT16 레지스터(UINT16 와이어).

    ⭐ 클램프하지 않고 **범위를 벗어나면 던진다**. 잘린 좌표는 로봇을 엉뚱한 곳으로
       보내면서 에러를 남기지 않기 때문이다.
    """
    if value is None:
        raise PickEncodeError(f"{name}: 값이 None")
    try:
        fval = float(value)
    except (TypeError, ValueError) as e:
        raise PickEncodeError(f"{name}: 숫자가 아님 ({value!r})") from e
    if fval != fval or fval in (float("inf"), float("-inf")):
        # nan은 자기 자신과 다르다. 7/28 IPPE가 ok=True인데 nan을 반환한 전례가 있어
        # 유한성 검사를 넣는다 (조용한 오염원).
        raise PickEncodeError(f"{name}: 유한한 값이 아님 ({fval})")

    raw = int(round(fval * unit_per_mm))
    if not (INT16_MIN <= raw <= INT16_MAX):
        limit = INT16_MAX / unit_per_mm
        raise PickEncodeError(
            f"{name}: INT16 범위 초과 — {fval}(→{raw}), 한계 ±{limit:.1f}. "
            "센서 고장이나 단위 착오를 의심할 것 (조용히 자르지 않음)"
        )
    return raw & 0xFFFF


def _to_uint16_reg(value: float, unit_per_mm: float, name: str) -> int:
    """음수를 허용하지 않는 값(그리퍼 벌림 등)."""
    if value is None:
        raise PickEncodeError(f"{name}: 값이 None")
    fval = float(value)
    if fval < 0:
        raise PickEncodeError(f"{name}: 음수 불가 ({fval})")
    raw = int(round(fval * unit_per_mm))
    if raw > UINT16_MAX:
        raise PickEncodeError(f"{name}: UINT16 초과 ({fval}→{raw})")
    return raw


def decode_int16(register: int) -> float:
    """레지스터 → 물리값(1/10 단위). 왕복 검증·로봇 읽기용."""
    if register > INT16_MAX:
        register -= 65536
    return register / 10.0


def encode_pick(
    detection: Dict[str, Any],
    part_id: int,
    gripper_width_mm: float,
    *,
    require_angle: bool = True,
) -> Dict[int, int]:
    """6요소 검출 1건 → {레지스터: 값}.

    `detection` = `depth_track_to_6elements.py` 출력의 `detections[i]`.
    좌표는 픽셀(x,y)이 아니라 **`camera_3d`(mm)** 를 쓴다 — 로봇은 mm로 움직인다.

    Args:
        require_angle: True면 `angle=0`을 거부한다. 🔴 현재 예측 JSON은 마스크를
            저장하지 않아 angle이 **0으로 고정**돼 있다(`notes`에
            `angle=0_mask_not_saved`). 회전 비대칭 부품은 이 값 없이는 파지 자세를
            정할 수 없으므로, **기본을 거부로 두어 미해결 상태가 로봇까지 흘러가지
            않게** 한다. 대칭 부품만 다룰 때 의도적으로 False로 낮출 수 있다.
    """
    cam = detection.get("camera_3d")
    if not cam:
        raise PickEncodeError("camera_3d 없음 — 픽셀 좌표만으로는 로봇을 못 움직인다")

    xc, yc, zc = cam.get("Xc"), cam.get("Yc"), cam.get("Zc")

    # 유한성을 **범위 검사보다 먼저** 본다. nan은 모든 비교가 False라 범위 검사에
    # 먼저 걸리면 "범위 밖"이라는 오해를 부르는 메시지가 나온다(진단 비용).
    for nm, v in (("Xc", xc), ("Yc", yc), ("Zc", zc)):
        if v is None:
            raise PickEncodeError(f"{nm}: 값이 None")
        fv = float(v)
        if fv != fv or fv in (float("inf"), float("-inf")):
            raise PickEncodeError(
                f"{nm}: 유한한 값이 아님 ({fv}) — 7/28 IPPE가 ok=True인데 nan을"
                " 반환한 전례가 있다(조용한 오염원)"
            )

    # ⭐ 물리 검산. 7/29 교훈 = "값이 자연스러워 보여도 물리 검산할 것"
    #    (uint16 스케일 오해로 z=3136mm가 실내 거리로 그럴싸했다)
    if zc is None or not (Z_PLAUSIBLE_MM[0] <= float(zc) <= Z_PLAUSIBLE_MM[1]):
        raise PickEncodeError(
            f"z={zc}mm 가 물리 범위 {Z_PLAUSIBLE_MM} 밖 — depth 단위 변환"
            " (raw×10/65535) 누락이나 센서 이상을 의심할 것"
        )
    for nm, v in (("Xc", xc), ("Yc", yc)):
        if v is None or abs(float(v)) > XY_PLAUSIBLE_MM:
            raise PickEncodeError(f"{nm}={v}mm 가 물리 범위 ±{XY_PLAUSIBLE_MM} 밖")

    angle = detection.get("angle", 0.0)
    if require_angle and float(angle) == 0.0:
        raise PickEncodeError(
            "angle=0 고정 상태 — 마스크 미저장으로 회전각이 산출되지 않았다. "
            "회전 비대칭 부품은 파지 자세를 정할 수 없다. "
            "(대칭 부품만 다룬다면 require_angle=False)"
        )

    if part_id < 1:
        raise PickEncodeError(f"part_id는 1-based여야 함 ({part_id})")
    if part_id > UINT16_MAX:
        raise PickEncodeError(f"part_id UINT16 초과 ({part_id})")

    return {
        REG_PICK_X: _to_int16_reg(xc, 10.0, "Xc"),
        REG_PICK_Y: _to_int16_reg(yc, 10.0, "Yc"),
        REG_PICK_Z: _to_int16_reg(zc, 10.0, "Zc"),
        REG_PICK_ANGLE: _to_int16_reg(angle, 10.0, "angle"),
        REG_PICK_PART_ID: int(part_id),
        REG_PICK_GRIP_W: _to_uint16_reg(gripper_width_mm, 10.0, "gripper_width_mm"),
    }


def decode_pick(regs: Dict[int, int]) -> Dict[str, float]:
    """레지스터 → 물리값. 왕복(round-trip) 검증용."""
    return {
        "Xc": decode_int16(regs[REG_PICK_X]),
        "Yc": decode_int16(regs[REG_PICK_Y]),
        "Zc": decode_int16(regs[REG_PICK_Z]),
        "angle": decode_int16(regs[REG_PICK_ANGLE]),
        "part_id": regs[REG_PICK_PART_ID],
        "gripper_width_mm": regs[REG_PICK_GRIP_W] / 10.0,
    }


def build_part_id_map(labels: List[str]) -> Dict[str, int]:
    """라벨 → 1-based ID. 정렬 고정으로 재현성 확보.

    ⚠️ 로봇 펜던트와 **같은 표를 써야** 한다. 순서가 어긋나면 로봇이 다른 부품의
       파지 자세를 쓴다 — 조용히 틀리는 또 하나의 경로.
    """
    return {name: i + 1 for i, name in enumerate(sorted(set(labels)))}


__all__ = [
    "PickEncodeError", "encode_pick", "decode_pick", "decode_int16",
    "build_part_id_map", "CMD_BIN_PICK",
    "REG_COMMAND", "REG_SEND_TRIGGER", "REG_PC_READY",
    "REG_ROBOT_READY", "REG_ROBOT_MOVED",
    "REG_PICK_X", "REG_PICK_Y", "REG_PICK_Z",
    "REG_PICK_ANGLE", "REG_PICK_PART_ID", "REG_PICK_GRIP_W",
]
