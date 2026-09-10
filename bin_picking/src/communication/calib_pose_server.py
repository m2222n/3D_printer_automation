"""
hand-eye 샘플 수신 서버 — 로봇이 보고한 TCP 포즈를 받고, 그 순간 카메라를 찍어 (pose, image) 쌍을 적재한다
=======================================================================================================

🎯 왜 있는가 (9/8 재택 조사 → 9/10 신설)
--------------------------------------
카메라를 로봇 팔에 달면(eye-in-hand) "카메라 좌표 → 로봇 좌표" 변환에 **그 순간의 로봇 자세**가 들어간다.
그래서 자세 N개(10~15)마다 (로봇 TCP 포즈, 카메라 영상) 쌍이 필요하다.

🚨 현행 경로는 **로봇이 클라이언트**라 PC가 로봇에 "지금 어디냐"고 물어볼 수 없다
(`pick_socket_server.py`는 PC가 좌표를 **보내고** 로봇이 DONE 을 돌려주는 방향).
⇒ 방향이 반대인 서버가 하나 더 필요하다 = 이 파일. **로봇이 포즈를 보고**하고 PC 가 받는다.

프로토콜 (펜던트 `rodi_pick_sequence.js` MODE 'calib' · `rodi_calib_tiny.js` 와 짝)
--------------------------------------------------------------------------------
  로봇 → PC : {"kind":"calib","tcp":[x,y,z,rx,ry,rz],"unit":"mm_deg"}\n   (배열만 와도 받는다)
  PC  → 로봇: "OK n\n"  (n = 지금까지 쌓인 샘플 수)  /  "ERR <사유>\n"

  한 접속 = 샘플 하나. 로봇 쪽 `socketReadLine` 상한이 15000ms(9/7 실측)라
  "다음 자세까지 연결을 열어 두고 기다리는" 설계는 안 된다 ⇒ 사람이 로봇을 옮기고 스크립트를 다시 ▶ 실행한다.

🔴 제1원칙 = "조용히 틀리지 말고 크게 실패하라" (pick_socket_server 와 같다)
----------------------------------------------------------------------
  - 6요소가 아니거나 NaN/inf 면 거부
  - |x|,|y|,|z| 가 전부 5 미만이면 **m 단위 의심**으로 거부 (hand_eye_calibration.py 는 m, 로봇은 mm — 9/8 §8 "조용히 틀릴 자리 ①")
  - |xyz| > 3000mm 또는 |각도| > 360 이면 거부 (10L 도달 1800mm · z=3136 사고 형태)
  - 카메라 트리거가 실패하면 **포즈만 저장하지 않고 ERR 로 돌려준다** — 영상 없는 포즈는 hand-eye 에 못 쓰고,
    "OK" 를 받은 사람은 다음 자세로 넘어가 버린다.
  - 오일러 규약(rx,ry,rz 가 ZYX 인지)은 여기서 판단하지 않는다. **원값을 그대로 저장**하고 계산 단계에서 정한다
    ⇒ 규약이 틀려도 데이터는 훼손되지 않는다(9/8 §8 "조용히 틀릴 자리 ②" 를 채집 단계에서 격리).

📁 출력 = `<out>/samples.json`(누적 · 이어받기) + `<out>/NNN_depth.npy` (+ `NNN_rgb.png`)
  ⭐ 8/24 촬영기처럼 **중단돼도 이어진다** — 기존 samples.json 이 있으면 다음 번호부터 쌓는다.

사용
----
  python -m bin_picking.src.communication.calib_pose_server --out /path/calib_0911 --capture none    # 포즈만(왕복 시험)
  python -m bin_picking.src.communication.calib_pose_server --out /path/calib_0911 --capture blaze   # Blaze depth(+ACE2)
  🚨 포트 5000 은 pick_socket_server 와 같다 — 둘을 동시에 띄우지 않는다.
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
READ_TIMEOUT_SEC = 15.0          # 로봇이 접속 후 한 줄 보내는 데 걸리는 시간 상한

XYZ_MAX_MM = 3000.0              # HCR-10L 도달 1800mm + 여유. z=3136(7/29 사고) 같은 값은 거부
ANG_MAX_DEG = 360.0
METER_SUSPECT_MM = 5.0           # |x|,|y|,|z| 전부 이 미만 = m 단위로 보낸 것 의심


class CalibPoseError(ValueError):
    """포즈 한 줄이 규약에 어긋난다. 저장하지 않고 ERR 로 돌려준다."""


# ============================================================
# 포즈 파싱·검증
# ============================================================
def validate_tcp(tcp: Sequence[float]) -> list[float]:
    if not isinstance(tcp, (list, tuple)) or len(tcp) != 6:
        raise CalibPoseError(f"tcp 는 6요소여야 한다 (받은 것: {tcp!r})")
    vals: list[float] = []
    for i, v in enumerate(tcp):
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise CalibPoseError(f"tcp[{i}]={v!r} 숫자가 아니다")
        if not math.isfinite(f):
            raise CalibPoseError(f"tcp[{i}]={v!r} NaN/inf")
        vals.append(f)
    x, y, z, rx, ry, rz = vals
    if all(abs(c) < METER_SUSPECT_MM for c in (x, y, z)):
        raise CalibPoseError(
            f"xyz={vals[:3]} 전부 |v|<{METER_SUSPECT_MM} — m 단위로 보낸 것 아닌가? 이 서버는 mm 만 받는다"
        )
    for name, c in zip("xyz", (x, y, z)):
        if abs(c) > XYZ_MAX_MM:
            raise CalibPoseError(f"{name}={c} — |{name}|>{XYZ_MAX_MM}mm 는 로봇 도달 밖(단위 오류 의심)")
    for name, a in zip(("rx", "ry", "rz"), (rx, ry, rz)):
        if abs(a) > ANG_MAX_DEG:
            raise CalibPoseError(f"{name}={a} — |각도|>{ANG_MAX_DEG}deg (rad/deg 혼동 의심)")
    return vals


def parse_pose_line(line: str) -> list[float]:
    """로봇이 보낸 한 줄 → [x,y,z,rx,ry,rz] (mm·deg). 규약 위반은 CalibPoseError."""
    line = line.strip()
    if not line:
        raise CalibPoseError("빈 줄")
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise CalibPoseError(f"JSON 아님: {e} — 받은 줄: {line[:80]!r}")
    if isinstance(obj, dict):
        kind = obj.get("kind", "calib")
        if kind != "calib":
            raise CalibPoseError(f"kind={kind!r} — 이 서버는 'calib' 만 받는다")
        unit = obj.get("unit", "mm_deg")
        if unit != "mm_deg":
            raise CalibPoseError(f"unit={unit!r} — 'mm_deg' 만 받는다 (변환은 하지 않는다)")
        tcp = obj.get("tcp")
    else:
        tcp = obj
    return validate_tcp(tcp)


# ============================================================
# 저장
# ============================================================
@dataclass
class CalibSample:
    idx: int
    ts: str
    tcp_mm_deg: list[float]
    peer: str
    depth_path: Optional[str] = None
    rgb_path: Optional[str] = None
    note: str = ""


class CalibSampleStore:
    """`<out>/samples.json` 누적. 이미 있으면 이어받는다(8/24 촬영기 설계)."""

    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.out_dir / "samples.json"
        self.samples: list[dict] = []
        if self.path.exists():
            self.samples = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def next_idx(self) -> int:
        return (max((s["idx"] for s in self.samples), default=0) + 1)

    def add(self, sample: CalibSample) -> int:
        self.samples.append(asdict(sample))
        self.path.write_text(json.dumps(self.samples, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(self.samples)


# ============================================================
# 카메라 트리거 — 호출 가능 객체 하나로 격리 (없으면 포즈만 기록)
# ============================================================
CaptureFn = Callable[[int, Path], dict]   # (idx, out_dir) -> {"depth_path": str, "rgb_path": str|None}


def make_blaze_capture(blaze_ip: str, ace2_ip: Optional[str] = None) -> CaptureFn:
    """Blaze Range 한 장(+ACE2 컬러 한 장) grab. 8/28 IPC 검증 4줄과 같은 경로.

    🚨 pypylon 이 없으면 **여기서 즉시** 실패한다 — 현장에서 첫 샘플을 받고서야 알면 늦다.
    ⚠️ ACE2 경로는 8/24 확립값(BayerRG8 → cv2 COLOR_BayerBG2BGR)을 옮긴 것이고 이 파일로는 [미검증].
    """
    try:
        from pypylon import pylon  # type: ignore
    except ImportError as e:
        raise RuntimeError("pypylon 이 없다 — --capture none 으로 포즈만 받거나 pypylon 을 설치할 것") from e
    import numpy as np  # 지연 import: 테스트 환경에서 불필요

    tl = pylon.TlFactory.GetInstance().CreateTl("BaslerGigE")   # 🚨 EnumerateDevices 는 항상 0 (8/28)

    def _find(ip: str):
        devs = [d for d in tl.EnumerateAllDevices() if d.GetIpAddress() == ip]
        if not devs:
            raise RuntimeError(f"카메라 {ip} 열거 안 됨 — 랜선·포트 IP(.20.1/.20.2)·링크 협상(몇 초) 확인")
        return pylon.InstantCamera(tl.CreateDevice(devs[0]))

    def capture(idx: int, out_dir: Path) -> dict:
        out: dict = {"depth_path": None, "rgb_path": None}
        cam = _find(blaze_ip)
        cam.Open()
        try:
            cam.ComponentSelector.SetValue("Range")
            cam.ComponentEnable.SetValue(True)
            cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            r = cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)   # 🚨 타임아웃 = 방화벽(8/28)
            arr = np.array(r.Array, copy=True)
            r.Release()
            cam.StopGrabbing()
        finally:
            cam.Close()
        if arr.shape != (480, 848):
            raise RuntimeError(f"Blaze depth 모양 {arr.shape} — 기대 (480, 848)")
        p = out_dir / f"{idx:03d}_depth.npy"
        np.save(p, arr.astype(np.uint16))
        out["depth_path"] = str(p)

        if ace2_ip:
            import cv2  # 지연 import
            c2 = _find(ace2_ip)
            c2.Open()
            try:
                c2.PixelFormat.SetValue("BayerRG8")             # 8/24: BGR8 은 대역 초과로 0/5
                c2.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                r2 = c2.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
                raw = np.array(r2.Array, copy=True)
                r2.Release()
                c2.StopGrabbing()
            finally:
                c2.Close()
            bgr = cv2.cvtColor(raw, cv2.COLOR_BayerBG2BGR)     # 8/24: Basler RG ≠ OpenCV RG (R/B 뒤바뀜 방지)
            p2 = out_dir / f"{idx:03d}_rgb.png"
            cv2.imwrite(str(p2), bgr)
            out["rgb_path"] = str(p2)
        return out

    return capture


# ============================================================
# 서버
# ============================================================
class CalibPoseServer:
    def __init__(
        self,
        store: CalibSampleStore,
        capture: Optional[CaptureFn] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        read_timeout: float = READ_TIMEOUT_SEC,
        verbose: bool = True,
    ):
        self.store = store
        self.capture = capture
        self.host = host
        self.port = port
        self.read_timeout = read_timeout
        self.verbose = verbose
        self._sock: Optional[socket.socket] = None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[calib-server] {msg}", flush=True)

    def open(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self.port = s.getsockname()[1]      # port=0 이면 OS 가 고른 값(테스트용)
        self._sock = s
        self._log(f"listening {self.host}:{self.port} · 저장 {self.store.out_dir} · 기존 샘플 {len(self.store.samples)}개"
                  f" · 카메라 {'있음' if self.capture else '없음(포즈만)'}")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> "CalibPoseServer":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def _read_line(conn: socket.socket) -> str:
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buf += chunk
        return buf.decode("utf-8", "replace")

    def serve_one(self, accept_timeout: Optional[float] = None) -> Optional[CalibSample]:
        """접속 1건 = 샘플 1개. 거부·실패는 None (서버는 계속 산다)."""
        if self._sock is None:
            raise RuntimeError("open() 먼저")
        self._sock.settimeout(accept_timeout)
        try:
            conn, addr = self._sock.accept()
        except socket.timeout:
            return None
        peer = f"{addr[0]}:{addr[1]}"
        with conn:
            conn.settimeout(self.read_timeout)
            try:
                line = self._read_line(conn)
            except socket.timeout:
                self._log(f"🔴 {peer} 접속 후 {self.read_timeout}s 안에 한 줄이 안 왔다")
                return None

            try:
                tcp = parse_pose_line(line)
            except CalibPoseError as e:
                self._log(f"🔴 거부: {e}")
                self._reply(conn, f"ERR {e}")
                return None

            idx = self.store.next_idx
            depth_path = rgb_path = None
            if self.capture is not None:
                try:
                    cap = self.capture(idx, self.store.out_dir)
                    depth_path, rgb_path = cap.get("depth_path"), cap.get("rgb_path")
                except Exception as e:  # noqa: BLE001 — 어떤 실패든 ERR 로 알린다
                    self._log(f"🔴 카메라 트리거 실패(포즈 저장 안 함): {e}")
                    self._reply(conn, f"ERR capture_failed: {e}")
                    return None

            sample = CalibSample(
                idx=idx,
                ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
                tcp_mm_deg=tcp,
                peer=peer,
                depth_path=depth_path,
                rgb_path=rgb_path,
                note="raw getCurrentPose('tcp') · 오일러 규약 미판정(계산 단계에서 결정)",
            )
            n = self.store.add(sample)
            self._reply(conn, f"OK {n}")
            self._log(f"✅ 샘플 {idx} 저장 ({n}개) tcp={tcp}"
                      + (f" depth={Path(depth_path).name}" if depth_path else " (포즈만)"))
            return sample

    def _reply(self, conn: socket.socket, text: str) -> None:
        try:
            conn.sendall((text + "\n").encode("utf-8"))
        except OSError as e:
            self._log(f"⚠️ 응답 전송 실패: {e}")

    def serve_forever(self, max_samples: Optional[int] = None) -> int:
        got = 0
        while max_samples is None or got < max_samples:
            self._log(f"── 샘플 {self.store.next_idx} 대기 (로봇을 자세로 옮기고 calib 스크립트 ▶) ──")
            if self.serve_one() is not None:
                got += 1
        return got


# ============================================================
# CLI
# ============================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="hand-eye 샘플 수신 서버 (로봇=클라이언트 · 포즈 보고 → 카메라 트리거)")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--out", required=True, help="샘플 저장 폴더 (있으면 이어받는다)")
    ap.add_argument("--capture", choices=("none", "blaze"), default="none",
                    help="none=포즈만(왕복 시험) / blaze=Blaze depth(+--ace2-ip 주면 컬러도)")
    ap.add_argument("--blaze-ip", default="192.168.20.10")
    ap.add_argument("--ace2-ip", default=None, help="ACE2 IP (8/28 IPC 실측 192.168.20.20). 비우면 depth 만")
    ap.add_argument("--max", type=int, default=0, help="받을 샘플 수. 0=무한")
    ap.add_argument("--read-timeout", type=float, default=READ_TIMEOUT_SEC)
    args = ap.parse_args()

    capture = None
    if args.capture == "blaze":
        capture = make_blaze_capture(args.blaze_ip, args.ace2_ip)   # pypylon 없으면 여기서 즉시 실패

    store = CalibSampleStore(Path(args.out))
    print("── hand-eye 샘플 채집 · 한 접속 = 한 샘플 · 로봇은 스크립트 실행 중 움직이지 않는다 ──")
    print("🚨 로봇을 옮길 때는 스크립트를 멈춘 상태에서(직접교시/조그) · 정지 후 ▶ 실행")
    with CalibPoseServer(store, capture, args.host, args.port, args.read_timeout) as server:
        n = server.serve_forever(None if args.max == 0 else args.max)
    print(f"\n받은 샘플 {n}개 · 누적 {len(store.samples)}개 → {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
