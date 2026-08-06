"""
빈피킹 좌표 소켓 서버 (우리 PC = 서버 / 로봇 = 클라이언트)
============================================================

협력사가 준 예시(`rodi_tcp_motion_server.py`)를 우리 운영 조건에 맞게 새로 짠 것.
**예시 원본은 그대로 보존**하고(`/data/jtm/synth_out/hanwha_rodi_script/rodi_tcp/`)
이 파일이 실사용 구현이다.

⭐ 왜 예시를 그대로 못 쓰는가
------------------------------
예시는 "TCP가 통하는지" 보여주는 1회성 데모다. 실운영과 다른 점이 5가지 있다.

  1. **좌표를 접속 즉시 보낸다** — 빈피킹은 접속 후 촬영·추론에 수 초가 걸린다.
     로봇 쪽 `socketReadLine(name, 10000)`이 10초 타임아웃이므로 그 안에 보내야 한다.
  2. **1회 accept 후 종료** — 실운영은 사이클마다 반복해야 한다.
  3. **좌표 하드코딩** — 우리는 6요소 인식 결과에서 만든다.
  4. **검증이 전혀 없다** — 로봇 쪽 클라이언트도 받은 값을 그대로 `createPose`에
     넣고 즉시 `moveLinear`한다. 즉 **막을 곳이 서버뿐이다.**
  5. **예외 처리 없음** — 연결 끊김·타임아웃·잘못된 응답에 대응이 없다.

🔴 이 서버의 제1원칙 = "조용히 틀리지 말고 크게 실패하라"
----------------------------------------------------------
로봇 클라이언트에는 좌표 검증이 **없다**. 서버가 z=3136mm(7/29에 실제로 있었던
단위 버그)를 보내면 로봇은 의심 없이 그 높이로 뻗는다. 그래서 전송 직전에
`pick_encoder`의 물리 범위 검증을 통과하지 못한 좌표는 **보내지 않고 예외를 던진다.**

⚠️ 안전 절차 (협력사 예시 주석에 명시된 순서)
----------------------------------------------
예시 코드에 *"처음에는 빈 배열로 TCP 통신만 확인합니다 / 통신 확인 후 로봇에서
직접 티칭하고 검증한 좌표를 넣습니다"* 라고 적혀 있다. 이 순서를 지킨다.

  1단계 `--mode handshake`  : 빈 배열. TCP 왕복만 확인. 로봇 안 움직임.
  2단계 `--mode teach`      : 티칭으로 검증된 좌표 1개. 모션 확인.
  3단계 `--mode vision`     : 인식 결과 좌표. **hand-eye 캘리브 완료 후에만.**

🚨 3단계는 hand-eye 캘리브가 선행되어야 한다. 카메라 좌표를 로봇 좌표로 바꾸는
변환이 검증되기 전에는 인식이 맞아도 로봇은 엉뚱한 데로 간다.

프로토콜 (예시 코드에서 확인된 실제 규약)
------------------------------------------
  PC(서버)  →  로봇 : JSON 배열 + "\n"
                      [[x, y, z, rx, ry, rz], ...]   단위 mm / deg, 실수 OK
  로봇      →  PC   : "DONE\n"

  ⭐ 실수를 그대로 보낸다 → 7/30에 만든 INT16 1/10mm 인코딩은 **불필요**(폐기).
     단 `pick_encoder`의 **범위 검증 로직은 그대로 유효**하므로 재사용한다.
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

try:
    from .pick_encoder import PickEncodeError, XY_PLAUSIBLE_MM, Z_PLAUSIBLE_MM
except ImportError:  # 단독 실행 대비
    from pick_encoder import PickEncodeError, XY_PLAUSIBLE_MM, Z_PLAUSIBLE_MM

# ⭐ 출력 게이트(부품이 아닌 예측 제거). `src/pipeline/`에 있어 경로가 한 단계 다르다.
try:
    from ..pipeline import input_gate
except ImportError:  # 단독 실행 대비
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from pipeline import input_gate  # type: ignore


# ============================================================
# 설정
# ============================================================
DEFAULT_HOST = "0.0.0.0"     # 모든 인터페이스. 예시의 127.0.0.1은 같은 PC만 접속 가능
DEFAULT_PORT = 5000

# 로봇 쪽 socketReadLine 타임아웃이 10초 → 그 안에 좌표를 보내야 한다.
# 여유를 두고 8초로 잡는다. 추론이 이보다 오래 걸리면 설계를 바꿔야 한다.
SEND_DEADLINE_SEC = 8.0

# 로봇이 "DONE"을 보낼 때까지 기다리는 시간. 모션 시간이 포함되므로 넉넉히.
DONE_TIMEOUT_SEC = 120.0

# 회전 자세 기본값 — 6요소에는 angle(Z축 회전) 하나뿐이라 rx·ry는 우리가 정한다.
# 예시 코드의 티칭 좌표가 [180, 0, -90]이므로 수직 하강 자세로 추정.
# 🔴 실기에서 티칭으로 확인 후 확정할 값 [미확인]
DEFAULT_RX = 180.0
DEFAULT_RY = 0.0


class PickSocketError(RuntimeError):
    """소켓 계층 오류. 좌표 값 오류는 PickEncodeError를 쓴다."""


# ============================================================
# 좌표 검증 — 로봇에는 방어가 없으므로 여기가 마지막 관문
# ============================================================
def validate_pose(pose: Sequence[float], idx: int = 0) -> list[float]:
    """6DoF 포즈를 물리 범위로 검증한다. 통과하면 float 리스트를 돌려준다.

    ⭐ 클램프하지 않고 예외를 던진다. 범위를 벗어나는 값은 센서 고장이나
       단위 착오이므로, 잘라서 보내면 "엉뚱한 데로 가는데 에러는 없는" 상태가 된다.
    """
    if pose is None:
        raise PickEncodeError(f"pose[{idx}]: None")

    seq = list(pose)
    if len(seq) != 6:
        raise PickEncodeError(
            f"pose[{idx}]: 6개(x,y,z,rx,ry,rz)여야 하는데 {len(seq)}개 "
            f"— 6요소(x,y,z,edge,angle,label)를 그대로 넣지 않았는지 확인"
        )

    names = ("x", "y", "z", "rx", "ry", "rz")
    out: list[float] = []
    for name, value in zip(names, seq):
        if value is None:
            raise PickEncodeError(f"pose[{idx}].{name}: None")
        try:
            fval = float(value)
        except (TypeError, ValueError) as e:
            raise PickEncodeError(f"pose[{idx}].{name}: 숫자가 아님 ({value!r})") from e
        if not math.isfinite(fval):
            raise PickEncodeError(f"pose[{idx}].{name}: 유한한 값이 아님 ({fval})")
        out.append(fval)

    x, y, z, rx, ry, rz = out

    # z = 작업 거리. 7/29 실측 100장에서 99%가 400~600mm.
    # 🚨 3136mm(uint16 단위 착오)를 여기서 잡는다.
    zlo, zhi = Z_PLAUSIBLE_MM
    if not (zlo <= z <= zhi):
        raise PickEncodeError(
            f"pose[{idx}].z={z}mm 가 물리 범위 {zlo}~{zhi}mm 밖 "
            f"— depth 단위 착오(raw×10/65535=m)를 의심할 것"
        )

    for name, value in (("x", x), ("y", y)):
        if abs(value) > XY_PLAUSIBLE_MM:
            raise PickEncodeError(
                f"pose[{idx}].{name}={value}mm 가 물리 범위 ±{XY_PLAUSIBLE_MM}mm 밖"
            )

    for name, value in (("rx", rx), ("ry", ry), ("rz", rz)):
        if abs(value) > 360.0:
            raise PickEncodeError(f"pose[{idx}].{name}={value}° 가 ±360° 밖")

    return out


def six_elements_to_pose(
    det: dict,
    rx: float = DEFAULT_RX,
    ry: float = DEFAULT_RY,
    require_reliable_angle: bool = True,
) -> list[float]:
    """6요소 검출 1건 → 로봇 6DoF 포즈 [x, y, z, rx, ry, rz].

    🔴 6요소(x, y, z, edge, angle, label)를 그대로 보낼 수 없는 이유
    ---------------------------------------------------------------
      - `edge`(4코너)·`label`(부품 종류)은 **포즈가 아니다.** 그리퍼 벌림과
        부품 식별용이라 별도 경로로 보내야 한다.
      - 6요소의 `angle`은 **Z축 회전 하나**뿐이다. 로봇은 rx·ry·rz 3축을 받는다.
        → angle을 rz에 넣고, rx·ry는 파지 자세 기본값을 쓴다.
      - `x`·`y`는 **픽셀 좌표**다. 로봇에 보낼 것은 `camera_3d`(mm)다.

    ⚠️ 이 함수가 주는 좌표는 **카메라 좌표계**다. hand-eye 캘리브로 로봇
       베이스 좌표로 바꾸지 않으면 로봇이 엉뚱한 데로 간다. 변환은 상위에서 한다.
    """
    cam = det.get("camera_3d")
    if not cam:
        raise PickEncodeError(
            "camera_3d 없음 — 픽셀 좌표(x,y)만으로는 로봇을 못 움직인다"
        )

    # ⚠️ 실측 JSON은 dict {"Xc","Yc","Zc"} 형식이다(`coord_frame` =
    #    blaze_depth_pixel_and_camera_mm). 처음에 배열로 가정했다가 틀렸다 —
    #    ⭐ 키 이름·자료구조는 추측하지 말고 파일을 열어볼 것(7/31 predictions
    #    키 오독과 같은 유형). 리스트 형식도 함께 받아 둔다.
    if isinstance(cam, dict):
        try:
            xyz = [cam["Xc"], cam["Yc"], cam["Zc"]]
        except KeyError as e:
            raise PickEncodeError(
                f"camera_3d dict에 {e} 키가 없다 (받은 키: {list(cam)})"
            ) from e
    else:
        xyz = list(cam)
        if len(xyz) != 3:
            raise PickEncodeError(f"camera_3d가 3개여야 하는데 {len(xyz)}개")

    angle = det.get("angle")
    if angle is None:
        raise PickEncodeError("angle 없음")

    # ⚠️ reliable=False = 거의 정사각형(각도 무의미) 또는 마스크 깨짐.
    #    7/30 실측에서 801건 중 155건이 여기 해당했다. 로봇이 이 플래그를 봐야 한다.
    if require_reliable_angle and det.get("angle_reliable") is False:
        raise PickEncodeError(
            f"angle_reliable=False — 각도를 신뢰할 수 없다 "
            f"({det.get('angle_note', '')}). 파지 실패 위험이 있어 거부한다"
        )

    xc, yc, zc = (float(v) for v in xyz)
    return validate_pose([xc, yc, zc, rx, ry, float(angle)])


# ============================================================
# 서버
# ============================================================
@dataclass
class CycleResult:
    """한 사이클(로봇 1회 접속) 결과."""
    peer: str = ""
    poses_sent: list = field(default_factory=list)
    response: str = ""
    prepare_sec: float = 0.0
    done_sec: float = 0.0
    ok: bool = False
    error: str = ""


class PickSocketServer:
    """로봇이 접속하면 좌표를 주고 완료 응답을 받는다.

    예시와 달리 **반복**하고, **보내기 전에 검증**하고, **타임아웃을 건다.**
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        send_deadline: float = SEND_DEADLINE_SEC,
        done_timeout: float = DONE_TIMEOUT_SEC,
        verbose: bool = True,
    ):
        self.host = host
        self.port = port
        self.send_deadline = send_deadline
        self.done_timeout = done_timeout
        self.verbose = verbose
        self._sock: Optional[socket.socket] = None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[pick-server] {msg}", flush=True)

    def __enter__(self) -> "PickSocketServer":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self._sock = s
        self._log(f"listening {self.host}:{self.port}")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            self._log("closed")

    def serve_cycle(
        self,
        pose_provider: Callable[[], Iterable[Sequence[float]]],
        accept_timeout: Optional[float] = None,
    ) -> CycleResult:
        """로봇 접속 1건을 처리한다.

        pose_provider
            호출 시점에 포즈 리스트를 만들어 주는 함수. **접속 후에 호출**되므로
            여기서 촬영·추론을 해도 된다. 단 `send_deadline` 안에 끝나야 한다.
        """
        if self._sock is None:
            raise PickSocketError("open() 먼저 호출할 것")

        result = CycleResult()
        self._sock.settimeout(accept_timeout)

        try:
            conn, addr = self._sock.accept()
        except socket.timeout:
            result.error = "accept 타임아웃 — 로봇이 접속하지 않았다"
            return result

        result.peer = f"{addr[0]}:{addr[1]}"
        self._log(f"로봇 접속: {result.peer}")

        with conn:
            # ── 좌표 준비 (촬영·추론이 여기서 일어난다) ──
            t0 = time.monotonic()
            try:
                raw_poses = list(pose_provider())
            except Exception as e:
                result.error = f"좌표 생성 실패: {e}"
                self._log(f"🔴 {result.error}")
                return result
            result.prepare_sec = time.monotonic() - t0

            # 🚨 로봇에는 검증이 없다. 여기가 마지막 관문.
            try:
                poses = [validate_pose(p, i) for i, p in enumerate(raw_poses)]
            except PickEncodeError as e:
                result.error = f"좌표 검증 실패(전송 안 함): {e}"
                self._log(f"🔴 {result.error}")
                return result

            if result.prepare_sec > self.send_deadline:
                result.error = (
                    f"좌표 준비에 {result.prepare_sec:.1f}초 걸림 "
                    f"— 로봇 socketReadLine 타임아웃(10초) 초과 위험. "
                    f"보내지 않는다"
                )
                self._log(f"🔴 {result.error}")
                return result

            # ── 전송 ──
            payload = json.dumps(poses) + "\n"
            try:
                conn.sendall(payload.encode("utf-8"))
            except OSError as e:
                result.error = f"전송 실패: {e}"
                self._log(f"🔴 {result.error}")
                return result

            result.poses_sent = poses
            self._log(
                f"전송 {len(poses)}개 (준비 {result.prepare_sec:.2f}초): {poses}"
            )

            # ── 완료 응답 대기 ──
            t1 = time.monotonic()
            conn.settimeout(self.done_timeout)
            buf = b""
            try:
                while b"\n" not in buf:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    buf += chunk
            except socket.timeout:
                result.error = (
                    f"완료 응답 {self.done_timeout}초 타임아웃 "
                    f"— 로봇이 모션 중이거나 멈췄다"
                )
                self._log(f"🔴 {result.error}")
                return result
            result.done_sec = time.monotonic() - t1

            result.response = buf.decode("utf-8", "replace").strip()
            if not result.response:
                result.error = "로봇이 응답 없이 연결을 끊었다"
                self._log(f"🔴 {result.error}")
                return result

            if result.response != "DONE":
                result.error = f"예상 밖 응답: {result.response!r} (기대값 'DONE')"
                self._log(f"⚠️ {result.error}")
                return result

            result.ok = True
            self._log(f"✅ DONE 수신 (모션 {result.done_sec:.1f}초)")
            return result

    def serve_forever(
        self,
        pose_provider: Callable[[], Iterable[Sequence[float]]],
        max_cycles: Optional[int] = None,
    ) -> list[CycleResult]:
        """사이클을 반복한다. 한 사이클 실패가 서버를 죽이지 않는다."""
        results: list[CycleResult] = []
        n = 0
        while max_cycles is None or n < max_cycles:
            n += 1
            self._log(f"── 사이클 {n} 대기 ──")
            res = self.serve_cycle(pose_provider)
            results.append(res)
            if not res.ok:
                self._log(f"사이클 {n} 실패: {res.error} (계속 대기)")
        return results


