"""
L6 로봇 통신 — Modbus TCP 서버 (HCR-10L 실제 레지스터 맵)
===========================================================

비전 PC가 Modbus TCP 서버로 동작하고,
HCR-10L 협동로봇이 클라이언트로 레지스터를 읽어간다.

HCR-10L Modbus 레지스터 맵
--------------------------

■ 비전PC → 로봇 (Register 130~149, 비전PC가 쓰기/로봇이 읽기)
  130: 명령 코드 (0=IDLE, 1=NEW_PICK, 99=ERROR)
  131: 부품 ID (grasp_database.yaml 순서, 1-based)
  132: X 위치 (INT16, 단위 1/10mm → ±3276.7mm)
  133: Y 위치
  134: Z 위치
  135: Rx 회전 (INT16, 단위 1/10deg → ±3276.7°)
  136: Ry 회전
  137: Rz 회전
  138: 그리퍼 벌림 (UINT16, 1/10mm)
  139: 그리퍼 힘 (UINT16, 1/10N)
  140: 시퀀스 번호 (0~65535 순환, 동기화 검증용)

■ 로봇 → 비전PC (Register 150~159, 로봇이 쓰기/비전PC가 읽기)
  150: 로봇 상태 (0=IDLE, 2=DONE, 3=BUSY, 99=ERROR)
  151: 시퀀스 확인 (로봇이 읽은 시퀀스 번호를 echo)

■ 로봇 내장 레지스터 (읽기 전용, HCR 시스템)
  400~405: 현재 TCP 좌표 (X,Y,Z,Rx,Ry,Rz — 1/10mm, 1/10deg, INT16)
  600: Program State (0=None, 1=Play, 2=Stop, 3=Pause, ...)
  700/701/702: Command (Start/Pause/Stop)

좌표계:
  - Base 좌표계 (로봇 바닥 고정부 기준)
  - 오일러 각 ZYX intrinsic (Rz→Ry→Rx)
  - INT16 범위: -32768 ~ 32767 → ±3276.7mm / ±3276.7°

INT16 인코딩:
  - mm → register: int(round(mm * 10))
  - deg → register: int(round(deg * 10))
  - register → mm: register / 10.0
  - 음수: 2의 보수 (INT16), 예: -30.2mm → -302 → 0xFED2

피킹 사이클:
  1. 비전 PC: seq++ → 좌표 쓰기 → CMD=NEW_PICK(1) 쓰기 (CMD은 마지막에)
  2. 로봇 펜던트: CMD 폴링 → 1이면 좌표 읽기 → seq 확인 → CMD=BUSY(3) 쓰기 → 모션 실행
  3. 로봇 펜던트: 피킹 완료 → ROBOT_STATE=DONE(2) + seq echo 쓰기
  4. 비전 PC: ROBOT_STATE==DONE && seq 일치 확인 → CMD=IDLE(0) → 다음 부품

사용법:
  # 서버 시작 (기본 포트 5020, 실전 502)
  python bin_picking/src/communication/modbus_server.py --port 5020

  # 테스트 모드 (더미 데이터 전송 + INT16 인코딩 검증)
  python bin_picking/src/communication/modbus_server.py --port 5020 --test

실행 환경: source .venv/binpick/bin/activate
"""

import argparse
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
)


# ============================================================
# 레지스터 맵 상수 — HCR-10L 사용자 영역 (130~255)
# ============================================================

# --- 비전PC → 로봇 (Register 130~149) ---
REG_BASE = 130          # HCR-10L 사용자 레지스터 시작 (교육 확인: 130~255)
REG_COMMAND = 130       # 명령 코드
REG_PART_ID = 131       # 부품 ID (1-based)
REG_X = 132             # X 위치 (INT16, 1/10mm)
REG_Y = 133             # Y 위치
REG_Z = 134             # Z 위치
REG_RX = 135            # Rx 회전 (INT16, 1/10deg)
REG_RY = 136            # Ry 회전
REG_RZ = 137            # Rz 회전
REG_GRIPPER_WIDTH = 138  # 그리퍼 벌림 (UINT16, 1/10mm)
REG_GRIPPER_FORCE = 139  # 그리퍼 힘 (UINT16, 1/10N)
REG_SEQ = 140            # 시퀀스 번호 (동기화용, 0~65535)

