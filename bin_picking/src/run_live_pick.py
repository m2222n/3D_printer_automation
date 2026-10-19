r"""
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
  · 🆕 10/19 **검출∩덩어리 융합 기본 ON**(`blob_fusion`) — 10/16 사이클 1·3 이 모델 좌표로 빈 바닥·옆 부품에 간 것을 막는다.
    로봇 좌표 = 검출이 덮은 깊이 덩어리의 중심·윗면(사이클 2 성공 방식). 버린 검출은 이유와 함께 출력 · `--no-fuse` 로 끈다.

사용 (IPC · C:\binpick_venv):
  # 촬영 없이 기존 npy 로 (연습·재택)
  python -m bin_picking.src.run_live_pick --depth shot_001_c1.npy --checkpoint <OVN2 best.pt> --out-dir C:\live\r1
  # 실촬영 → 소켓 대기 (현장) — 🆕 9/17: --calib 필수(카메라→base 변환) · 첫 시험은 --hover-mm 50(집기 없이 위에서 멈춤)
  python -m bin_picking.src.run_live_pick --capture --checkpoint <OVN2 best.pt> --out-dir C:\live\r1 --calib <cam_to_base.json> --hover-mm 50
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
from bin_picking.src.pipeline import roi_mask  # noqa: E402  (10/12 빈 안쪽만 — 벽이 크롭에 들어오면 진짜 부품이 사라진다)
from bin_picking.src.pipeline import blob_fusion  # noqa: E402  (10/19 검출∩덩어리 — 좌표는 덩어리에서)

DEFAULT_INTR = REPO / "bin_picking" / "config" / "blaze_intrinsics.json"

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
# ②' 웹 보고 — 🆕 10/16 셀B 실제 모니터링 배선 (8/13 송신 함수·수신 라우터를 잇는 한 줄)
#   · 인식 결과를 POST /api/v1/binpick/reports 로 보낸다 → 서버가 저장 + /binpick/ws 로 화면에 푸시
#   · 🚨 보고 실패는 로봇을 멈추지 않는다(웹은 보고 경로 · web_reporter 설계원칙 1) — 경고만 찍고 소켓으로 간다
#   · IPC 는 웹 서버(공장 PC)와 다른 PC 라 loopback 인증 면제가 안 된다 ⇒ JWT 필요
#     토큰 = 환경변수 BINPICK_REPORT_TOKEN, 없으면 BINPICK_REPORT_USER/BINPICK_REPORT_PASSWORD 로 로그인해서 받는다
#     🔒 비번을 인자·파일로 받지 않는다(명령 기록·커밋에 남는다)
# ---------------------------------------------------------------------------
REPORT_PATH = "/api/v1/binpick/reports"
LOGIN_PATH = "/api/v1/auth/login"


def _base_url(url: str) -> str:
    """'http://host:8085' 또는 '…/api/v1/binpick/reports' 둘 다 받는다 → 'http://host:8085'."""
    url = url.rstrip("/")
    return url[: -len(REPORT_PATH)] if url.endswith(REPORT_PATH) else url


def _report_token(base: str, timeout_s: float = 3.0) -> str | None:
    import os
    tok = os.environ.get("BINPICK_REPORT_TOKEN", "").strip()
    if tok:
        return tok
    user = os.environ.get("BINPICK_REPORT_USER", "").strip()
    pw = os.environ.get("BINPICK_REPORT_PASSWORD", "")
    if not (user and pw):
        return None                                   # 같은 PC(loopback)면 토큰 없이 된다
    import urllib.request
    from bin_picking.src.communication.web_reporter import HTTP_USER_AGENT
    req = urllib.request.Request(base + LOGIN_PATH, method="POST",
                                 data=json.dumps({"username": user, "password": pw}).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": HTTP_USER_AGENT})   # 🐛 10/16 터널 403 (Python 기본 UA 차단)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def report_scene(six_path: Path, url: str, latency_ms: float | None) -> bool:
    """six.json 한 장을 웹에 보고한다. 성패만 돌려주고 예외를 던지지 않는다(로그인 실패 포함)."""
    from bin_picking.src.communication.web_reporter import WebReporter, http_transport
    base = _base_url(url)
    try:
        token = _report_token(base)
    except Exception as e:                           # noqa: BLE001 — 로그인 실패도 로봇을 멈추지 않는다
        print(f"[보고] ⚠️ 로그인 실패 — 보고 생략: {type(e).__name__}: {e}")
        return False
    six = json.loads(Path(six_path).read_text(encoding="utf-8"))
    rep = WebReporter(http_transport(base + REPORT_PATH, token=token))
    try:
        res = rep.report_bin_picking(six, latency_ms=latency_ms)
    except Exception as e:                           # noqa: BLE001 — payload 를 못 만든 것(계약 위반)도 여기선 경고로
        print(f"[보고] ⚠️ payload 생성 실패 — 보고 생략: {type(e).__name__}: {e}")
        return False
    if res.ok:
        print(f"[보고] ✅ {res.detail} · scene={res.scene_id} · 검출 {len(six.get('detections') or [])}건 → 운영 화면 빈피킹 패널")
    else:
        print(f"[보고] ⚠️ 실패(로봇은 계속): {res.error}")
    return res.ok


# ---------------------------------------------------------------------------
# ③ 소켓 서버 — 로봇(펜던트 MODE vision)이 붙어 좌표를 읽고 DONE 을 보낼 때까지 기다린다
# ---------------------------------------------------------------------------
def serve(six: Path, host: str, port: int, limit: int, cycles: int, python: str,
          calib: Path, hover_mm: float, rz_mode: str, only_labels: str = "") -> int:
    # 🆕 9/17: --calib 없이는 서버가 시작을 거부한다(카메라 좌표를 그대로 보내던 경로 폐기). 여기서도 먼저 막는다.
    if not calib or not Path(calib).exists():
        raise SystemExit(f"🔴 캘리브 파일이 없다: {calib} — hand-eye(3점법) → cam_to_base build 가 선행이다. "
                         "촬영·추론만 점검하려면 --no-server")
    cmd = [python, "-m", "bin_picking.src.communication.pick_socket_server",
           "--mode", "vision", "--six-json", str(six), "--calib", str(calib),
           "--hover-mm", str(hover_mm), "--rz-mode", rz_mode,
           "--host", host, "--port", str(port), "--limit", str(limit), "--cycles", str(cycles)]
    if only_labels:
        cmd += ["--only-labels", only_labels]       # 🆕 10/12 시연 3종만 로봇에 보낸다(빈 안 잡음이 다른 이름으로 잡히는 것 차단)
    print("[소켓] " + " ".join(cmd[2:]))
    print(f"[소켓] 펜던트에서 MODE='vision' 실행 → 로봇이 {port} 포트로 접속하면 base 좌표 {limit}건을 보낸다"
          f" (hover {hover_mm}mm · rz {rz_mode})")
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
    ap.add_argument("--calib", type=Path, default=None,
                    help="🆕 cam_to_base 캘리브 파일 — 서버를 띄우려면 필수(카메라→base 변환 · P_capture 고정)")
    ap.add_argument("--hover-mm", type=float, default=0.0,
                    help="변환 결과 z 에 더한다(위로). 9/22 '집기 없이 이동 1회' = 50")
    ap.add_argument("--rz-mode", choices=("fixed", "angle"), default="fixed",
                    help="fixed=캘리브 rz_ref 그대로(위치만) / angle=부품 각도 반영(부호·오프셋 실측 후)")
    ap.add_argument("--roi", type=Path, default=None,
                    help="🆕 10/12 ROI 마스크 JSON(빈 안쪽만) — 추론 전에 적용해 <stem>_roi.npy 로 저장하고 그것을 추론한다. "
                         "만들기: python -m bin_picking.src.pipeline.roi_mask propose --depth <npy> --out <json>")
    ap.add_argument("--only-labels", default="",
                    help="🆕 로봇에 보낼 부품 이름만(쉼표) — 시연 = 02_sol_block_b,plate_e,13_x2_bcf8ccb4 · 비우면 전부")
    ap.add_argument("--report-url", default="",
                    help="🆕 10/16 인식 결과를 웹에 보고(셀B 모니터링) — 예: http://<웹서버>:8085 · 비우면 보고 안 함. "
                         "다른 PC 면 환경변수 BINPICK_REPORT_TOKEN 또는 BINPICK_REPORT_USER/BINPICK_REPORT_PASSWORD")
    ap.add_argument("--no-fuse", action="store_true",
                    help="🆕 10/19 검출∩덩어리 융합을 끈다(모델 좌표를 그대로 보냄 — 10/16 사이클 1·3 처럼 빈 곳으로 갈 수 있다)")
    ap.add_argument("--pick-unmatched", action="store_true",
                    help="🆕 10/19 모델이 못 본 덩어리도 'unlabeled' 로 뒤에 붙인다(이름 없이 찾아 집기 · --only-labels 와 같이 쓰면 걸러진다)")
    ap.add_argument("--max-blob-height", type=float, default=blob_fusion.MAX_HEIGHT_MM,
                    help="이보다 높은 덩어리 = 빈 벽·케이블로 보고 제외(mm · 10/16 부품 15~21 · 벽 34~68)")
    ap.add_argument("--intr", type=Path, default=DEFAULT_INTR)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()
    t_start = time.time()
    if not args.no_server and not args.calib:
        ap.error("--calib <cam_to_base.json> 이 필요하다 (서버 없이 촬영·추론만 보려면 --no-server)")

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

    if args.roi:
        # 🚨 마스크는 "추론 입력" 에만 건다. 원본 npy 는 그대로 두고 옆에 _roi 를 만든다(학습·대조용 원본 보존).
        depth, st = roi_mask.apply_to_file(depth, args.roi)
        print(f"[ROI] {args.roi.name} 적용 → {depth.name} · 유효% {st['before']['valid_pct']}→{st['after']['valid_pct']}"
              f" · 크롭 대역% {st['before']['crop_band_pct']}→{st['after']['crop_band_pct']}")
        if st["after"]["valid_pct"] > 25:
            print("   ⚠️ 마스크 뒤에도 유효 25% 초과 — 빈이 움직였나(propose 다시) / 바닥 반사?")
    else:
        print("[ROI] 없음 — 빈 벽이 크롭에 들어오면 부품을 놓친다(10/12 실측: 3개 중 1개). --roi 권장")

    six = run_e2e(depth, args.out_dir, args.checkpoint, args.python)
    if args.roi:
        roi_mask.rescore_scene_in_roi(six, depth, args.roi)   # 장면 게이트를 "빈 안쪽 면적" 기준으로 다시 쓴다(전체 화면 기준이면 마스크 뒤 항상 "비어 있다")
    if args.no_fuse:
        print("[융합] 끔(--no-fuse) — 모델 좌표를 그대로 보낸다. 🚨 10/16 사이클 1·3 은 이 상태에서 빈 곳·옆 부품으로 갔다")
    else:
        if not args.roi:
            print("[융합] ⚠️ --roi 없음 — 빈 벽 덩어리를 테두리 규칙으로 못 거른다(높이 규칙만)")
        six, fusion = blob_fusion.fuse_file(six, depth, args.intr, roi_path=args.roi,
                                            pick_unmatched=args.pick_unmatched, max_height_mm=args.max_blob_height)
        blob_fusion.print_summary(fusion)
        n_out = fusion["n_kept"] + (len(fusion["unmatched_blob_ids"]) if args.pick_unmatched else 0)
        if n_out == 0:
            print("[융합] 🔴 로봇에 보낼 후보 0 — 빈에 부품이 덩어리로 보이는지(위 표) · 모델이 못 봤으면 --pick-unmatched")
        if args.pick_unmatched and args.only_labels:
            print("[융합] ⚠️ --only-labels 가 있으면 이름 없는(unlabeled) 후보는 서버에서 걸러진다")
        print(f"[융합] → {six.name}")
    if args.report_url:
        # ⭐ 게이트 재판정 뒤에 보낸다 — 화면에 뜨는 신뢰 판정이 로봇이 받은 것과 같아야 한다
        report_scene(six, args.report_url, latency_ms=(time.time() - t_start) * 1000.0)
    else:
        print("[보고] 없음 — 운영 화면에 빈피킹이 안 뜬다. --report-url 권장")
    if args.no_server:
        print("[소켓] --no-server 로 종료. six =", six)
        return 0
    return serve(six, args.host, args.port, args.limit, args.cycles, args.python,
                 args.calib, args.hover_mm, args.rz_mode, args.only_labels)


if __name__ == "__main__":
    sys.exit(main())
