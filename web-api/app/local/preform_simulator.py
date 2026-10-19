"""
PreFormServer 시뮬레이터 — Formlabs 프로그램 없이 출력 흐름 전체를 로컬에서 돌린다 (2026-10-19)

🎯 왜 있는가
  PreFormServer(Local API)는 Windows/Mac 전용 프로그램이고 인증이 없어 공장 PC 안에서만 돈다.
  그래서 공장 밖(개발자 PC · 리눅스 6000 · 시험 인스턴스)에서는 Scene 준비 → 서포트 → 시간·레진 예측 → 전송
  흐름을 개발·시연할 길이 없었다(6000 → 공장 VPN 은 끊김 · 10/19 확인).
  ⇒ `.env` 에 `PREFORM_SIMULATE=true` 하나로, PreFormServer 와 file_receiver 로 나가는 HTTP 요청을
     **전송 계층(httpx.MockTransport)에서 가로채** 같은 모양의 응답을 돌려준다.
     preform_client 의 호출 코드는 한 줄도 안 바뀐다(세척기 시뮬레이터 · PrinterAdapter 와 같은 "스위치" 방식).

🚨 정직하게
  - 슬라이싱·서포트·시간 예측은 **가짜 값**이다(파일 크기로 대충 비례). 실제 수치는 운영 web-api(공장 PC)에서 확인한다.
  - 프린터 전송은 job_id 만 돌려주고 아무 데도 안 보낸다. 운영 `.env` 에는 절대 켜지 않는다(기본 False).
  - 상태(Scene 목록·스크린샷)는 프로세스 메모리에만 있다 — 재시작하면 사라진다.

응답 모양의 근거 = `preform_client.py` 가 읽는 키(id · models · estimated_* · total_print_time_s · devices · file_path · job_id)
"""
from __future__ import annotations

import json
import re
import struct
import time
import uuid
import zlib
from typing import Any, Dict
from urllib.parse import unquote

import httpx

SIMULATED_MATERIALS = [
    {"code": "FLGPGR05", "name": "Grey V5", "machine_type": "FORM-4-0"},
    {"code": "FLGPCL05", "name": "Clear V5", "machine_type": "FORM-4-0"},
    {"code": "FLGPWH05", "name": "White V5", "machine_type": "FORM-4-0"},
    {"code": "FLGPBK05", "name": "Black V5", "machine_type": "FORM-4-0"},
    {"code": "FLFX8001", "name": "Flexible 80A V1.1", "machine_type": "FORM-4-0"},
]

# 가짜 예측 계수 — 실제 Form 4 Grey V5 50µm 기준 "대략 이 정도" 수준(검증값 아님 · 화면 흐름용)
_BASE_PRINT_S = 1800.0          # 빈 Scene 도 이 정도(예열 · 첫 층)
_S_PER_MB = 2400.0              # STL 1MB 당 추가 초
_ML_PER_MB = 12.0               # STL 1MB 당 레진 ml


def _basename(p: str) -> str:
    """Windows 경로(C:\\STL_Files\\x.png)를 리눅스에서 받아도 파일명만 — Path().name 은 백슬래시를 못 가른다."""
    return re.split(r"[\\/]", p)[-1] if p else p