# --- 로봇 → 비전PC (Register 150~159) ---
REG_ROBOT_STATE = 150    # 로봇 상태
REG_ROBOT_SEQ = 151      # 시퀀스 확인 (echo)

# --- 로봇 내장 (읽기 전용) ---
REG_TCP_X = 400          # 현재 TCP X (1/10mm)
REG_TCP_Y = 401
REG_TCP_Z = 402
REG_TCP_RX = 403         # 현재 TCP Rx (1/10deg)
REG_TCP_RY = 404
REG_TCP_RZ = 405
REG_PROG_STATE = 600     # Program State (0~6)
REG_CMD_START = 700      # 프로그램 시작
REG_CMD_PAUSE = 701      # 프로그램 일시정지
REG_CMD_STOP = 702       # 프로그램 정지

# 데이터 블록 크기 (0~702까지 커버, 여유 포함)
DATABLOCK_SIZE = 710

# --- 명령 코드 (비전PC → 로봇, Register 130) ---
CMD_IDLE = 0             # 대기 (피킹 데이터 없음)
CMD_NEW_PICK = 1         # 신규 피킹 데이터 준비됨
CMD_ERROR = 99           # 비전 시스템 에러

# --- 로봇 상태 (로봇 → 비전PC, Register 150) ---
ROBOT_IDLE = 0           # 대기 중
ROBOT_DONE = 2           # 피킹 완료
ROBOT_BUSY = 3           # 피킹 실행 중
ROBOT_ERROR = 99         # 로봇 에러


# ============================================================
# INT16 ↔ 물리값 변환
# ============================================================
def mm_to_int16(value_mm: float) -> int:
    """mm → INT16 (1/10mm 단위). 범위: ±3276.7mm."""
    raw = int(round(value_mm * 10))
    raw = max(-32768, min(32767, raw))
    # Modbus 레지스터는 UINT16(0~65535) — 음수는 2의 보수
    return raw & 0xFFFF


def int16_to_mm(register: int) -> float:
    """INT16 레지스터 → mm. 2의 보수 처리."""
    if register > 32767:
        register -= 65536
    return register / 10.0


def deg_to_int16(value_deg: float) -> int:
    """deg → INT16 (1/10deg 단위). 범위: ±3276.7°."""
    raw = int(round(value_deg * 10))
    raw = max(-32768, min(32767, raw))
    return raw & 0xFFFF


def int16_to_deg(register: int) -> float:
    """INT16 레지스터 → deg. 2의 보수 처리."""
    if register > 32767:
        register -= 65536
    return register / 10.0


