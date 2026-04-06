"""
L6 로봇 통신 — Modbus TCP 서버
================================

비전 PC가 Modbus TCP 서버로 동작하고,
HCR-10L 협동로봇이 클라이언트로 레지스터를 읽어간다.

레지스터 맵 (Holding Registers, 40001~):
  40001: 명령 코드 (0=대기, 1=신규피킹, 2=완료, 99=에러)
  40002: 부품 ID (grasp_database.yaml 순서)
  40003~40004: X 위치 (FLOAT32, mm)
  40005~40006: Y 위치 (FLOAT32, mm)
  40007~40008: Z 위치 (FLOAT32, mm)
  40009~40010: Rx 회전 (FLOAT32, deg)
  40011~40012: Ry 회전 (FLOAT32, deg)
  40013~40014: Rz 회전 (FLOAT32, deg)
  40015: 그리퍼 벌림 (UINT16, mm * 10)
  40016: 그리퍼 힘 (UINT16, N * 10)

FLOAT32 인코딩: IEEE 754, Big-endian (2 x UINT16 레지스터)

사용법:
  # 서버 시작 (기본 포트 502)
  python bin_picking/src/communication/modbus_server.py --port 5020

  # 테스트 모드 (더미 데이터 전송)
  python bin_picking/src/communication/modbus_server.py --port 5020 --test

실행 환경: source .venv/binpick/bin/activate
"""

import argparse
import struct
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from pymodbus.server import StartTcpServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)
from pymodbus.device import ModbusDeviceIdentification


# ============================================================
# 레지스터 맵 상수
# ============================================================
# 기본 주소 (0-based, Modbus 주소 40001 = 인덱스 0)
REG_COMMAND = 0        # 40001: 명령 코드
REG_PART_ID = 1        # 40002: 부품 ID
REG_X = 2              # 40003~40004: X (FLOAT32)
REG_Y = 4              # 40005~40006: Y
REG_Z = 6              # 40007~40008: Z
REG_RX = 8             # 40009~40010: Rx
REG_RY = 10            # 40011~40012: Ry
REG_RZ = 12            # 40013~40014: Rz
REG_GRIPPER_WIDTH = 14  # 40015: 그리퍼 벌림 (mm * 10)
REG_GRIPPER_FORCE = 15  # 40016: 그리퍼 힘 (N * 10)

TOTAL_REGISTERS = 20    # 여유분 포함

# 명령 코드
CMD_IDLE = 0           # 대기
CMD_NEW_PICK = 1       # 신규 피킹 데이터 준비됨
CMD_DONE = 2           # 피킹 완료 (로봇이 씀)
CMD_ERROR = 99         # 에러


# ============================================================
# FLOAT32 ↔ 2×UINT16 변환
# ============================================================
def float32_to_registers(value: float) -> tuple:
    """FLOAT32를 Big-endian 2개 UINT16 레지스터로 변환."""
    packed = struct.pack(">f", value)
    hi = struct.unpack(">H", packed[0:2])[0]
    lo = struct.unpack(">H", packed[2:4])[0]
    return hi, lo


def registers_to_float32(hi: int, lo: int) -> float:
    """Big-endian 2개 UINT16 레지스터를 FLOAT32로 변환."""
    packed = struct.pack(">HH", hi, lo)
    return struct.unpack(">f", packed)[0]


