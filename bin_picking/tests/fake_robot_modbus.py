#!/usr/bin/env python3
"""가짜 HCR 로봇 — Modbus TCP 서버 (8단계 핸드셰이크 상대역)

⭐ 왜 필요한가
--------------
실물 로봇은 공장에 있고, 배포 타깃 Thor는 **발주 전**이다. 그런데 6요소 좌표를
로봇에 보내는 통신 로직은 지금 만들어둬야 한다. 이 서버가 로봇 역할을 대신하면
**로봇·카메라 없이 재택에서 핸드셰이크를 완성**할 수 있다.

🔴 이게 시뮬로 먼저 잡아야 하는 이유: 좌표 변환·핸드셰이크 버그가 실물에서 터지면
   **로봇이 엉뚱한 좌표로 움직인다.** 사람이 옆에 있는 협동로봇이다.

동작 (예승님 운영 로직 `sequence_service`의 상대역)
----------------------------------------------------
  200 Robot Ready  = 1 (대기 중) → 명령 수신하면 0
  206 Robot Moved  = 0 → 트리거(150=1) 받으면 `--move-seconds` 후 1
  130/131~135      = PC가 쓰는 명령·파라미터 (읽어서 로그)
  140~145          = PC가 쓰는 빈피킹 좌표 (읽어서 물리값으로 되돌려 로그)

⚠️ 이 서버는 **PC가 클라이언트**라는 전제다. 예승님 코드
   (`modbus_protocol.py:58 ModbusTcpClient`)가 로봇에 접속해서 쓰기 때문.
   기존 `src/communication/modbus_server.py`는 반대(비전PC=서버) 전제라 못 쓴다.

실행
----
  python3 bin_picking/tests/fake_robot_modbus.py --port 5020
  (실전 502는 root 필요 → 시뮬은 5020)

  다른 터미널에서:
  python3 bin_picking/tests/test_handshake_sim.py --port 5020
"""
from __future__ import annotations
import argparse
import threading
import time

try:
    from pymodbus.server import StartTcpServer
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
    try:
        # pymodbus 3.12에서 ModbusSlaveContext → ModbusDeviceContext로 개명됨.
        # 양쪽을 받아 버전 차이로 조용히 죽지 않게 한다(공장 PC 버전이 다를 수 있음).
        from pymodbus.datastore import ModbusDeviceContext as _DeviceCtx
    except ImportError:
        from pymodbus.datastore import ModbusSlaveContext as _DeviceCtx
except ImportError as e:
    raise SystemExit(f"pymodbus import 실패({e}) → .venv/binpick/bin/python 으로 실행하세요")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin_picking.src.communication.pick_encoder import (  # noqa: E402
    REG_COMMAND, REG_PARAM_START, REG_SEND_TRIGGER, REG_PC_READY,
    REG_ROBOT_READY, REG_ROBOT_MOVED,
    REG_PICK_X, REG_PICK_Y, REG_PICK_Z, REG_PICK_ANGLE,
    REG_PICK_PART_ID, REG_PICK_GRIP_W, decode_int16,
)

SIZE = 720   # 0~206 + 여유


class FakeRobot(threading.Thread):
    """레지스터를 폴링해 로봇처럼 반응한다."""

    def __init__(self, store, move_seconds: float = 1.0, verbose: bool = True):
        super().__init__(daemon=True)
        self.store = store
        self.move_seconds = move_seconds
        self.verbose = verbose
        self.stop_flag = threading.Event()
        self.cycles = 0
        self._moving_until = 0.0
        self._state = "IDLE"

    # pymodbus datastore는 (fx, addr, count) 규약. holding register = fx 3.
    def _get(self, addr: int) -> int:
        return self.store.getValues(3, addr, 1)[0]

    def _set(self, addr: int, val: int):
        self.store.setValues(3, addr, [val])

    def log(self, msg: str):
        if self.verbose:
            print(f"[robot] {msg}", flush=True)

    def run(self):
        self._set(REG_ROBOT_READY, 1)     # 처음엔 수신 가능
        self._set(REG_ROBOT_MOVED, 0)
        self.log("기동 — 200 Robot Ready=1, 206 Moved=0")

        while not self.stop_flag.is_set():
            time.sleep(0.02)
            trigger = self._get(REG_SEND_TRIGGER)

            if self._state == "IDLE" and trigger == 1:
                # Step 6에서 PC가 트리거를 올렸다 → 레지스터를 읽어간다.
                cmd = self._get(REG_COMMAND)
                params = [self._get(REG_PARAM_START + i) for i in range(5)]
                pick = {
                    "Xc": decode_int16(self._get(REG_PICK_X)),
                    "Yc": decode_int16(self._get(REG_PICK_Y)),
                    "Zc": decode_int16(self._get(REG_PICK_Z)),
                    "angle": decode_int16(self._get(REG_PICK_ANGLE)),
                    "part_id": self._get(REG_PICK_PART_ID),
                    "grip_w": self._get(REG_PICK_GRIP_W) / 10.0,
                }
                self.log(f"트리거 수신 — cmd={cmd} params={params}")
                self.log(f"  좌표 해석: X={pick['Xc']}mm Y={pick['Yc']}mm "
                         f"Z={pick['Zc']}mm angle={pick['angle']}° "
                         f"part={pick['part_id']} grip={pick['grip_w']}mm")
                self.last_pick = pick
                self._set(REG_ROBOT_READY, 0)          # 이제 바쁨
                self._moving_until = time.time() + self.move_seconds
                self._state = "MOVING"
                self.log(f"  모션 시작 ({self.move_seconds}s)")

            elif self._state == "MOVING" and time.time() >= self._moving_until:
                self._set(REG_ROBOT_MOVED, 1)          # Step 7 대기 해제
                self._state = "DONE"
                self.cycles += 1
                self.log("모션 완료 — 206 Moved=1")

            elif self._state == "DONE" and trigger == 0:
                # Step 8에서 PC가 트리거를 내렸다 → 사이클 종료, 다시 대기.
                self._set(REG_ROBOT_MOVED, 0)
                self._set(REG_ROBOT_READY, 1)
                self._state = "IDLE"
                self.log(f"사이클 {self.cycles} 종료 — 대기 복귀\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5020)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--move-seconds", type=float, default=1.0)
    args = ap.parse_args()

    block = ModbusSequentialDataBlock(0, [0] * SIZE)
    device = _DeviceCtx(hr=block)
    ctx = ModbusServerContext(devices=device, single=True)

    robot = FakeRobot(device, move_seconds=args.move_seconds)
    robot.start()

    print(f"가짜 로봇 Modbus TCP — {args.host}:{args.port}")
    print("Ctrl+C 로 종료\n")
    try:
        StartTcpServer(context=ctx, address=(args.host, args.port))
    except KeyboardInterrupt:
        print(f"\n종료. 완료 사이클 {robot.cycles}건")


if __name__ == "__main__":
    main()
