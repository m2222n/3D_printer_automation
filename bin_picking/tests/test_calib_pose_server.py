"""
calib_pose_server 자체 검증 — 로봇 없이 소켓 왕복으로 돈다 (numpy·pypylon 불필요)

사용: python bin_picking/tests/test_calib_pose_server.py
(다른 bin_picking/tests/*.py 와 같이 pytest 파일이 아니라 자체 실행 스크립트다 — sys.exit 로 끝난다)

검증하는 것
  🟢 정상 한 줄(dict / 배열) → OK n · samples.json 에 누적 · 카메라 트리거가 idx·폴더를 받는다
  🟢 거부 7종 → ERR + 저장 0 : 6요소 아님 · NaN · m 단위 의심 · 도달 밖 · 각도 rad 의심 · JSON 아님 · unit 다름
  🟢 카메라 실패 → ERR capture_failed + 저장 0 (OK 를 받은 사람이 다음 자세로 넘어가는 사고 방지)
  🟢 이어받기 — 같은 폴더로 서버를 다시 열면 다음 번호부터
  🧪 그물 확인 — 검증을 무력화하면 m 단위 줄이 통과한다(= 거부의 주체가 검증 함수임을 확인)
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bin_picking.src.communication import calib_pose_server as cps  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  🟢 {name}")
    else:
        FAIL += 1
        print(f"  🔴 {name}" + (f"  — {detail}" if detail else ""))


def roundtrip(port: int, line: str) -> str:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
        c.sendall((line + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = c.recv(1024)
            if not chunk:
                break
            buf += chunk
    return buf.decode().strip()


def serve_n(server: cps.CalibPoseServer, n: int) -> threading.Thread:
    """접속 n건을 처리하는 스레드(거부도 1건으로 센다)."""
    def _run():
        for _ in range(n):
            server.serve_one(accept_timeout=5)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="calib_test_"))
    captured: list[tuple[int, Path]] = []

    def fake_capture(idx: int, out_dir: Path) -> dict:
        captured.append((idx, out_dir))
        p = out_dir / f"{idx:03d}_depth.npy"
        p.write_bytes(b"fake")
        return {"depth_path": str(p), "rgb_path": None}

    print("① 정상 샘플 2건 (dict · 배열)")
    store = cps.CalibSampleStore(tmp)
    with cps.CalibPoseServer(store, fake_capture, host="127.0.0.1", port=0, verbose=False) as srv:
        t = serve_n(srv, 2)
        r1 = roundtrip(srv.port, json.dumps({"kind": "calib", "tcp": [300.5, -20, 450.25, 180, 0, 92.5], "unit": "mm_deg"}))
        r2 = roundtrip(srv.port, json.dumps([310, -20, 450, 180, 0, 90]))
        t.join(5)
    check("dict 한 줄 → OK 1", r1 == "OK 1", r1)
    check("배열 한 줄 → OK 2", r2 == "OK 2", r2)
    data = json.loads((tmp / "samples.json").read_text(encoding="utf-8"))
    check("samples.json 2건 · idx 1,2", [s["idx"] for s in data] == [1, 2], str([s["idx"] for s in data]))
    check("포즈가 원값 그대로 저장(소수점 포함)", data[0]["tcp_mm_deg"] == [300.5, -20.0, 450.25, 180.0, 0.0, 92.5], str(data[0]["tcp_mm_deg"]))
    check("카메라 트리거가 idx·폴더를 받았다", captured == [(1, tmp), (2, tmp)], str(captured))
    check("depth 경로가 샘플에 기록됨", data[0]["depth_path"].endswith("001_depth.npy"), data[0]["depth_path"])

    print("\n② 거부 7종 — 전부 ERR · 저장 0")
    bad = [
        ("6요소 아님", json.dumps([1, 2, 3, 4, 5])),
        ("NaN", '{"kind":"calib","tcp":[300,0,NaN,180,0,0],"unit":"mm_deg"}'),
        ("m 단위 의심(전부 <5)", json.dumps([0.4, 0.05, 0.25, 180, 0, 90])),
        ("도달 밖 z=3136 (7/29 사고 형태)", json.dumps([400, 50, 3136, 180, 0, 0])),
        ("각도 rad 의심? 아니라 |각|>360", json.dumps([400, 50, 250, 720, 0, 0])),
        ("JSON 아님", "hello robot"),
        ("unit 다름", json.dumps({"kind": "calib", "tcp": [0.3, 0.0, 0.45, 3.1, 0, 1.6], "unit": "m_rad"})),
    ]
    n_before = len(store.samples)
    with cps.CalibPoseServer(store, fake_capture, host="127.0.0.1", port=0, verbose=False) as srv:
        t = serve_n(srv, len(bad))
        replies = [(name, roundtrip(srv.port, line)) for name, line in bad]
        t.join(5)
    for name, rep in replies:
        check(f"{name} → ERR", rep.startswith("ERR"), rep)
    check("거부는 저장하지 않는다", len(store.samples) == n_before, f"{n_before} → {len(store.samples)}")
    check("거부는 카메라도 안 찍는다", len(captured) == 2, f"트리거 {len(captured)}회")

    print("\n③ 카메라 실패 → ERR capture_failed · 저장 0")
    def broken_capture(idx: int, out_dir: Path) -> dict:
        raise RuntimeError("Blaze 타임아웃(방화벽)")
    with cps.CalibPoseServer(store, broken_capture, host="127.0.0.1", port=0, verbose=False) as srv:
        t = serve_n(srv, 1)
        rep = roundtrip(srv.port, json.dumps([400, 50, 250, 180, 0, 0]))
        t.join(5)
    check("ERR capture_failed 로 알린다", rep.startswith("ERR capture_failed"), rep)
    check("포즈만 남기지 않는다(영상 없는 포즈는 못 쓴다)", len(store.samples) == 2, f"{len(store.samples)}건")

    print("\n④ 이어받기 — 같은 폴더로 다시 열면 3번부터")
    store2 = cps.CalibSampleStore(tmp)
    with cps.CalibPoseServer(store2, None, host="127.0.0.1", port=0, verbose=False) as srv:
        t = serve_n(srv, 1)
        rep = roundtrip(srv.port, json.dumps([420, 60, 260, 180, 0, 45]))
        t.join(5)
    check("기존 2건 로드", len(store2.samples) == 3, f"{len(store2.samples)}건")
    check("OK 3 · idx 3", rep == "OK 3" and store2.samples[-1]["idx"] == 3, f"{rep} idx={store2.samples[-1]['idx']}")
    check("--capture none 이면 depth_path 없이 저장(포즈만 · 왕복 시험용)", store2.samples[-1]["depth_path"] is None)

    print("\n⑤ 🧪 그물 확인 — validate_tcp 를 무력화하면 m 단위 줄이 통과해야 한다(거부의 주체 확인)")
    orig = cps.validate_tcp
    cps.validate_tcp = lambda tcp: [float(v) for v in tcp]   # type: ignore
    try:
        store3 = cps.CalibSampleStore(Path(tempfile.mkdtemp(prefix="calib_tear_")))
        with cps.CalibPoseServer(store3, None, host="127.0.0.1", port=0, verbose=False) as srv:
            t = serve_n(srv, 1)
            rep = roundtrip(srv.port, json.dumps([0.4, 0.05, 0.25, 180, 0, 90]))
            t.join(5)
        check("검증 제거 시 m 단위 줄이 OK 로 통과(=평소엔 검증이 막고 있었다)", rep == "OK 1", rep)
    finally:
        cps.validate_tcp = orig
    with cps.CalibPoseServer(cps.CalibSampleStore(Path(tempfile.mkdtemp(prefix="calib_restore_"))), None,
                             host="127.0.0.1", port=0, verbose=False) as srv:
        t = serve_n(srv, 1)
        rep = roundtrip(srv.port, json.dumps([0.4, 0.05, 0.25, 180, 0, 90]))
        t.join(5)
    check("복원 후 다시 ERR", rep.startswith("ERR"), rep)

    print(f"\n통과 {PASS} / 실패 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