# ============================================================
# CLI — 3단계 안전 절차
# ============================================================
def _provider_handshake() -> list:
    """1단계: 빈 배열. TCP 왕복만 확인. 로봇은 움직이지 않는다."""
    return []


def _provider_teach(pose: Sequence[float]) -> Callable[[], list]:
    """2단계: 티칭으로 검증된 좌표. 모션까지 확인."""
    def provider() -> list:
        return [list(pose)]
    return provider


def _provider_vision(json_path: str, limit: int) -> Callable[[], list]:
    """3단계: 6요소 인식 결과 → 포즈.

    🚨 hand-eye 캘리브 완료 후에만 쓸 것. 카메라 좌표를 그대로 보내면
       로봇 베이스 기준이 아니라서 엉뚱한 위치로 간다.
    """
    def provider() -> list:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        dets = data.get("detections") or data.get("predictions") or []
        # ⚠️ 키 이름을 추측하지 않는다 — 7/31에 predictions를 detections로
        #    잘못 읽어 집계가 0건으로 나온 전례가 있다.
        if not dets:
            # ⭐ 왜 비었는지를 함께 말한다 — "비어 있다"만 보면 원인을 찾으러
            #   엉뚱한 데를 뒤진다. 게이트가 이미 걸러낸 파일일 수 있다.
            hint = ""
            gs = data.get("gate_scene")
            if isinstance(gs, dict) and not gs.get("trusted", True):
                hint = f" | 장면 게이트: {gs.get('note')}"
            n_dropped = len(data.get("gate_dropped") or [])
            if n_dropped:
                hint += f" | 크기 게이트가 이미 {n_dropped}건을 제거했다"
            raise PickEncodeError(
                f"{json_path}: 보낼 검출이 없다{hint}"
            )

        # ⭐⭐ 출력 게이트 = 부품이 아닌 예측(화면을 덮는 덩어리)을 로봇에 보내지 않는다.
        #   근거(8/5 실측 → 8/6 정정) = 진짜 TP 예측 최대 223px인데 c2·c3의 오검출은
        #   434~573px로 나온다. 230px 상한으로 **c1(실운영)은 무해(F1 변화 0)**,
        #   c2 위치 precision 0.338→0.512, 전체 FP 194→117건.
        #   🚨 만들어두고 호출하지 않으면 의미가 없다 — 8/5에 `depth_units.py`를 단일
        #      출처로 만들었는데 `convert()`가 그걸 안 써서 좌표가 전건 무효였던 전례.
        gated, dropped = input_gate.filter_detections(dets)
        if dropped:
            print(f"[pick-server] 크기 게이트 제거 {len(dropped)}건 "
                  f"(>{input_gate.MAX_PART_SIDE_PX}px = 부품이 아니다)")
            for d in dropped[:5]:
                print(f"    - {d.get('label', '?')}: {d['gate']['reason']}")
        if not gated:
            raise PickEncodeError(
                f"크기 게이트가 검출 {len(dets)}건을 전부 걸러냈다 — "
                "장면이 학습 조건과 다를 가능성이 크다(빈 밖 물체·거리 이탈). "
                "사람이 확인할 것."
            )
        dets = gated

        # ⭐ 입력 게이트(장면) = 6요소 JSON에 장면 판정이 실려 있으면 경고한다.
        #   🚨 여기서 조용히 멈추지 않는다 — 멈출지 말지는 운영 정책이고,
        #      경고를 눈에 보이게 남기는 것이 이 계층의 역할이다.
        scene = data.get("gate_scene")
        if isinstance(scene, dict) and not scene.get("trusted", True):
            print(f"[pick-server] ⚠️ 장면 게이트 경고: {scene.get('note')}")
        # ⭐ 건별로 걸러낸다 — 한 건이 신뢰불가라고 나머지 정상 검출까지
        #    버리면 안 된다(첫 구현이 그랬고, vision 모드가 통째로 실패했다).
        #    로봇은 집을 수 있는 것만 받으면 된다.
        poses, skipped = [], []
        for i, det in enumerate(dets):
            if len(poses) >= limit:
                break
            try:
                poses.append(six_elements_to_pose(det))
            except PickEncodeError as e:
                skipped.append(f"#{i}({det.get('label', '?')}): {e}")
        if skipped:
            print(f"[pick-server] 건너뜀 {len(skipped)}건")
            for s in skipped[:5]:
                print(f"    - {s}")
        if not poses:
            raise PickEncodeError(
                f"보낼 수 있는 좌표가 없다 (검출 {len(dets)}건 전부 거부)"
            )
        return poses
    return provider


