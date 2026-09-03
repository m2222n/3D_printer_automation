"""
빈피킹 라이브 1사이클 — **촬영 → 추론 → 6요소 → 소켓 대기** 를 한 명령으로 (2026-09-04)
=====================================================================================

⭐ 왜 이 파일이 필요한가
  지금은 사람이 CLI 를 세 번 친다:
    ① 촬영   `blaze_ace2_capture_dual.py`(대화형 · s 키로 저장)
    ② 추론   `run_binpick_e2e --depth-dir …`
    ③ 소켓   `pick_socket_server --mode vision --six-json …`
  현장에서 세 번 치면 **파일 경로를 잘못 이어 붙이는 실수**가 난다(9/1 에도 six.json 경로를 손으로 맞췄다).
  ⇒ 이 스크립트가 셋을 이어 `MODE vision`(펜던트) 이 붙기를 기다린다.

🚨 검증 상태 (정직하게)
  · ②③ = 6000 에서 `--depth <npy>` + `fake_robot_socket.py` 로 **왕복 검증** (9/4)
  · ① 촬영 = 🔴 **카메라 없는 6000 에선 못 돌렸다** — `blaze_ace2_capture_dual.py` 의 검증된 함수(open_cam·setup_blaze)를
    그대로 import 해 **한 프레임만** 받는다. IPC 첫 실행 때 `--capture --no-server` 로 npy 한 장 먼저 확인할 것.
  · 상주 프로세스가 아니다 — 매 사이클 모델을 다시 로드한다(IPC 1.3초 + 로드). 데모엔 충분.

사용 (IPC · C:\binpick_venv):
  # 촬영 없이 기존 npy 로 (연습·재택)
  python -m bin_picking.src.run_live_pick --depth shot_001_c1.npy --checkpoint <OVN2 best.pt> --out-dir C:\live\r1
  # 실촬영 → 소켓 대기 (현장)
  python -m bin_picking.src.run_live_pick --capture --checkpoint <OVN2 best.pt> --out-dir C:\live\r1
  # 촬영만 확인
  python -m bin_picking.src.run_live_pick --capture --no-server --checkpoint <OVN2 best.pt> --out-dir C:\live\cap

🔒 IP·경로는 인자로만. 이 파일에 실제 값을 커밋하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bin_picking.src.utils.console_utf8 import enable_utf8_console  # noqa: E402  (cp949 방어 · 8/28)

CAPTURE_SCRIPT_DIR = REPO / "bin_picking" / "depth_track" / "scripts"
DEFAULT_BLAZE_IP = "192.168.20.10"      # 8/28 IPC 실측(카메라에 저장된 값) — 인자로 덮어쓸 수 있다
DEFAULT_THROUGHPUT = 30.0               # 8/24 실측: 낮추면 역효과(10→0/8, 30→8/8)


# ---------------------------------------------------------------------------
# ① 촬영 — 검증된 함수만 빌려 쓴다. 대화형 루프·cv2 창은 쓰지 않는다.
# ---------------------------------------------------------------------------
def capture_one(out_dir: Path, blaze_ip: str, throughput: float, stem: str) -> Path:
    sys.path.insert(0, str(CAPTURE_SCRIPT_DIR))
    try:
        from pypylon import pylon                    # noqa: F401
        import numpy as np
        import blaze_ace2_capture_dual as cap        # open_cam / setup_blaze = 7/28·8/18·8/28 성공 코드
    except Exception as e:                           # pypylon 없는 PC(6000)에서 --capture 를 치면 여기서 크게 실패한다
        raise SystemExit(f"🔴 촬영 준비 실패: {type(e).__name__}: {e}\n   IPC 의 C:\\binpick_venv 에서 실행하라(pypylon 포함).")

    print(f"[촬영] Blaze {blaze_ip} 열기 (throughput {throughput}Mbps)")
    cam = cap.open_cam(blaze_ip, throughput)
    try:
        cap.setup_blaze(cam)                         # 🚨 8/18 학습 조건과 동일 설정
        cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        depth = None
        for _ in range(20):                          # 첫 프레임들은 컴포넌트가 섞여 올 수 있다(7/28)
            res = cam.RetrieveResult(2000, pylon.TimeoutHandling_ThrowException)
            try:
                if res.GrabSucceeded():
                    arr = res.Array.copy()
                    if arr.ndim == 2 and arr.dtype == np.uint16:
                        depth = arr
                        break
            except Exception:
                pass
            finally:
                res.Release()
        if depth is None:
            raise SystemExit("🔴 depth 프레임을 못 받았다 — 방화벽 UDP 규칙·전원·같은 랜포트인가(8/28 절차서)")
    finally:
        try:
            cam.StopGrabbing(); cam.Close()
        except Exception:
            pass

    out_dir.mkdir(parents=True, exist_ok=True)
    npy = out_dir / f"{stem}.npy"
    np.save(npy, depth)                              # raw uint16 (학습셋과 동일 포맷)
    valid = float((depth > 0).mean() * 100)
    print(f"[촬영] 저장 {npy.name} shape={depth.shape} dtype={depth.dtype} 유효픽셀 {valid:.1f}%")
    if depth.shape != (480, 848):
        print(f"   ⚠️ shape 가 학습셋 (480,848) 과 다르다 — 그대로 진행하나 인식 결과를 믿지 말 것")
    return npy


# ---------------------------------------------------------------------------
# ② 추론 → 6요소 (검증된 러너를 그대로 부른다 — 플래그 6개는 러너가 못박고 있다)
# ---------------------------------------------------------------------------
def run_e2e(depth: Path, out_dir: Path, ckpt: Path, python: str) -> Path:
    cmd = [python, "-m", "bin_picking.src.run_binpick_e2e",
           "--depth", str(depth), "--out-dir", str(out_dir), "--checkpoint", str(ckpt)]
    print("[추론] " + " ".join(cmd[2:]))
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(REPO), text=True, encoding="utf-8", errors="replace",
                       capture_output=True)
    print(r.stdout[-1500:])
    if r.returncode != 0:
        print(r.stderr[-1500:])
        raise SystemExit(f"🔴 추론 단계 실패 rc={r.returncode}")
    six = out_dir / "six" / f"{depth.stem}.six.json"
    if not six.exists():
        raise SystemExit(f"🔴 six.json 이 없다: {six}  — 러너 출력 구조가 바뀌었나")
    d = json.loads(six.read_text(encoding="utf-8"))
    dets = d.get("detections") or d.get("objects") or []
    print(f"[추론] {time.time() - t0:.1f}s · 검출 {len(dets)}건 · {six.name}")
    return six


# ---------------------------------------------------------------------------
# ③ 소켓 서버 — 로봇(펜던트 MODE vision)이 붙어 좌표를 읽고 DONE 을 보낼 때까지 기다린다
# ---------------------------------------------------------------------------
def serve(six: Path, host: str, port: int, limit: int, cycles: int, python: str) -> int:
    cmd = [python, "-m", "bin_picking.src.communication.pick_socket_server",
           "--mode", "vision", "--six-json", str(six),
           "--host", host, "--port", str(port), "--limit", str(limit), "--cycles", str(cycles)]
    print("[소켓] " + " ".join(cmd[2:]))
    print(f"[소켓] 펜던트에서 MODE='vision' 실행 → 로봇이 {port} 포트로 접속하면 좌표 {limit}건을 보낸다")
    return subprocess.call(cmd, cwd=str(REPO))


def main() -> int:
    enable_utf8_console()
    ap = argparse.ArgumentParser(description="촬영 → 추론 → 6요소 → 소켓 대기 (1사이클)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--capture", action="store_true", help="Blaze 로 한 프레임 촬영")
    src.add_argument("--depth", type=Path, help="기존 depth .npy 사용(촬영 생략)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True,
                    help="🚨 실물 시작 전 1개로 고정 — 9/4 기준 OVN2_mg138_ep80/best.pt (md5 6ddfe295…)")
    ap.add_argument("--blaze-ip", default=DEFAULT_BLAZE_IP)
    ap.add_argument("--throughput", type=float, default=DEFAULT_THROUGHPUT)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=1, help="로봇에 보낼 포즈 수 (데모 = 1)")
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--no-server", action="store_true", help="six.json 까지만 만들고 끝(촬영·추론 점검용)")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    if not args.checkpoint.exists():
        raise SystemExit(f"🔴 체크포인트 없음: {args.checkpoint}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.capture:
        stem = time.strftime("live_%Y%m%d_%H%M%S")
        depth = capture_one(args.out_dir, args.blaze_ip, args.throughput, stem)
    else:
        depth = args.depth
        if not depth.exists():
            raise SystemExit(f"🔴 depth 없음: {depth}")
        print(f"[촬영] 생략 — {depth}")

    six = run_e2e(depth, args.out_dir, args.checkpoint, args.python)
    if args.no_server:
        print("[소켓] --no-server 로 종료. six =", six)
        return 0
    return serve(six, args.host, args.port, args.limit, args.cycles, args.python)


if __name__ == "__main__":
    sys.exit(main())