# ============================================================
# PickingModbusServer
# ============================================================
class PickingModbusServer:
    """빈피킹 Modbus TCP 서버.

    L5 그래스프 결과를 Modbus 레지스터에 쓰면,
    HCR-10L 로봇이 읽어서 피킹을 실행한다.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 502):
        self.host = host
        self.port = port
        self._server_thread: Optional[threading.Thread] = None

        # 데이터 블록 초기화 (Holding Registers)
        self._block = ModbusSequentialDataBlock(0, [0] * TOTAL_REGISTERS)
        self._store = ModbusSlaveContext(hr=self._block)
        self._context = ModbusServerContext(slaves=self._store, single=True)

        # 부품 이름 → ID 매핑 (런타임에 설정)
        self._part_id_map: Dict[str, int] = {}

    def set_part_id_map(self, part_names: List[str]):
        """부품 이름 → ID 매핑을 설정한다.

        Args:
            part_names: 부품 이름 리스트 (인덱스 = ID)
        """
        self._part_id_map = {name: i + 1 for i, name in enumerate(part_names)}

    def get_part_id(self, part_name: str) -> int:
        """부품 이름에서 ID를 반환."""
        return self._part_id_map.get(part_name, 0)

    def write_pick_command(self, grasp_result: Dict[str, Any]):
        """L5 그래스프 결과를 레지스터에 쓴다.

        Args:
            grasp_result: GraspPlanner.compute_grasp_world() 반환값
        """
        pos = grasp_result["position_mm"]

        # 오일러 각도 추출 (T_grasp_world에서)
        T = grasp_result["T_grasp_world"]
        from scipy.spatial.transform import Rotation
        euler = Rotation.from_matrix(T[:3, :3]).as_euler("ZYX", degrees=True)

        # 레지스터에 쓰기
        values = [0] * TOTAL_REGISTERS

        values[REG_COMMAND] = CMD_NEW_PICK
        values[REG_PART_ID] = self.get_part_id(grasp_result["part_name"])

        # FLOAT32 → 2×UINT16
        for reg_offset, val in [
            (REG_X, pos["x"]),
            (REG_Y, pos["y"]),
            (REG_Z, pos["z"]),
            (REG_RX, float(euler[2])),  # Rx
            (REG_RY, float(euler[1])),  # Ry
            (REG_RZ, float(euler[0])),  # Rz
        ]:
            hi, lo = float32_to_registers(val)
            values[reg_offset] = hi
            values[reg_offset + 1] = lo

        # 그리퍼 (정수, ×10 스케일)
        values[REG_GRIPPER_WIDTH] = int(grasp_result.get("gripper_width_mm", 40) * 10)
        values[REG_GRIPPER_FORCE] = int(grasp_result.get("gripper_force_N", 15) * 10)

        # 블록에 쓰기
        self._block.setValues(0, values)

    def write_idle(self):
        """대기 상태로 전환."""
        self._block.setValues(REG_COMMAND, [CMD_IDLE])

    def write_error(self):
        """에러 상태로 전환."""
        self._block.setValues(REG_COMMAND, [CMD_ERROR])

    def read_command(self) -> int:
        """현재 명령 코드를 읽는다 (로봇이 CMD_DONE을 썼는지 확인)."""
        return self._block.getValues(REG_COMMAND, 1)[0]

    def read_all_registers(self) -> Dict[str, Any]:
        """전체 레지스터를 읽어서 딕셔너리로 반환."""
        vals = self._block.getValues(0, TOTAL_REGISTERS)

        return {
            "command": vals[REG_COMMAND],
            "part_id": vals[REG_PART_ID],
            "x_mm": registers_to_float32(vals[REG_X], vals[REG_X + 1]),
            "y_mm": registers_to_float32(vals[REG_Y], vals[REG_Y + 1]),
            "z_mm": registers_to_float32(vals[REG_Z], vals[REG_Z + 1]),
            "rx_deg": registers_to_float32(vals[REG_RX], vals[REG_RX + 1]),
            "ry_deg": registers_to_float32(vals[REG_RY], vals[REG_RY + 1]),
            "rz_deg": registers_to_float32(vals[REG_RZ], vals[REG_RZ + 1]),
            "gripper_width_mm": vals[REG_GRIPPER_WIDTH] / 10.0,
            "gripper_force_N": vals[REG_GRIPPER_FORCE] / 10.0,
        }

    def start(self, blocking: bool = True):
        """Modbus TCP 서버를 시작한다.

        Args:
            blocking: True면 메인 스레드에서 블로킹, False면 백그라운드 스레드
        """
        identity = ModbusDeviceIdentification()
        identity.VendorName = "Orinu"
        identity.ProductCode = "BinPick-Vision"
        identity.ProductName = "Bin Picking Vision Server"

        print(f"  Modbus TCP 서버 시작: {self.host}:{self.port}")
        print(f"  레지스터: 40001~400{TOTAL_REGISTERS}")
        print(f"  부품 ID 맵: {len(self._part_id_map)}종")

        if blocking:
            StartTcpServer(
                context=self._context,
                identity=identity,
                address=(self.host, self.port),
            )
        else:
            self._server_thread = threading.Thread(
                target=StartTcpServer,
                kwargs={
                    "context": self._context,
                    "identity": identity,
                    "address": (self.host, self.port),
                },
                daemon=True,
            )
            self._server_thread.start()
            time.sleep(0.5)  # 서버 시작 대기
            print(f"  백그라운드 서버 시작됨")

    def print_registers(self):
        """현재 레지스터 상태를 출력."""
        regs = self.read_all_registers()
        cmd_names = {0: "IDLE", 1: "NEW_PICK", 2: "DONE", 99: "ERROR"}
        cmd_str = cmd_names.get(regs["command"], f"UNKNOWN({regs['command']})")

        print(f"  명령: {cmd_str} ({regs['command']})")
        print(f"  부품 ID: {regs['part_id']}")
        print(f"  위치: ({regs['x_mm']:+.1f}, {regs['y_mm']:+.1f}, {regs['z_mm']:+.1f}) mm")
        print(f"  회전: ({regs['rx_deg']:+.1f}, {regs['ry_deg']:+.1f}, {regs['rz_deg']:+.1f}) deg")
        print(f"  그리퍼: width={regs['gripper_width_mm']:.1f}mm, force={regs['gripper_force_N']:.1f}N")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="빈피킹 Modbus TCP 서버")
    parser.add_argument("--host", default="0.0.0.0", help="바인드 주소 (기본: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5020, help="포트 (기본: 5020, 실전: 502)")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (더미 데이터 전송)")
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
        print("  Modbus 서버 테스트 모드")
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

        print("\n  3. FLOAT32 인코딩 검증...")
        for val in [120.5, -30.2, 65.0, 45.5, -12.3, 90.0]:
            hi, lo = float32_to_registers(val)
            restored = registers_to_float32(hi, lo)
            ok = "OK" if abs(restored - val) < 0.001 else "FAIL"
            print(f"    {val:>8.1f} → [{hi:#06x}, {lo:#06x}] → {restored:>8.3f}  [{ok}]")

        print("\n  테스트 완료!")

    else:
        print("=" * 60)
        print("  빈피킹 Modbus TCP 서버")
        print("=" * 60)
        print(f"  Ctrl+C로 종료")
        server.start(blocking=True)


if __name__ == "__main__":
    main()