def main() -> int:
    ap = argparse.ArgumentParser(
        description="빈피킹 좌표 소켓 서버 (로봇=클라이언트)"
    )
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help="바인드 주소 (기본 0.0.0.0 = 모든 인터페이스)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--mode", choices=("handshake", "teach", "vision"),
                    default="handshake",
                    help="handshake=빈 배열(로봇 안 움직임) / "
                         "teach=티칭 검증 좌표 / vision=인식 결과(hand-eye 필요)")
    ap.add_argument("--pose", type=float, nargs=6,
                    metavar=("X", "Y", "Z", "RX", "RY", "RZ"),
                    help="--mode teach 에서 쓸 티칭 검증 좌표")
    ap.add_argument("--six-json",
                    help="--mode vision 에서 쓸 6요소 결과 JSON")
    ap.add_argument("--limit", type=int, default=1,
                    help="vision 모드에서 보낼 최대 포즈 개수 (기본 1)")
    ap.add_argument("--cycles", type=int, default=1,
                    help="처리할 사이클 수. 0=무한")
    args = ap.parse_args()

    if args.mode == "handshake":
        provider: Callable[[], Iterable[Sequence[float]]] = _provider_handshake
        print("── 1단계: 통신 확인 (빈 배열, 로봇은 움직이지 않는다) ──")
    elif args.mode == "teach":
        if not args.pose:
            ap.error("--mode teach 에는 --pose X Y Z RX RY RZ 가 필요하다")
        try:
            validate_pose(args.pose)
        except PickEncodeError as e:
            print(f"🔴 좌표 검증 실패: {e}")
            return 2
        provider = _provider_teach(args.pose)
        print(f"── 2단계: 티칭 검증 좌표 1개 전송 {list(args.pose)} ──")
    else:
        if not args.six_json:
            ap.error("--mode vision 에는 --six-json 이 필요하다")
        provider = _provider_vision(args.six_json, args.limit)
        print("── 3단계: 인식 결과 전송 ──")
        print("🚨 hand-eye 캘리브가 끝나지 않았다면 좌표계가 달라 "
              "로봇이 엉뚱한 데로 간다. 확인 후 진행할 것.")

    max_cycles = None if args.cycles == 0 else args.cycles
    with PickSocketServer(args.host, args.port) as server:
        results = server.serve_forever(provider, max_cycles=max_cycles)

    ok = sum(1 for r in results if r.ok)
    print(f"\n결과: {ok}/{len(results)} 성공")
    for i, r in enumerate(results, 1):
        mark = "✅" if r.ok else "🔴"
        detail = r.error if r.error else f"{len(r.poses_sent)}개 전송, {r.response}"
        print(f"  {mark} 사이클 {i}: {detail}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
