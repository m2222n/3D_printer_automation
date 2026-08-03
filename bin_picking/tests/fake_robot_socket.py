"""
가짜 로봇 소켓 클라이언트 — 실물 없이 서버를 검증한다
=======================================================

협력사 예시 `rodi_tcp_motion_client.js`(펜던트 JS)가 하는 일을 파이썬으로 흉내낸다.
로봇·펜던트 없이 `pick_socket_server.py`를 왕복 검증하는 것이 목적이다.

⭐ 왜 필요한가
---------------
7/30에 `fake_robot_modbus.py`로 시뮬한 덕에 **pymodbus 3.12 API 개명을
공장 가기 전에** 발견했다(`ModbusSlaveContext`→`ModbusDeviceContext`). 시뮬을
안 했으면 현장에서 터졌을 종류다. 소켓도 같은 이유로 미리 돌려본다.

🔴 10L 드라이버 오류(`[CODE 301016]`)로 실기 검증이 막혀 있는 동안,
   서버 로직만이라도 여기서 끝내 둔다.

예시 JS가 하는 순서 (그대로 재현)
----------------------------------
  socketCreate(name, ip, port)      → socket.socket()
  socketOpen(name)                  → connect()
  socketWaitConnection(name, 10000) → (connect가 겸함)
  socketReadLine(name, 10000)       → recv until "\n"   ← 타임아웃 10초
  JSON.parse(line)                  → json.loads()
  createPose(...) / moveLinear(...)  → 모션 시간만큼 sleep
  socketSendLine(name, "DONE")      → sendall("DONE\n")
  socketDisconnect(name)            → close()

⚠️ 이것은 **문법·프로토콜 검증**이다. 실제 로봇이 이 JSON을 어떻게 소화하는지는
   실기에서만 확인된다. "시뮬 통과 = 실기 동작"이 아니다.
"""
from __future__ import annotations

import argparse
import json
import socket
import time

# 예시 JS의 socketReadLine(socketName, 10000) = 10초
READ_TIMEOUT_SEC = 10.0

# moveLinear("tcp", pose, 20, 100) = 20mm/s. 포즈당 대략 이 정도 걸린다고 가정.
FAKE_MOTION_SEC = 1.0


def run_fake_robot(
    host: str,
    port: int,
    read_timeout: float = READ_TIMEOUT_SEC,
    motion_sec: float = FAKE_MOTION_SEC,
    bad_response: str | None = None,
    drop_before_done: bool = False,
    verbose: bool = True,
) -> dict:
    """서버에 접속해 좌표를 받고 DONE을 보낸다. 결과를 dict로 돌려준다.

    bad_response
        "DONE" 대신 보낼 문자열. 서버의 예상 밖 응답 처리를 시험한다.
    drop_before_done
        DONE을 보내지 않고 연결을 끊는다. 서버의 끊김 처리를 시험한다.
    """
    def log(msg: str) -> None:
        if verbose:
            print(f"[fake-robot] {msg}", flush=True)

    out: dict = {"connected": False, "poses": [], "ok": False, "error": ""}

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(read_timeout)
        try:
            s.connect((host, port))
        except OSError as e:
            out["error"] = f"connect 실패: {e}"
            log(f"🔴 {out['error']}")
            return out

        out["connected"] = True
        log(f"접속 {host}:{port}")

        # ── socketReadLine 재현 ──
        buf = b""
        try:
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            out["error"] = (
                f"socketReadLine {read_timeout}초 타임아웃 "
                f"— 서버가 좌표를 제때 못 보냈다"
            )
            log(f"🔴 {out['error']}")
            return out

        line = buf.decode("utf-8", "replace").strip()
        if not line:
            out["error"] = "서버가 아무것도 안 보내고 끊었다"
            log(f"🔴 {out['error']}")
            return out

        # ── JSON.parse 재현 ──
        try:
            poses = json.loads(line)
        except json.JSONDecodeError as e:
            out["error"] = f"JSON 파싱 실패: {e} (받은 것: {line[:120]!r})"
            log(f"🔴 {out['error']}")
            return out

        if not isinstance(poses, list):
            out["error"] = f"배열이 아니다: {type(poses).__name__}"
            log(f"🔴 {out['error']}")
            return out

        out["poses"] = poses
        log(f"좌표 {len(poses)}개 수신: {poses}")

        # ── createPose / moveLinear 재현 ──
        for i, p in enumerate(poses):
            if not isinstance(p, (list, tuple)) or len(p) != 6:
                out["error"] = (
                    f"pose[{i}] 형식 오류: createPose는 6개 인자가 필요한데 "
                    f"{p!r} — 실제 로봇이라면 스크립트 오류로 정지한다"
                )
                log(f"🔴 {out['error']}")
                return out
            log(f"  moveLinear #{i} → {p} ({motion_sec}초)")
            time.sleep(motion_sec)

        if drop_before_done:
            log("⚠️ DONE 안 보내고 끊는다 (서버 예외 처리 시험)")
            return out

        # ── socketSendLine("DONE") 재현 ──
        reply = (bad_response if bad_response is not None else "DONE") + "\n"
        try:
            s.sendall(reply.encode("utf-8"))
        except OSError as e:
            out["error"] = f"응답 전송 실패: {e}"
            return out

        log(f"응답 전송: {reply.strip()!r}")
        out["ok"] = True
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description="가짜 로봇 소켓 클라이언트")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--read-timeout", type=float, default=READ_TIMEOUT_SEC)
    ap.add_argument("--motion-sec", type=float, default=FAKE_MOTION_SEC,
                    help="포즈당 가짜 모션 시간")
    ap.add_argument("--bad-response",
                    help="'DONE' 대신 보낼 문자열 (서버 처리 시험)")
    ap.add_argument("--drop", action="store_true",
                    help="DONE 안 보내고 끊기 (서버 처리 시험)")
    args = ap.parse_args()

    res = run_fake_robot(
        args.host, args.port,
        read_timeout=args.read_timeout,
        motion_sec=args.motion_sec,
        bad_response=args.bad_response,
        drop_before_done=args.drop,
    )
    print(f"\n결과: ok={res['ok']} poses={len(res['poses'])} "
          f"error={res['error'] or '없음'}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
