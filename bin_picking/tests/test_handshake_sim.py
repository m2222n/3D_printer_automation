#!/usr/bin/env python3
"""8단계 핸드셰이크 왕복 검증 — 가짜 로봇 상대로 실행.

⭐ 검증하는 것 = **예승님의 검증된 8단계를 빈피킹 좌표에 그대로 재사용할 수 있나**.
   새로 짜지 않는다. 예승님 `execute_command`가 레지스터를 전부 인자로 받게
   설계돼 있어(재사용 의도) 좌표 쓰기만 얹으면 된다.

실행 (터미널 2개):
  1) .venv/binpick/bin/python bin_picking/tests/fake_robot_modbus.py --port 5020
  2) .venv/binpick/bin/python bin_picking/tests/test_handshake_sim.py --port 5020
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pymodbus.client import ModbusTcpClient  # noqa: E402

from bin_picking.src.communication.pick_encoder import (  # noqa: E402
    encode_pick, build_part_id_map, decode_int16, CMD_BIN_PICK,
    REG_COMMAND, REG_SEND_TRIGGER, REG_PC_READY,
    REG_ROBOT_READY, REG_ROBOT_MOVED, REG_PICK_X, REG_PICK_Z,
)

_pass = _fail = 0


def check(name, cond, detail=""):
    global _pass, _fail
    if cond:
        _pass += 1; print(f"  ✅ {name}")
    else:
        _fail += 1; print(f"  ❌ {name}  {detail}")


class Handshake:
    """예승님 8단계(`modbus_protocol.py:33-131`)를 빈피킹용으로 옮긴 것.

    ⚠️ `PC_READY_OFF_DELAY`는 예승님 운영값이 **4.0초**인데 이유가 코드에 없다
       (`robot.py:509-511`은 동작만 적음). 로봇 쪽 사정(모션 정착·안전 확인)일
       가능성이 있어 **빈피킹도 지켜야 하는지 미해명** → 시뮬에서는 짧게 두고,
       실물 연결 전 반드시 확인. 여기서 0으로 두면 실물에서 다르게 동작할 수 있다.
    """

    def __init__(self, host, port, timeout=5.0, pc_ready_off_delay=0.2, trace=True):
        self.cli = ModbusTcpClient(host, port=port, timeout=timeout)
        self.timeout = timeout
        self.delay = pc_ready_off_delay
        self.trace = trace
        self.steps = []

    def log(self, msg):
        self.steps.append(msg)
        if self.trace:
            print(f"    [pc] {msg}")

    def _read(self, addr):
        rr = self.cli.read_holding_registers(address=addr, count=1)
        if rr.isError():
            raise RuntimeError(f"read {addr} 실패: {rr}")
        return rr.registers[0]

    def _write(self, addr, val):
        rr = self.cli.write_register(address=addr, value=val)
        if rr.isError():
            raise RuntimeError(f"write {addr}={val} 실패: {rr}")

    def _wait(self, addr, expect, label):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self._read(addr) == expect:
                return True
            time.sleep(0.02)
        raise TimeoutError(f"{label}: reg={addr} != {expect} ({self.timeout}s 초과)")

    def execute(self, pick_regs: dict, command_value: int = CMD_BIN_PICK):
        if not self.cli.connect():
            raise RuntimeError("연결 실패")
        try:
            # Step 1: 로봇이 수신 가능해질 때까지
            self._wait(REG_ROBOT_READY, 1, "robot_ready"); self.log("1. 200 Ready=1 확인")
            # Step 2: PC 선점
            self._write(REG_PC_READY, 1); self.log("2. 151 PC Ready=1")
            # Step 3: 이전 사이클의 완료 플래그가 내려갔는지
            self._wait(REG_ROBOT_MOVED, 0, "robot_moved(before)"); self.log("3. 206 Moved=0 확인")
            # Step 4: 지연 후 선점 해제
            if self.delay > 0:
                time.sleep(self.delay)
            self._write(REG_PC_READY, 0); self.log(f"4. 151=0 (delay {self.delay}s)")
            # Step 5: 명령 + 좌표 payload
            self._write(REG_COMMAND, command_value); self.log(f"5. 130 cmd={command_value}")
            for reg, val in sorted(pick_regs.items()):
                self._write(reg, val)
            self.log(f"   좌표 {len(pick_regs)}개 레지스터 기록 ({min(pick_regs)}~{max(pick_regs)})")
            # Step 6: 트리거
            self._write(REG_SEND_TRIGGER, 1); self.log("6. 150 트리거=1")
            # Step 7: 모션 완료 대기
            self._wait(REG_ROBOT_MOVED, 1, "robot_moved(after)"); self.log("7. 206 Moved=1 확인")
            # Step 8: 트리거 내림 (ACK)
            self._write(REG_SEND_TRIGGER, 0); self.log("8. 150=0 종료")
            return True
        finally:
            self.cli.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5020)
    ap.add_argument("--real", default="/data/jtm/synth_out/6elements_100/shot_009_g1_6elem.json")
    args = ap.parse_args()

    print("\n=== 1. 실측 6요소 → 인코딩 ===")
    data = json.load(open(args.real))
    dets = data["detections"]
    pmap = build_part_id_map([d["label"] for d in dets])
    d0 = dets[0]
    # ⚠️ require_angle=False: 현재 angle=0 고정(마스크 미저장). 실물 전 해소 필요.
    regs = encode_pick(d0, pmap[d0["label"]], 50.0, require_angle=False)
    print(f"  장면 {data['scene_id']} / 검출 {len(dets)}건 중 1건 전송")
    print(f"  {d0['label']}  X={d0['camera_3d']['Xc']} Y={d0['camera_3d']['Yc']} "
          f"Z={d0['camera_3d']['Zc']}mm")
    print(f"  → 레지스터 {regs}")

    print("\n=== 2. 8단계 핸드셰이크 ===")
    hs = Handshake(args.host, args.port)
    try:
        ok = hs.execute(regs)
    except Exception as e:
        print(f"  ❌ 핸드셰이크 실패: {type(e).__name__}: {e}")
        print("  → 가짜 로봇이 떠 있는지 확인: fake_robot_modbus.py --port %d" % args.port)
        sys.exit(1)
    check("8단계 전부 통과", ok and len(hs.steps) == 9, f"{len(hs.steps)} steps")

    print("\n=== 3. 로봇이 받은 값이 원본과 같은가 (조용한 손상 확인) ===")
    cli = ModbusTcpClient(args.host, port=args.port)
    cli.connect()
    got_x = decode_int16(cli.read_holding_registers(address=REG_PICK_X, count=1).registers[0])
    got_z = decode_int16(cli.read_holding_registers(address=REG_PICK_Z, count=1).registers[0])
    cli.close()
    check(f"X 왕복 ({d0['camera_3d']['Xc']}mm)", abs(got_x - d0["camera_3d"]["Xc"]) < 0.06, f"got {got_x}")
    check(f"Z 왕복 ({d0['camera_3d']['Zc']}mm)", abs(got_z - d0["camera_3d"]["Zc"]) < 0.06, f"got {got_z}")

    print("\n=== 4. 연속 3사이클 (상태 복귀 확인) ===")
    # 사이클이 끝나면 로봇이 IDLE로 돌아와야 다음 부품을 보낼 수 있다.
    # 안 돌아오면 2번째 사이클이 Step 1에서 타임아웃 → 실전에서 1개만 집고 멈춤.
    n_ok = 0
    for i in range(3):
        di = dets[i % len(dets)]
        r = encode_pick(di, pmap[di["label"]], 50.0, require_angle=False)
        try:
            h = Handshake(args.host, args.port, trace=False)
            h.execute(r)
            n_ok += 1
            print(f"  사이클 {i+1}: OK  {di['label']} Z={di['camera_3d']['Zc']}mm")
        except Exception as e:
            print(f"  사이클 {i+1}: 실패 {type(e).__name__}: {e}")
    check("3사이클 연속 성공", n_ok == 3, f"{n_ok}/3")

    print("\n=== 5. 타임아웃 동작 (로봇 무응답 시) ===")
    # 존재하지 않는 포트 → 연결 실패가 예외로 나와야 한다(조용히 성공하면 위험).
    try:
        Handshake(args.host, args.port + 1, timeout=1.0, trace=False).execute(regs)
        check("무응답 포트에서 예외", False, "조용히 통과함")
    except Exception as e:
        check(f"무응답 포트에서 예외 ({type(e).__name__})", True)

    print(f"\n{'='*46}\n결과: {_pass} 통과 / {_fail} 실패\n{'='*46}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