def _tiny_png(w: int = 64, h: int = 48) -> bytes:
    """회색 PNG 한 장(의존성 없이) — 스크린샷 다운로드가 '진짜 이미지'를 돌려주게."""
    raw = b"".join(b"\x00" + bytes([200, 200, 200] * w) for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


class PreFormSimulator:
    """PreFormServer + file_receiver 두 서버의 가짜. 인스턴스 하나가 Scene 상태를 들고 있다."""

    def __init__(self, printer_serial_map: Dict[int, str] | None = None):
        self.scenes: Dict[str, Dict[str, Any]] = {}
        self.screenshots: Dict[str, bytes] = {}
        self.uploads: Dict[str, int] = {}          # 가짜 공장 경로 → 바이트 수
        self.jobs: list[dict] = []
        self.printer_serial_map = printer_serial_map or {}
        self.transport = httpx.MockTransport(self._handle)

    # ---------------------------------------------------------------- helpers
    def _json(self, status: int, body: Any) -> httpx.Response:
        return httpx.Response(status, json=body)

    def _scene_or_404(self, scene_id: str):
        s = self.scenes.get(scene_id)
        return s if s is not None else self._json(404, {"error": f"scene {scene_id} not found (simulated)"})

    def _estimate(self, scene: Dict[str, Any]) -> tuple[float, float]:
        mb = sum(self.uploads.get(m["file"], 0) for m in scene["models"]) / 1e6
        total_s = _BASE_PRINT_S + _S_PER_MB * mb * max(1, len(scene["models"]))
        ml = round(_ML_PER_MB * mb * max(1, len(scene["models"])) + 3.0, 1)
        return total_s, ml

    # ---------------------------------------------------------------- router
    def _handle(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        m = request.method
        try:
            body = json.loads(request.content) if request.content and request.headers.get("content-type", "").startswith("application/json") else {}
        except json.JSONDecodeError:
            body = {}

        # ---- file_receiver (8089) ----
        if p == "/upload" and m == "POST":
            name = unquote(request.headers.get("X-Filename", "upload.stl"))   # 클라이언트가 quote() 해서 보낸다
            fake_path = f"C:\\STL_Files\\{name}"
            self.uploads[fake_path] = len(request.content or b"")
            return self._json(200, {"status": "ok", "file_path": fake_path, "simulated": True})
        if p.startswith("/screenshots/") and m == "GET":
            png = self.screenshots.get(p.rsplit("/", 1)[-1])
            return httpx.Response(200, content=png, headers={"content-type": "image/png"}) if png else self._json(404, {"error": "no screenshot"})

        # ---- PreFormServer (44388) ----
        if p == "/" and m == "GET":
            return self._json(200, {"name": "PreFormServer (simulated)", "version": "sim-1.0", "simulated": True})
        if p == "/list-materials/" and m == "GET":
            return self._json(200, {"materials": SIMULATED_MATERIALS})
        if p == "/discover-devices/" and m == "POST":
            serials = [s for _, s in sorted(self.printer_serial_map.items())] or ["Form4-SimPrinter"]   # .env 없는 개발자 PC 대비
            devices = [{"serial": s, "name": s.replace("Form4-", ""), "ip_address": "0.0.0.0", "machine_type": "FORM-4-0", "is_online": True}
                       for s in serials]
            return self._json(200, {"devices": devices})
        if p == "/load-form/" and m == "POST":
            sid = uuid.uuid4().hex[:12]
            self.scenes[sid] = {"id": sid, "machine_type": "FORM-4-0", "material_code": "FLGPGR05", "layer_thickness_mm": 0.1,
                                "models": [{"id": uuid.uuid4().hex[:8], "name": _basename(body.get("file", "form.form")), "file": body.get("file", "")}]}
            return self._json(200, {"id": sid})
        if p == "/scene/" and m == "POST":
            sid = uuid.uuid4().hex[:12]
            self.scenes[sid] = {"id": sid, "machine_type": body.get("machine_type", "FORM-4-0"),
                                "material_code": body.get("material_code", "FLGPGR05"),
                                "layer_thickness_mm": body.get("layer_thickness_mm", 0.1), "models": []}
            return self._json(200, {"id": sid, "simulated": True})

        mt = re.match(r"^/scene/([^/]+)/?(.*)$", p)
        if not mt:
            return self._json(404, {"error": f"simulated PreFormServer: unknown path {p}"})
        sid, rest = mt.group(1), mt.group(2).rstrip("/")
        scene = self._scene_or_404(sid)
        if isinstance(scene, httpx.Response):
            return scene

        if rest == "" and m == "GET":
            total_s, ml = self._estimate(scene)
            return self._json(200, {**scene, "estimated_print_time_ms": int(total_s * 1000), "estimated_material_ml": ml, "simulated": True})
        if rest == "" and m == "DELETE":
            self.scenes.pop(sid, None)
            return self._json(200, {"deleted": sid})
        if rest == "import-model" and m == "POST":
            f = body.get("file", "")
            scene["models"].append({"id": uuid.uuid4().hex[:8], "name": _basename(f), "file": f})
            return self._json(200, {"id": scene["models"][-1]["id"], "file": f})
        if rest in ("auto-orient", "auto-support", "auto-layout") and m == "POST":
            return self._json(200, {"ok": True, "step": rest, "simulated": True})
        if rest == "print-validation" and m == "GET":
            return self._json(200, {"valid": True, "errors": [], "warnings": [], "per_model_validations": [{"model_id": x["id"], "valid": True} for x in scene["models"]], "simulated": True})
        if rest == "estimate-print-time" and m == "POST":
            total_s, _ = self._estimate(scene)
            pre = 240.0
            return self._json(200, {"total_print_time_s": total_s, "preprint_time_s": pre, "printing_time_s": total_s - pre, "simulated": True})
        if rest == "interferences" and m == "POST":
            return self._json(200, [])
        if rest == "save-screenshot" and m == "POST":
            name = _basename(body.get("file", f"{sid}.png"))
            self.screenshots[name] = _tiny_png()
            return self._json(200, {"file": body.get("file"), "simulated": True})
        if rest == "hollow-model" and m == "POST":
            return self._json(200, {"ok": True})
        md = re.match(r"^models/([^/]+)/duplicate$", rest)
        if md and m == "POST":
            n = int(body.get("count", 1))
            src = next((x for x in scene["models"] if x["id"] == md.group(1)), None)
            if src is None:
                return self._json(404, {"error": "model not found"})
            for _ in range(n):
                scene["models"].append({**src, "id": uuid.uuid4().hex[:8]})
            return self._json(200, {"ok": True, "count": n})
        if rest == "print" and m == "POST":
            job = {"job_id": f"sim-{int(time.time())}-{sid[:6]}", "printer": body.get("printer"), "job_name": body.get("job_name"), "scene_id": sid, "simulated": True}
            self.jobs.append(job)
            return self._json(200, job)
        return self._json(404, {"error": f"simulated PreFormServer: unknown {m} {p}"})


_singleton: PreFormSimulator | None = None


def get_simulator(printer_serial_map: Dict[int, str] | None = None) -> PreFormSimulator:
    global _singleton
    if _singleton is None:
        _singleton = PreFormSimulator(printer_serial_map)
    return _singleton