# ============================================================
# PickingModbusServer
# ============================================================
class PickingModbusServer:
    """빈피킹 Modbus TCP 서버 — HCR-10L 레지스터 맵.

    비전PC(Server)가 레지스터에 피킹 좌표를 쓰면,
    HCR-10L(Client)이 폴링하여 읽고 모션을 실행한다.
    좌표는 INT16(1/10mm, 1/10deg)으로 HCR 펜던트와 동일.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 502):
        self.host = host
        self.port = port
        self._server_thread: Optional[threading.Thread] = None
        self._seq: int = 0  # 시퀀스 번호 (0~65535 순환)

        # 데이터 블록 초기화 (Holding Registers, 0-based 인덱스)
        # pymodbus: address 0 = Modbus Register 0
        # HCR은 Register 130~부터 사용하므로 블록을 0~709로 할당
        self._block = ModbusSequentialDataBlock(0, [0] * DATABLOCK_SIZE)
        self._context = ModbusServerContext(
            devices={1: {"h": self._block}},
            single=True,
        )

        # 부품 이름 → ID 매핑 (런타임에 설정)
        self._part_id_map: Dict[str, int] = {}

    def set_part_id_map(self, part_names: List[str]):
        """부품 이름 → ID 매핑을 설정한다.

        Args:
            part_names: 부품 이름 리스트 (인덱스+1 = ID, 1-based)
        """
        self._part_id_map = {name: i + 1 for i, name in enumerate(part_names)}

    def get_part_id(self, part_name: str) -> int:
        """부품 이름에서 ID를 반환 (0 = 미등록)."""
        return self._part_id_map.get(part_name, 0)

    def _next_seq(self) -> int:
        """시퀀스 번호를 증가시키고 반환한다 (0~65535 순환)."""
        self._seq = (self._seq + 1) % 65536
        return self._seq

    def write_pick_command(self, grasp_result: Dict[str, Any]):
        """L5 그래스프 결과를 레지스터에 쓴다.

        쓰기 순서: 좌표 먼저 → CMD 마지막 (로봇이 CMD를 보고 읽기 시작하므로)

        Args:
            grasp_result: GraspPlanner.compute_grasp_world() 반환값
        """
        pos = grasp_result["position_mm"]

        # 오일러 각도 추출 (T_grasp_world에서)
        # 컨벤션: ZYX intrinsic (Rz→Ry→Rx)
        T = grasp_result["T_grasp_world"]
        from scipy.spatial.transform import Rotation
        euler = Rotation.from_matrix(T[:3, :3]).as_euler("ZYX", degrees=True)
        # as_euler("ZYX") 반환: [Rz, Ry, Rx]

        seq = self._next_seq()

        # 좌표 + 그리퍼 먼저 쓰기 (CMD보다 먼저!)
        self._block.setValues(REG_PART_ID, [self.get_part_id(grasp_result["part_name"])])
        self._block.setValues(REG_X, [mm_to_int16(pos["x"])])
        self._block.setValues(REG_Y, [mm_to_int16(pos["y"])])
        self._block.setValues(REG_Z, [mm_to_int16(pos["z"])])
        self._block.setValues(REG_RX, [deg_to_int16(float(euler[2]))])   # Rx
        self._block.setValues(REG_RY, [deg_to_int16(float(euler[1]))])   # Ry
        self._block.setValues(REG_RZ, [deg_to_int16(float(euler[0]))])   # Rz
        self._block.setValues(REG_GRIPPER_WIDTH, [mm_to_int16(grasp_result.get("gripper_width_mm", 40))])
        self._block.setValues(REG_GRIPPER_FORCE, [int(round(grasp_result.get("gripper_force_N", 15) * 10))])
        self._block.setValues(REG_SEQ, [seq])

        # CMD는 마지막에 (로봇이 CMD 폴링 → 1이면 나머지 읽기)
        self._block.setValues(REG_COMMAND, [CMD_NEW_PICK])

    def write_idle(self):
        """대기 상태로 전환."""
        self._block.setValues(REG_COMMAND, [CMD_IDLE])

    def write_error(self):
        """에러 상태로 전환."""
        self._block.setValues(REG_COMMAND, [CMD_ERROR])

    def read_command(self) -> int:
        """비전PC 명령 레지스터를 읽는다."""
        return self._block.getValues(REG_COMMAND, 1)[0]

    def read_robot_state(self) -> int:
        """로봇 상태 레지스터를 읽는다 (Register 150)."""
        return self._block.getValues(REG_ROBOT_STATE, 1)[0]

    def read_robot_seq(self) -> int:
        """로봇이 echo한 시퀀스 번호를 읽는다 (Register 151)."""
        return self._block.getValues(REG_ROBOT_SEQ, 1)[0]

    def read_tcp_position(self) -> Dict[str, float]:
        """로봇 현재 TCP 좌표를 읽는다 (Register 400~405)."""
        vals = self._block.getValues(REG_TCP_X, 6)
        return {
            "x_mm": int16_to_mm(vals[0]),
            "y_mm": int16_to_mm(vals[1]),
            "z_mm": int16_to_mm(vals[2]),
            "rx_deg": int16_to_deg(vals[3]),
            "ry_deg": int16_to_deg(vals[4]),
            "rz_deg": int16_to_deg(vals[5]),
        }

    def read_program_state(self) -> int:
        """로봇 프로그램 상태를 읽는다 (Register 600)."""
        return self._block.getValues(REG_PROG_STATE, 1)[0]

    def read_pick_registers(self) -> Dict[str, Any]:
        """비전PC→로봇 피킹 레지스터를 읽어서 딕셔너리로 반환."""
        return {
            "command": self._block.getValues(REG_COMMAND, 1)[0],
            "part_id": self._block.getValues(REG_PART_ID, 1)[0],
            "x_mm": int16_to_mm(self._block.getValues(REG_X, 1)[0]),
            "y_mm": int16_to_mm(self._block.getValues(REG_Y, 1)[0]),
            "z_mm": int16_to_mm(self._block.getValues(REG_Z, 1)[0]),
            "rx_deg": int16_to_deg(self._block.getValues(REG_RX, 1)[0]),
            "ry_deg": int16_to_deg(self._block.getValues(REG_RY, 1)[0]),
            "rz_deg": int16_to_deg(self._block.getValues(REG_RZ, 1)[0]),
            "gripper_width_mm": int16_to_mm(self._block.getValues(REG_GRIPPER_WIDTH, 1)[0]),
            "gripper_force_N": self._block.getValues(REG_GRIPPER_FORCE, 1)[0] / 10.0,
            "seq": self._block.getValues(REG_SEQ, 1)[0],
            "robot_state": self._block.getValues(REG_ROBOT_STATE, 1)[0],
            "robot_seq": self._block.getValues(REG_ROBOT_SEQ, 1)[0],
        }

    def start(self, blocking: bool = True):
        """Modbus TCP 서버를 시작한다.

        Args:
            blocking: True면 메인 스레드에서 블로킹, False면 백그라운드 스레드
        """
        print(f"  Modbus TCP 서버 시작: {self.host}:{self.port}")
        print(f"  피킹 레지스터: {REG_COMMAND}~{REG_SEQ}")
        print(f"  로봇 상태 레지스터: {REG_ROBOT_STATE}~{REG_ROBOT_SEQ}")
        print(f"  부품 ID 맵: {len(self._part_id_map)}종")

        if blocking:
            StartTcpServer(
                context=self._context,
                address=(self.host, self.port),
            )
        else:
            self._server_thread = threading.Thread(
                target=StartTcpServer,
                kwargs={
                    "context": self._context,
                    "address": (self.host, self.port),
                },
                daemon=True,
            )
            self._server_thread.start()
            time.sleep(0.5)  # 서버 시작 대기
            print(f"  백그라운드 서버 시작됨")

    def print_registers(self):
        """현재 레지스터 상태를 출력."""
        regs = self.read_pick_registers()
        cmd_names = {0: "IDLE", 1: "NEW_PICK", 99: "ERROR"}
        robot_names = {0: "IDLE", 2: "DONE", 3: "BUSY", 99: "ERROR"}
        cmd_str = cmd_names.get(regs["command"], f"UNKNOWN({regs['command']})")
        robot_str = robot_names.get(regs["robot_state"], f"UNKNOWN({regs['robot_state']})")

        print(f"  --- 비전PC → 로봇 (Reg {REG_COMMAND}~{REG_SEQ}) ---")
        print(f"  명령: {cmd_str} ({regs['command']})")
        print(f"  부품 ID: {regs['part_id']}")
        print(f"  위치: ({regs['x_mm']:+.1f}, {regs['y_mm']:+.1f}, {regs['z_mm']:+.1f}) mm")
        print(f"  회전: ({regs['rx_deg']:+.1f}, {regs['ry_deg']:+.1f}, {regs['rz_deg']:+.1f}) deg")
        print(f"  그리퍼: width={regs['gripper_width_mm']:.1f}mm, force={regs['gripper_force_N']:.1f}N")
        print(f"  시퀀스: {regs['seq']}")
        print(f"  --- 로봇 → 비전PC (Reg {REG_ROBOT_STATE}~{REG_ROBOT_SEQ}) ---")
        print(f"  로봇 상태: {robot_str} ({regs['robot_state']})")
        print(f"  로봇 시퀀스: {regs['robot_seq']}")

    def wait_for_done(self, timeout_s: float = 30.0, poll_hz: float = 10.0) -> bool:
        """로봇이 DONE 상태가 될 때까지 대기한다.

        피킹 사이클: write_pick_command() → wait_for_done() → write_idle()

        확인 조건:
          - Register 150 == ROBOT_DONE (2)
          - Register 151 == 현재 seq (동기화 검증)

        Args:
            timeout_s: 최대 대기 시간 (초)
            poll_hz: 폴링 주기 (Hz)

        Returns:
            True: 피킹 완료 (DONE + seq 일치), False: 타임아웃/에러/seq 불일치
        """
        interval = 1.0 / poll_hz
        elapsed = 0.0
        expected_seq = self._seq

        while elapsed < timeout_s:
            state = self.read_robot_state()

            if state == ROBOT_ERROR:
                print(f"  [에러] 로봇 에러 수신 (ROBOT_ERROR)")
                return False

            if state == ROBOT_DONE:
                robot_seq = self.read_robot_seq()
                if robot_seq == expected_seq:
                    return True
                else:
                    print(f"  [경고] seq 불일치: 기대 {expected_seq}, 수신 {robot_seq}")
                    return False

            time.sleep(interval)
            elapsed += interval

        print(f"  [타임아웃] {timeout_s}s — 로봇 응답 없음")
        return False


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="빈피킹 Modbus TCP 서버 (HCR-10L)")
    parser.add_argument("--host", default="0.0.0.0", help="바인드 주소 (기본: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5020, help="포트 (기본: 5020, 실전: 502)")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (더미 데이터 + INT16 검증)")
    args = parser.parse_args()

    server = PickingModbusServer(host=args.host, port=args.port)

    # 테스트용 부품 ID 맵
    test_parts = [
        "01_sol_block_a", "02_sol_block_b", "07_guide_paper_l",
        "bracket_sensor1", "17_mks_holder",
    ]
    server.set_part_id_map(test_parts)

    if args.test:
        print("=" * 60)
        print("  Modbus 서버 테스트 모드 (HCR-10L INT16)")
        print("=" * 60)

        # 백그라운드로 서버 시작
        server.start(blocking=False)

        # 더미 그래스프 데이터
        dummy_grasp = {
            "part_name": "01_sol_block_a",
            "T_grasp_world": np.eye(4),
            "position_mm": {"x": 120.5, "y": -30.2, "z": 65.0},
            "gripper_width_mm": 20,
            "gripper_force_N": 15,
        }

        print("\n  1. 피킹 명령 쓰기...")
        server.write_pick_command(dummy_grasp)
        server.print_registers()

        print("\n  2. 대기 상태로 전환...")
        server.write_idle()
        server.print_registers()

        print("\n  3. INT16 인코딩 검증 (mm)...")
        test_mm = [120.5, -30.2, 65.0, 0.0, -3276.7, 3276.7, 1500.3]
        for val in test_mm:
            encoded = mm_to_int16(val)
            decoded = int16_to_mm(encoded)
            ok = "OK" if abs(decoded - val) < 0.15 else "FAIL"
            print(f"    {val:>9.1f}mm → reg={encoded:#06x} ({encoded:>6d}) → {decoded:>9.1f}mm  [{ok}]")

        print("\n  4. INT16 인코딩 검증 (deg)...")
        test_deg = [45.5, -12.3, 90.0, 180.0, -180.0, 0.0]
        for val in test_deg:
            encoded = deg_to_int16(val)
            decoded = int16_to_deg(encoded)
            ok = "OK" if abs(decoded - val) < 0.15 else "FAIL"
            print(f"    {val:>9.1f}° → reg={encoded:#06x} ({encoded:>6d}) → {decoded:>9.1f}°  [{ok}]")

        print("\n  5. 시퀀스 번호 검증...")
        for i in range(3):
            dummy_grasp["position_mm"]["x"] = 100.0 + i * 50
            server.write_pick_command(dummy_grasp)
            regs = server.read_pick_registers()
            print(f"    pick #{i+1}: seq={regs['seq']}, x={regs['x_mm']:.1f}mm")

        print("\n  테스트 완료!")

    else:
        print("=" * 60)
        print("  빈피킹 Modbus TCP 서버 (HCR-10L)")
        print("=" * 60)
        print(f"  레지스터 맵: 비전PC→로봇 {REG_COMMAND}~{REG_SEQ}, "
              f"로봇→비전PC {REG_ROBOT_STATE}~{REG_ROBOT_SEQ}")
        print(f"  Ctrl+C로 종료")
        server.start(blocking=True)


if __name__ == "__main__":
    main()
