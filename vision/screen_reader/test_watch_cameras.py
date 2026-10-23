"""watch_cameras 검증 — 웹캠·네트워크·키 없이 (실행: web-api/venv/bin/python vision/screen_reader/test_watch_cameras.py)

① 폴더 입력원이 이름순(알파벳 · 숫자 접두어로 순서를 정한다)으로 돌고, 끝나면 처음으로(loop)
② 변화 게이트: 같은 프레임이면 판독기를 부르지 않는다 · 다른 프레임이면 부른다 · 임계 0 이면 매번
③ 발행 정책: 첫 판정 발행 · 같은 상태는 심장박동 전엔 안 함 · 심장박동 지나면 재발행 · 상태 바뀌면 즉시
④ 게이트로 건너뛴 주기에도 심장박동이 되면 마지막 페이로드를 재발행한다
⑤ unknown/printer 는 발행하지 않고 마지막 상태를 유지한다
⑥ 판독 실패(ReadError/SystemExit)·프레임 없음·발행 실패에도 루프가 죽지 않고 기록만 남는다
⑦ 증빙: last.jpg 와 log.jsonl 이 카메라별로 쌓인다 · 기록 키
⑧ 🧪 그물: 게이트 임계를 크게 하면 다른 프레임도 건너뛴다(게이트가 실제로 호출 수를 가른다)
⑨ CLI 파서: --cam 꼴 검사 · 설정 파일 병합
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_screen as rs  # noqa: E402
import watch_cameras as wc  # noqa: E402

OK = True


def check(name: str, cond: bool) -> None:
    global OK
    print(("  🟢 " if cond else "  🔴 ") + name)
    OK = OK and bool(cond)


def write_img(path: Path, level: int, seed: int = 0) -> None:
    """level 밝기의 1280x720 BGR 사진(노이즈 조금). 같은 level·seed 면 같은 그림."""
    import cv2
    rng = np.random.default_rng(seed)
    img = np.full((720, 1280, 3), level, dtype=np.uint8)
    img = np.clip(img.astype(np.int16) + rng.integers(-2, 3, img.shape), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def make_watcher(tmp: Path, cams: list[tuple[str, str]], **kw) -> tuple[wc.Watcher, list, list, FakeClock]:
    """판독 = dry-run 가짜(파일명 기반) · 발행 = 리스트에 쌓기 · 시계 = 가짜."""
    calls: list[Path] = []
    pubs: list[tuple[str, dict]] = []
    clock = FakeClock()

    def reader(p: Path):
        calls.append(p)
        src = next(c for c in w.cams if (w.out_root / c.camera_id / "last.jpg") == p).source
        name_path = getattr(src, "last_path", None) or p          # 가짜 판정은 **원본 파일명**(wash_running_…)으로
        r = rs.fake_result(Path(name_path))
        return {"image": str(p), "latency_ms": 1.0, "model": "fake", "result": r, "meta": {"dry_run": True}}

    w = wc.Watcher(cams=[wc.CamState(camera_id=cid, source=wc.make_source(src)) for cid, src in cams],
                   out_root=tmp / "captures", reader=reader, publisher=lambda t, p: pubs.append((t, p)),
                   clock=clock, sleep=lambda s: None, log=lambda s: None, dry_run=True, **kw)
    return w, calls, pubs, clock


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ① 폴더 입력원
        print("① DirSource 순서·loop")
        d1 = tmp / "seq"
        write_img(d1 / "1_wash_idle.jpg", 60, seed=1)
        write_img(d1 / "2_wash_running.jpg", 120, seed=2)
        write_img(d1 / "3_wash_complete.jpg", 200, seed=3)
        s = wc.DirSource(d1)
        names = [s.last_path.name for _ in range(4) if s.read() is not None]
        check("이름순 3장 뒤 다시 처음", names == ["1_wash_idle.jpg", "2_wash_running.jpg", "3_wash_complete.jpg", "1_wash_idle.jpg"])

        # ② 변화 게이트
        print("② 변화 게이트")
        d2 = tmp / "same"
        write_img(d2 / "1_wash_running_a.jpg", 100, seed=7)
        write_img(d2 / "2_wash_running_b.jpg", 100, seed=7)      # 같은 그림
        write_img(d2 / "3_wash_complete_c.jpg", 220, seed=8)     # 다른 그림
        w, calls, pubs, clock = make_watcher(tmp / "t2", [("wash_1", f"dir:{d2}")], change_threshold=6.0, heartbeat_s=10_000)
        cam = w.cams[0]
        r1 = w.step(cam); n1 = len(calls)
        r2 = w.step(cam); n2 = len(calls)
        r3 = w.step(cam); n3 = len(calls)
        check("첫 프레임은 무조건 판독", r1["event"] == "judged" and n1 == 1)
        check("같은 프레임은 건너뜀(판독기 호출 없음)", r2["event"] == "skipped_same_frame" and n2 == 1 and r2["diff"] < 6.0)
        check("다른 프레임은 판독", r3["event"] == "judged" and n3 == 2 and r3["diff"] > 6.0)
        w0, calls0, _, _ = make_watcher(tmp / "t2b", [("wash_1", f"dir:{d2}")], change_threshold=0.0, heartbeat_s=10_000)
        for _ in range(3):
            w0.step(w0.cams[0])
        check("임계 0 이면 매번 판독", len(calls0) == 3)

        # ③ 발행 정책
        print("③ 발행 정책")
        check("첫 판정 발행(changed)", r1["publish"] == "changed" and pubs[0][0] == "factory/wash/1/status" and pubs[0][1]["status"] == "wash_running")
        check("상태 바뀌면 즉시 발행", r3["publish"] == "changed" and pubs[-1][1]["status"] == "wash_complete" and len(pubs) == 2)
        d3 = tmp / "steady"
        write_img(d3 / "1_cure_running_a.jpg", 90, seed=11)
        write_img(d3 / "2_cure_running_b.jpg", 140, seed=12)     # 다른 그림 · 같은 상태
        w3, calls3, pubs3, clock3 = make_watcher(tmp / "t3", [("cure_2", f"dir:{d3}")], change_threshold=6.0, heartbeat_s=100)
        c3 = w3.cams[0]
        a = w3.step(c3); clock3.advance(30); b = w3.step(c3)
        check("같은 상태 · 심장박동 전 = 판독은 하되 발행 안 함", a["publish"] == "changed" and b["event"] == "judged" and b["publish"] == "same_status" and len(pubs3) == 1)
        clock3.advance(80); c = w3.step(c3)
        check("심장박동 지나면 재발행", c["publish"] == "heartbeat" and len(pubs3) == 2 and pubs3[1][1]["status"] == "cure_running")

        # ④ 건너뛴 주기의 심장박동
        print("④ 건너뛴 주기에도 심장박동")
        d4 = tmp / "still"
        write_img(d4 / "wash_running_only.jpg", 100, seed=21)
        w4, calls4, pubs4, clock4 = make_watcher(tmp / "t4", [("wash_1", f"file:{d4 / 'wash_running_only.jpg'}")], change_threshold=6.0, heartbeat_s=60)
        c4 = w4.cams[0]
        w4.step(c4); clock4.advance(30); s2 = w4.step(c4); clock4.advance(40); s3 = w4.step(c4)
        check("같은 프레임 반복 = 판독 1회뿐", len(calls4) == 1 and s2["event"] == "skipped_same_frame" and s3["event"] == "skipped_same_frame")
        check("건너뛰었어도 심장박동이면 마지막 페이로드 재발행", "publish" not in s2 and s3.get("publish") == "heartbeat" and len(pubs4) == 2
              and pubs4[1][1]["timestamp"] == clock4.t)

        # ⑤ unknown/printer
        print("⑤ enum 밖")
        d5 = tmp / "unk"
        write_img(d5 / "1_wash_running.jpg", 100, seed=31)
        write_img(d5 / "2_unknown_unknown.jpg", 180, seed=32)
        write_img(d5 / "3_printer_running.jpg", 40, seed=33)
        w5, calls5, pubs5, _ = make_watcher(tmp / "t5", [("wash_1", f"dir:{d5}")], heartbeat_s=10_000)
        c5 = w5.cams[0]
        w5.step(c5); u = w5.step(c5); p = w5.step(c5)
        check("unknown 은 발행 안 함 · 마지막 상태 유지", u["publish"] == "none_enum" and p["publish"] == "none_enum" and len(pubs5) == 1 and c5.last_status == "wash_running")

        # ⑥ 죽지 않는다
        print("⑥ 실패 격리")
        d6 = tmp / "err"
        write_img(d6 / "1_cure_idle.jpg", 100, seed=41)
        w6, _, pubs6, _ = make_watcher(tmp / "t6", [("cure_1", f"dir:{d6}")], heartbeat_s=10_000)
        c6 = w6.cams[0]

        def bad_reader(p):
            raise rs.ReadError("503 high demand(가짜)")
        w6.reader = bad_reader
        e1 = w6.step(c6)
        check("ReadError → read_error 기록 · 예외 안 남", e1["event"] == "read_error" and "503" in e1["error"] and c6.errors == 1)

        def exit_reader(p):
            raise SystemExit("🔴 이미지가 너무 작다(가짜)")
        w6.reader = exit_reader
        e2 = w6.step(c6)
        check("SystemExit 도 격리", e2["event"] == "read_error" and c6.errors == 2)

        class DeadSource(wc.FrameSource):
            name = "dead"

            def read(self):
                return None
        c6.source = DeadSource()
        e3 = w6.step(c6)
        check("프레임 없음 → no_frame", e3["event"] == "no_frame" and c6.errors == 3)

        class BoomSource(wc.FrameSource):
            name = "boom"

            def read(self):
                raise RuntimeError("USB 빠짐(가짜)")
        c6.source = BoomSource()
        e4 = w6.step(c6)
        check("입력원 예외 → source_error", e4["event"] == "source_error" and "USB" in e4["error"])

        w7, _, _, _ = make_watcher(tmp / "t7", [("cure_1", f"dir:{d6}")], heartbeat_s=10_000)

        def bad_pub(t, p):
            raise SystemExit("🔴 MQTT 브로커 연결 실패(가짜)")
        w7.publisher = bad_pub
        f1 = w7.step(w7.cams[0])
        check("발행 실패 → failed 기록 · last_status 안 바뀜(다음 주기에 다시 시도)", f1["publish"] == "failed" and w7.cams[0].last_status is None)
        w7.publisher = lambda t, p: None
        f2 = w7.step(w7.cams[0])
        check("다음 주기(같은 프레임이라도 last_status 없으므로) … 게이트가 막는다 → 판독 안 함", f2["event"] == "skipped_same_frame")
        w7.cams[0].last_sig = None
        f3 = w7.step(w7.cams[0])
        check("프레임이 바뀌면 재판독 → 발행 성공", f3["publish"] == "changed" and w7.cams[0].last_status == "cure_idle")

        # ⑦ 증빙
        print("⑦ 증빙 파일")
        cap = w.out_root / "wash_1"
        lines = [json.loads(x) for x in (cap / "log.jsonl").read_text(encoding="utf-8").splitlines()]
        check("last.jpg 존재", (cap / "last.jpg").exists() and (cap / "last.jpg").stat().st_size > 1000)
        check("log.jsonl 3줄 · 필수 키", len(lines) == 3 and all(k in lines[0] for k in ("ts", "camera_id", "event", "device", "state", "latency_ms", "publish", "topic")))

        # ⑧ 그물
        print("⑧ 그물")
        w8, calls8, _, _ = make_watcher(tmp / "t8", [("wash_1", f"dir:{d2}")], change_threshold=999.0, heartbeat_s=10_000)
        for _ in range(3):
            w8.step(w8.cams[0])
        check("임계를 999 로 하면 다른 프레임도 건너뛴다(게이트가 호출 수를 실제로 가른다)", len(calls8) == 1)

        # ⑨ CLI
        print("⑨ CLI")
        check("--cam 파싱", wc.parse_cam("wash_1=0") == ("wash_1", 0) and wc.parse_cam("cure_2=dir:/x") == ("cure_2", "dir:/x"))
        bad = False
        try:
            wc.parse_cam("washer=0")
        except SystemExit:
            bad = True
        check("camera_id 꼴 검사(<device>_<번호>)", bad)
        cfgp = tmp / "cams.json"
        cfgp.write_text(json.dumps({"interval_s": 5, "cameras": [{"camera_id": "wash_1", "source": 0}]}), encoding="utf-8")
        check("설정 파일 로드", wc.load_config(cfgp)["interval_s"] == 5)

        # run() 한 바퀴(max_cycles) — 요약까지 예외 없이
        print("⑩ run(max_cycles)")
        logs: list[str] = []
        w9, calls9, pubs9, _ = make_watcher(tmp / "t9", [("wash_1", f"dir:{d1}"), ("cure_1", f"dir:{d3}")], heartbeat_s=10_000)
        w9.log = logs.append
        w9.run(max_cycles=2)
        check("2주기 × 2대 = 판독 4 · 요약 줄", len(calls9) == 4 and any(x.startswith("요약") for x in logs))

    print("\n결과:", "🟢 전부 통과" if OK else "🔴 실패 있음")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
