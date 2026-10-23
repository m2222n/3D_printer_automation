"""웹캠 상시 감시 — 카메라 여러 대를 주기적으로 찍어 판독기(read_screen)에 넣고, 상태가 바뀌면 MQTT 로 발행한다.

무엇 · 왜 (10/23)
  read_screen.py 는 "사진 1장 → 상태 JSON → 발행" 한 번이다. 시연(화면 8대 · 웹캠 + 클라우드 판정)에는
  **계속 보고 있다가 바뀌면 알리는 것**이 필요하다. 이 파일이 그 루프다. 서버(web-api)는 바꾸지 않는다 —
  시뮬레이터와 같은 토픽·필드로 발행하므로 운영 화면 카드가 그대로 받는다.

설계 원칙
  · 입력원(source)은 셋 중 하나: 웹캠 번호(0,1,…) · 사진 폴더(`dir:<경로>` — 웹캠 없는 PC 에서 같은 루프를 돌려 본다) · 사진 1장(`file:<경로>`).
  · **변화 게이트**: 직전에 판독한 프레임과 거의 같으면(평균 밝기 차 < 임계) 클라우드를 부르지 않는다.
    화면이 안 바뀌는 시간이 대부분이라 호출 수(비용 · 503 노출)가 크게 준다. 첫 프레임은 무조건 판독.
  · **발행 정책**: 상태가 바뀌었을 때 + 심장박동(heartbeat_s 마다 같은 상태 재발행 · 서버가 "살아 있다" 를 알게).
    unknown/printer 는 발행하지 않는다(read_screen.to_status_payload 가 None) — 마지막 상태는 유지.
  · **죽지 않는다**: 카메라 한 대가 안 열리거나 판독이 실패해도 그 대만 건너뛰고 다음 주기에 다시 시도(10/22 215장 채점이 1장 때문에 전체 종료된 교훈).
  · **증빙**: 카메라마다 `captures/<camera_id>/last.jpg` + `log.jsonl`(시각 · 지연 · 판정 · 발행/건너뜀 사유) 를 남긴다 — 완료보고서 산출물 ③ 증거.
  · 판독·발행·시계·대기는 주입 가능 → 네트워크·웹캠·키 없이 테스트가 돈다(test_watch_cameras.py).

실행 (공장 PC · web-api venv 또는 opencv-python + paho-mqtt 가 있는 파이썬)
  python vision/screen_reader/watch_cameras.py --cam wash_1=0 --cam cure_1=1 --interval 15 [--dry-run]
  python vision/screen_reader/watch_cameras.py --config vision/screen_reader/cameras.json
  python vision/screen_reader/watch_cameras.py --cam wash_1=dir:/data/jtm/synth_out/maixcam_capture_0714/MaixCam_0714/wash_running --once --dry-run
  옵션: --heartbeat 120 · --change-threshold 6 · --mqtt-host/--mqtt-port(환경변수 MQTT_BROKER_HOST/PORT) · --no-publish(판독만) · --max-cycles N

설정 파일(JSON) 예
  {"interval_s": 15, "heartbeat_s": 120, "change_threshold": 6.0,
   "cameras": [{"camera_id": "wash_1", "source": 0}, {"camera_id": "cure_1", "source": "dir:captures/cure_1_test"}]}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_screen as rs  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
GATE_SIZE = (64, 36)          # 변화 게이트용 축소 크기(가로, 세로) — 글자 하나가 아니라 화면 전체의 변화를 본다


# ---------------------------------------------------------------------------
# 입력원 — 전부 "BGR numpy 프레임 하나를 준다" 로 통일
# ---------------------------------------------------------------------------
class FrameSource:
    name: str = "?"

    def read(self):  # -> np.ndarray | None
        raise NotImplementedError

    def close(self) -> None:
        pass


class WebcamSource(FrameSource):
    """USB 웹캠. 열어 둔 채로 쓴다(매번 열면 노출 워밍업 10프레임을 매 주기 버려야 한다)."""

    def __init__(self, index: int, width: int = 1280, height: int = 720, warmup: int = 10):
        self.index, self.width, self.height, self.warmup = index, width, height, warmup
        self.name = f"webcam:{index}"
        self._cap = None

    def _open(self) -> bool:
        import cv2
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY   # Windows 는 DSHOW 가 열리는 시간이 짧고 번호가 안정적
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        for _ in range(self.warmup):
            cap.read()
        self._cap = cap
        return True

    def read(self):
        if self._cap is None and not self._open():
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self.close()                    # 다음 주기에 다시 연다(USB 빠짐·다른 프로그램이 잡음)
            return None
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class DirSource(FrameSource):
    """폴더의 사진을 이름순으로 돌려가며 준다 — 웹캠 없는 PC 에서 루프·게이트·발행 정책을 그대로 시험하는 가짜 카메라."""

    def __init__(self, folder: Path, loop: bool = True):
        self.folder, self.loop = Path(folder), loop
        self.name = f"dir:{self.folder}"
        self.files = sorted(p for p in self.folder.iterdir() if p.suffix.lower() in IMG_EXT)
        if not self.files:
            raise SystemExit(f"🔴 사진 없음: {self.folder}")
        self.i = 0
        self.last_path: Path | None = None

    def read(self):
        import cv2
        if self.i >= len(self.files):
            if not self.loop:
                return None
            self.i = 0
        p = self.files[self.i]
        self.i += 1
        self.last_path = p
        return cv2.imread(str(p))


class FileSource(DirSource):
    """사진 1장을 매번 준다(게이트가 매번 '같음' 으로 막는 것을 보는 용도)."""

    def __init__(self, path: Path):
        self.folder, self.loop = Path(path).parent, True
        self.name = f"file:{path}"
        self.files = [Path(path)]
        self.i = 0
        self.last_path = None

    def read(self):
        self.i = 0
        return super().read()


def make_source(spec: int | str) -> FrameSource:
    if isinstance(spec, int) or (isinstance(spec, str) and spec.isdigit()):
        return WebcamSource(int(spec))
    if isinstance(spec, str) and spec.startswith("dir:"):
        return DirSource(Path(spec[4:]))
    if isinstance(spec, str) and spec.startswith("file:"):
        return FileSource(Path(spec[5:]))
    raise SystemExit(f"🔴 source 는 웹캠 번호 · dir:<폴더> · file:<사진> 중 하나: {spec!r}")


# ---------------------------------------------------------------------------
# 변화 게이트
# ---------------------------------------------------------------------------
def gate_signature(frame) -> "Any":
    """프레임 → 작은 회색 배열. 비교는 이 배열끼리."""
    import cv2
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, GATE_SIZE, interpolation=cv2.INTER_AREA).astype("float32")


def frame_diff(sig_a, sig_b) -> float:
    """두 시그니처의 평균 절대 밝기 차(0~255). 같은 화면이면 노이즈 수준(1~3), 타이머 숫자만 바뀌면 그보다 조금 큼, 플랫폼 상승·램프 점등은 수십."""
    import numpy as np
    return float(np.mean(np.abs(sig_a - sig_b)))


# ---------------------------------------------------------------------------
# 감시 루프
# ---------------------------------------------------------------------------
@dataclass
class CamState:
    camera_id: str
    source: FrameSource
    last_sig: Any = None                  # 마지막으로 **판독한** 프레임의 시그니처(건너뛴 프레임은 갱신 안 함 — 천천히 변하는 화면도 결국 잡히게)
    last_status: str | None = None        # 마지막으로 발행한 status(wash_running …)
    last_payload: dict[str, Any] | None = None
    last_publish_t: float = 0.0
    last_result: dict[str, Any] | None = None
    errors: int = 0
    judged: int = 0
    published: int = 0
    skipped: int = 0


@dataclass
class Watcher:
    cams: list[CamState]
    out_root: Path
    interval_s: float = 15.0
    heartbeat_s: float = 120.0
    change_threshold: float = 6.0
    dry_run: bool = False
    publish: bool = True
    model: str = rs.MODEL_GEMINI
    provider: str = "gemini"
    fallback_model: str | None = None
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    key: str | None = None
    # 주입점(테스트)
    reader: Callable[[Path], dict[str, Any]] | None = None
    publisher: Callable[[str, dict[str, Any]], None] | None = None
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = print
    _writer_cv2: Any = field(default=None, repr=False)

    # ---- 한 대 · 한 주기 ----
    def step(self, cam: CamState) -> dict[str, Any]:
        """프레임 1장 처리. 돌려주는 dict 는 log.jsonl 한 줄과 같다(테스트가 이것을 본다)."""
        now = self.clock()
        rec: dict[str, Any] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "t": now, "camera_id": cam.camera_id, "source": cam.source.name}
        frame = None
        try:
            frame = cam.source.read()
        except Exception as e:           # 입력원이 죽어도 루프는 산다
            rec.update(event="source_error", error=f"{type(e).__name__}: {e}")
        if frame is None:
            if "event" not in rec:
                rec.update(event="no_frame")
            cam.errors += 1
            return self._finish(cam, rec)

        sig = gate_signature(frame)
        diff = frame_diff(sig, cam.last_sig) if cam.last_sig is not None else None
        rec["diff"] = None if diff is None else round(diff, 2)
        heartbeat_due = cam.last_status is not None and (now - cam.last_publish_t) >= self.heartbeat_s

        if diff is not None and diff < self.change_threshold:
            cam.skipped += 1
            rec.update(event="skipped_same_frame")
            if heartbeat_due and self.publish and cam.last_payload is not None:
                self._publish(cam, cam.last_payload, now, rec, why="heartbeat")
            return self._finish(cam, rec)

        # 판독 — 프레임을 파일로(증빙 + read_one 입력)
        path = self._write_frame(cam, frame)
        try:
            r = self._read(cam, path)
        except (rs.ReadError, SystemExit) as e:      # read_screen 은 실패를 SystemExit/ReadError 로 낸다 — 감시 루프는 여기서 죽으면 안 된다
            cam.errors += 1
            rec.update(event="read_error", error=str(e))
            return self._finish(cam, rec)
        cam.judged += 1
        cam.last_sig = sig
        cam.last_result = r
        res = r["result"]
        rec.update(event="judged", latency_ms=r.get("latency_ms"), model=r.get("model"),
                   device=res["device"], state=res["state"], confidence=res.get("confidence"),
                   remaining_s=res.get("remaining_s"), screen_text=res.get("screen_text"), dry_run=bool(res.get("dry_run")))

        tp = rs.to_status_payload(res, camera_id=cam.camera_id)
        if tp is None:
            rec["publish"] = "none_enum"                 # unknown/printer — 화면에 가짜 상태를 올리지 않는다 · 마지막 상태 유지
            return self._finish(cam, rec)
        topic, payload = tp
        status = payload["status"]
        if not self.publish:
            rec["publish"] = "disabled"
            cam.last_status = status
            return self._finish(cam, rec)
        if status != cam.last_status:
            self._publish(cam, payload, now, rec, why="changed", topic=topic)
        elif heartbeat_due:
            self._publish(cam, payload, now, rec, why="heartbeat", topic=topic)
        else:
            rec["publish"] = "same_status"
        cam.last_payload = payload
        return self._finish(cam, rec)

    # ---- 보조 ----
    def _read(self, cam: CamState, path: Path) -> dict[str, Any]:
        if self.reader is not None:
            return self.reader(path)
        if self.dry_run:
            # 가짜 판정은 파일명(wash_running_…)으로 채운다 — 폴더 입력원이면 원본 이름, 웹캠이면 last.jpg 라 unknown(의도된 것 · 성과 아님)
            name_path = getattr(cam.source, "last_path", None) or path
            res = rs.fake_result(Path(name_path))
            return {"image": str(path), "image_bytes": path.stat().st_size, "provider": self.provider, "model": "dry-run",
                    "latency_ms": 0.0, "result": res, "meta": {"dry_run": True, "attempts": 1}, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        return rs.read_one(path, dry_run=self.dry_run, model=self.model, provider=self.provider, key=self.key, fallback_model=self.fallback_model)

    def _publish(self, cam: CamState, payload: dict[str, Any], now: float, rec: dict[str, Any], *, why: str, topic: str | None = None) -> None:
        payload = dict(payload)
        payload["timestamp"] = now
        topic = topic or f"factory/{payload['device_type']}/{payload['device_id']}/status"
        try:
            if self.publisher is not None:
                self.publisher(topic, payload)
            else:
                rs.publish_status(topic, payload, host=self.mqtt_host, port=self.mqtt_port)
        except SystemExit as e:                       # 브로커 끊김 — 다음 주기에 다시
            cam.errors += 1
            rec.update(publish="failed", publish_error=str(e))
            return
        cam.published += 1
        cam.last_status = payload["status"]
        cam.last_payload = payload
        cam.last_publish_t = now
        rec.update(publish=why, topic=topic, status=payload["status"])

    def _write_frame(self, cam: CamState, frame) -> Path:
        import cv2
        d = self.out_root / cam.camera_id
        d.mkdir(parents=True, exist_ok=True)
        p = d / "last.jpg"
        cv2.imwrite(str(p), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return p

    def _finish(self, cam: CamState, rec: dict[str, Any]) -> dict[str, Any]:
        d = self.out_root / cam.camera_id
        d.mkdir(parents=True, exist_ok=True)
        with (d / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ev = rec["event"]
        tail = ""
        if ev == "judged":
            tail = f" {rec['device']}/{rec['state']} conf={rec.get('confidence')} {rec.get('latency_ms')}ms → {rec.get('publish')}"
        elif ev == "skipped_same_frame":
            tail = f" diff={rec['diff']}" + (f" → {rec['publish']}" if "publish" in rec else "")
        elif "error" in rec:
            tail = f" {rec['error']}"
        self.log(f"[{cam.camera_id}] {ev}{tail}")
        return rec

    # ---- 전체 루프 ----
    def run(self, *, max_cycles: int | None = None) -> None:
        self.log(f"감시 시작 — 카메라 {len(self.cams)} · 주기 {self.interval_s}s · 심장박동 {self.heartbeat_s}s · 게이트 {self.change_threshold} · "
                 f"{'dry-run' if self.dry_run else self.model} · 발행 {'on' if self.publish else 'off'} → {self.out_root}")
        n = 0
        try:
            while True:
                t0 = self.clock()
                for cam in self.cams:
                    self.step(cam)
                n += 1
                if max_cycles is not None and n >= max_cycles:
                    break
                spent = self.clock() - t0
                self.sleep(max(0.0, self.interval_s - spent))
        except KeyboardInterrupt:
            self.log("중단(Ctrl+C)")
        finally:
            for cam in self.cams:
                cam.source.close()
            self.log("요약 " + " · ".join(f"{c.camera_id}: 판독 {c.judged} 발행 {c.published} 건너뜀 {c.skipped} 오류 {c.errors}" for c in self.cams))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_cam(spec: str) -> tuple[str, int | str]:
    if "=" not in spec:
        raise SystemExit(f"🔴 --cam 은 <camera_id>=<source> 꼴(예 wash_1=0 · cure_1=dir:폴더): {spec!r}")
    cid, src = spec.split("=", 1)
    dev, _, num = cid.rpartition("_")
    if dev not in ("wash", "cure") or not num.isdigit():
        raise SystemExit(f"🔴 camera_id 는 wash_<번호> 또는 cure_<번호> 꼴(서버 토픽 factory/<device>/<번호>/status 와 맞아야 한다): {cid!r}")
    return cid, (int(src) if src.isdigit() else src)


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg.get("cameras"), list) or not cfg["cameras"]:
        raise SystemExit(f"🔴 설정에 cameras 목록이 없다: {path}")
    return cfg


def main() -> int:
    try:
        from bin_picking.src.utils.console_utf8 import enable_utf8_console
        enable_utf8_console()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="웹캠 상시 감시 — 주기 촬영 → 판독 → 상태 변화 시 MQTT 발행")
    ap.add_argument("--cam", action="append", default=[], help="<camera_id>=<source> (반복 · 예 wash_1=0 · cure_1=dir:폴더)")
    ap.add_argument("--config", type=Path, help="JSON 설정(cameras · interval_s · heartbeat_s · change_threshold)")
    ap.add_argument("--interval", type=float, default=None, help="촬영 주기 초(기본 15)")
    ap.add_argument("--heartbeat", type=float, default=None, help="같은 상태 재발행 간격 초(기본 120)")
    ap.add_argument("--change-threshold", type=float, default=None, help="변화 게이트 임계(평균 밝기 차 · 기본 6.0 · 0 이면 매번 판독)")
    ap.add_argument("--out", type=Path, default=HERE / "captures", help="증빙 폴더(카메라별 last.jpg · log.jsonl)")
    ap.add_argument("--dry-run", action="store_true", help="클라우드 호출 없이 전부 돈다(파일명 기반 가짜 판정 · 성과 아님)")
    ap.add_argument("--no-publish", action="store_true", help="판독만 하고 발행 안 함")
    ap.add_argument("--once", action="store_true", help="한 주기만")
    ap.add_argument("--max-cycles", type=int, default=None)
    ap.add_argument("--provider", choices=rs.PROVIDERS, default="gemini")
    ap.add_argument("--model", default=None)
    ap.add_argument("--fallback-model", default=None)
    ap.add_argument("--key-file", type=Path, default=rs.KEY_FILE)
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_BROKER_HOST", "127.0.0.1"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_BROKER_PORT", "1883")))
    a = ap.parse_args()

    cfg: dict[str, Any] = load_config(a.config) if a.config else {}
    cam_specs: list[tuple[str, int | str]] = [(c["camera_id"], c["source"]) for c in cfg.get("cameras", [])]
    cam_specs += [parse_cam(s) for s in a.cam]
    if not cam_specs:
        raise SystemExit("🔴 카메라가 없다 — --cam wash_1=0 또는 --config")
    cams = [CamState(camera_id=cid, source=make_source(src)) for cid, src in cam_specs]
    model = a.model or (rs.MODEL_GEMINI if a.provider == "gemini" else rs.MODEL_ANTHROPIC)
    key = None if (a.dry_run or a.provider != "gemini") else rs.load_gemini_key(a.key_file)
    w = Watcher(cams=cams, out_root=a.out,
                interval_s=a.interval if a.interval is not None else float(cfg.get("interval_s", 15.0)),
                heartbeat_s=a.heartbeat if a.heartbeat is not None else float(cfg.get("heartbeat_s", 120.0)),
                change_threshold=a.change_threshold if a.change_threshold is not None else float(cfg.get("change_threshold", 6.0)),
                dry_run=a.dry_run, publish=not a.no_publish, model=model, provider=a.provider, fallback_model=a.fallback_model,
                mqtt_host=a.mqtt_host, mqtt_port=a.mqtt_port, key=key)
    w.run(max_cycles=1 if a.once else a.max_cycles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
