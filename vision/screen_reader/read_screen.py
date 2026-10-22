"""장비 화면 판독기 — 사진 1장(또는 웹캠 1프레임) → 클라우드 VLM(Gemini 기본 · Claude 선택) → 상태 JSON → (선택) MQTT 발행.

무엇 · 왜 (10/12 회의)
  "모니터 안의 텍스트를 읽는다 · 클라우드로 · 학습이 필요 없을 수도" + "최소한의 비전을 받아 다음 단계로 넘어가는 과정을 시연에 보여야"
  세척기(Form Wash)·경화기(Form Cure)는 API 가 없다 ⇒ 화면을 읽어야 "끝났다" 를 시스템이 안다(산출물 ③ 상태감시 · 정량목표 3).
  7/17: 분류 모델은 다른 날 데이터에서 0.34~0.70 으로 무너짐(배경 외움) → 룰베이스+OCR. 이번엔 OCR 자리에 VLM 을 넣어 본다.
  10/22: 회사 결제가 붙은 키는 Google Gemini(AI Studio · 선불 크레딧) ⇒ 기본 제공자를 Gemini 로. Claude 경로는 `--provider anthropic` 으로 남긴다.

설계 원칙
  · 입력 = 이미지 바이트. 카메라 종류·PC 종류에 매이지 않는다(C270 USB · HQ 카메라 · 폰 사진 전부 같은 길).
  · 출력 = 고정 스키마 JSON(아래 SCHEMA). 상태는 **enum** 이라 다음 단계가 문자열 파싱 없이 분기한다.
  · Gemini 호출은 표준 라이브러리(urllib)만 쓴다 — SDK 설치 없이 어느 PC 에서나 돈다(공장 PC 포함).
  · `--dry-run` = API 없이 요청 본문·스키마·파일 쓰기까지 전부 돈다(키 없는 PC·테스트용). 가짜 응답은 `"dry_run": true` 로 표시 — 성과로 읽지 않는다.
  · 지연시간(ms)을 결과에 남긴다 — 시험성적서 「시간 반응성」 측정값(화면 촬영 → 상태 판정)이 여기서 나온다.
  · `--eval <폴더>` = 7/14 라벨 사진(`<device>_<state>/*.jpg`) 전수 채점 → 정확도 표 + 토큰·비용 추정. "학습이 필요한가" 의 답은 이 숫자다.
  · `--publish` = 판정 결과를 서버가 구독하는 MQTT 토픽(`factory/{device}/{id}/status`)으로 발행 — 시뮬레이터(`web-api/app/vision/simulator.py`)와 같은 형식이라 서버 코드 변경 0.

키 (코드·리포에 두지 않는다 — 보안 원칙)
  Gemini  = 환경변수 GEMINI_API_KEY → 없으면 파일 `~/.ai_key`(600 · `--key-file` 로 바꿈)
  Claude  = 환경변수 ANTHROPIC_API_KEY (+ pip install anthropic)

실행
  python vision/screen_reader/read_screen.py --image photo.jpg [--dry-run] [--out result.json]
  python vision/screen_reader/read_screen.py --camera 0 --out result.json            # 웹캠 1프레임(cv2)
  python vision/screen_reader/read_screen.py --image photo.jpg --publish --camera-id wash_1 [--mqtt-host 127.0.0.1 --mqtt-port 1883]
  python vision/screen_reader/read_screen.py --eval /data/jtm/synth_out/maixcam_capture_0714/MaixCam_0714 --limit 5 [--dry-run] [--workers 4]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PROVIDERS = ("gemini", "anthropic")
MODEL_GEMINI = "gemini-2.5-flash"         # 10/22 1장 시험: 2.7~2.9초 · 이미지 258토큰 · 기본값. 작은 글자는 3.5-flash(1100토큰)가 유리 — --eval 로 비교
MODEL_ANTHROPIC = "claude-opus-5-5"       # 10/12 claude-api 스킬 기준 기본 모델
MODEL = MODEL_GEMINI
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
KEY_FILE = Path.home() / ".ai_key"
DEVICES = ("wash", "cure", "printer", "unknown")
STATES = ("idle", "running", "complete", "error", "unknown")

# 참고 단가(USD / 100만 토큰 · 입력, 출력) — 비용 "추정"에만 쓴다. 실제 지출은 AI Studio 「지출」 화면이 정본.
# 10/22 공식 가격표(ai.google.dev/gemini-api/docs/pricing) 확인 = 2.5-flash 0.30/2.50 · 3.5-flash-lite 0.30/2.50 · 3.8/3.6-flash 0.75/3.75(2026년까지)
# 3.5-flash 는 공식 표에 없음(구세대) → 집계 사이트 값 1.50/9.00 [미확인]
PRICE_USD_PER_M: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.8-flash": (0.75, 3.75),
}

# 다음 단계가 분기할 때 쓰는 고정 스키마. additionalProperties False 라 모델이 키를 지어내지 못한다.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "device": {"type": "string", "enum": list(DEVICES), "description": "어느 장비 화면인가"},
        "state": {"type": "string", "enum": list(STATES), "description": "idle=대기(작업 없음) · running=진행 중 · complete=끝남(꺼내도 됨) · error=오류·경고 표시"},
        "remaining_s": {"type": ["integer", "null"], "description": "남은 시간(초). 화면에 없으면 null"},
        "progress_pct": {"type": ["number", "null"], "description": "진행률 0~100. 없으면 null"},
        "screen_text": {"type": "string", "description": "화면에 보이는 글자를 읽은 그대로(줄바꿈은 ' | ')"},
        "confidence": {"type": "number", "description": "state 판정 확신 0~1"},
        "reason": {"type": "string", "description": "왜 그렇게 판정했나 — 한 문장 · 화면의 어떤 단서"},
    },
    "required": ["device", "state", "remaining_s", "progress_pct", "screen_text", "confidence", "reason"],
    "additionalProperties": False,
}

# 7/14 사진 6클래스를 눈으로 본 단서(10/22): 세척 완료는 "화면"이 아니라 "플랫폼이 올라와 있다"는 물리 단서다 — 글자만 읽게 하면 unknown 이 나온다.
SYSTEM = """You read photos of post-processing equipment in a 3D-printing factory and report the machine state as JSON.
Equipment: Formlabs Form Wash (IPA washer: a tall dark translucent bucket with a small OLED screen and a knob at the bottom front), Form Cure (UV cure oven: orange-tinted window, small OLED screen and knob below), Form 4 printer touchscreen.
Rules:
- Decide `device` from the machine's appearance and the screen wording. If none of the three, use "unknown".
- Form Wash states:
  running  = the build platform is DOWN inside the bucket and the screen shows a countdown timer (e.g. "8:33" with a preset like "10 min").
  complete = the build platform / basket has been RAISED UP out of the bucket (the metal platform carrier sits above the bucket lid). This is the physical sign the wash finished — even if the screen is small, dark or unreadable, a raised platform means complete.
  idle     = platform down, no timer; the screen shows a menu (e.g. "Custom", "Raise", a minutes setting).
- Form Cure states:
  running  = the chamber is lit violet/purple (UV lamps on) and/or the screen shows a countdown timer (e.g. "00:19").
  complete = the screen says "Finished" (or "Done"); chamber lamps off (window looks orange).
  idle     = the screen shows the start menu (e.g. "Start", "Grey V5", "Preheat", "Temp", "Cure 1 min"); lamps off.
- error = any error/warning dialog on the screen.
- Use "unknown" only when neither the screen nor the physical cues above can be seen (glare, blur, machine off, out of frame).
- Read numbers exactly as shown. A remaining time shown as M:SS or MM:SS becomes seconds in `remaining_s`.
- `screen_text` must contain the visible text verbatim (empty string if unreadable); do not translate it.
- `reason`: one short sentence naming the cue you used (screen text or platform/lamp state).
- Be strict: do not guess a state from the background; if the cues are not visible, say "unknown" with low confidence."""

USER_TEXT = "Report this equipment screen as JSON per the schema."


# ---------------------------------------------------------------------------
# 입력
# ---------------------------------------------------------------------------
def load_image_bytes(path: Path) -> tuple[bytes, str]:
    ext = path.suffix.lower()
    media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext)
    if not media:
        raise SystemExit(f"🔴 지원하지 않는 확장자 {ext} (jpg/png/webp)")
    data = path.read_bytes()
    if len(data) < 1000:
        raise SystemExit(f"🔴 이미지가 너무 작다({len(data)}B) — 깨진 파일?")
    return data, media


def capture_webcam(index: int, out: Path, warmup: int = 10) -> Path:
    """USB 웹캠(C270 등) 1프레임 → jpg. 첫 프레임들은 노출이 안 잡혀 어두우니 warmup 만큼 버린다."""
    import cv2
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise SystemExit(f"🔴 카메라 {index} 를 못 연다 — USB 꽂힘·다른 프로그램이 잡고 있나·번호(0/1)")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    frame = None
    for _ in range(warmup + 1):
        ok, frame = cap.read()
        if not ok:
            frame = None
    cap.release()
    if frame is None:
        raise SystemExit("🔴 프레임을 못 받았다")
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"[촬영] {out} {frame.shape[1]}x{frame.shape[0]}")
    return out


# ---------------------------------------------------------------------------
# 요청 본문 — 네트워크 없이도 만들어지고, 테스트가 이것을 검사한다
# ---------------------------------------------------------------------------
def build_request_gemini(image: bytes, media_type: str, model: str = MODEL_GEMINI, *, think: bool = False) -> dict[str, Any]:
    """Gemini generateContent 본문. 스키마는 response_json_schema(JSON Schema 그대로 · 10/22 2.5/3.5 확인).
    think=False 면 thinking_budget 0 — 판정에 추론이 필요 없고 지연이 줄어든다(3.5-flash-lite 는 이 키를 거부 → call 에서 빼고 재시도)."""
    gc: dict[str, Any] = {
        "temperature": 0,                         # 같은 사진 → 같은 답(채점·시험 재현성)
        "max_output_tokens": 1024,
        "response_mime_type": "application/json",
        "response_json_schema": SCHEMA,
    }
    if not think:
        gc["thinking_config"] = {"thinking_budget": 0}
    return {
        "model": model,
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": media_type, "data": base64.standard_b64encode(image).decode("ascii")}},
            {"text": USER_TEXT},
        ]}],
        "generationConfig": gc,
    }


def build_request(image: bytes, media_type: str, model: str = MODEL_ANTHROPIC) -> dict[str, Any]:
    """Anthropic messages 본문(10/13 원형 · `--provider anthropic`)."""
    return {
        "model": model,
        "max_tokens": 1024,                       # 출력은 작은 JSON 하나 · 짧게 잡아도 잘릴 일이 없다
        "system": SYSTEM,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(image).decode("ascii")}},
                {"type": "text", "text": USER_TEXT},
            ],
        }],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def validate_result(d: dict[str, Any]) -> dict[str, Any]:
    """모델 답이 스키마대로 왔는지 우리 쪽에서도 한 번 더 — 조용히 틀린 값이 다음 단계로 가지 않게."""
    missing = [k for k in SCHEMA["required"] if k not in d]
    if missing:
        raise ValueError(f"응답에 키가 없다: {missing}")
    if d["device"] not in DEVICES or d["state"] not in STATES:
        raise ValueError(f"enum 밖: device={d['device']!r} state={d['state']!r}")
    if not (0.0 <= float(d["confidence"]) <= 1.0):
        raise ValueError(f"confidence 범위 밖: {d['confidence']}")
    if d["remaining_s"] is not None and int(d["remaining_s"]) < 0:
        raise ValueError(f"remaining_s 음수: {d['remaining_s']}")
    return d


# ---------------------------------------------------------------------------
# 호출
# ---------------------------------------------------------------------------
class ReadError(RuntimeError):
    """한 장 판독 실패(API 오류 · 타임아웃 · JSON 깨짐). 단건 CLI 는 그대로 종료, 채점(--eval)은 그 장만 실패로 적고 계속 간다.
    10/22 전수 채점에서 2.5-flash 가 1장에 '\\r\\n' 만 1024토큰 뱉고(MAX_TOKENS) 3.5-flash 가 1장에 60초 타임아웃 → SystemExit 로 215장 채점이 통째로 죽었다."""


def load_gemini_key(key_file: Path = KEY_FILE) -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    if key_file.exists():
        k = key_file.read_text(encoding="utf-8").strip()
        if k:
            return k
    raise SystemExit(f"🔴 Gemini 키가 없다 — 환경변수 GEMINI_API_KEY 또는 파일 {key_file}(600)  (또는 --dry-run)")


def call_gemini(req: dict[str, Any], *, key: str, timeout: float = 60.0) -> tuple[dict[str, Any], dict[str, Any]]:
    """실제 호출(urllib · SDK 불필요). (결과 JSON, 메타{토큰, finish_reason, model_version})."""
    model = req["model"]
    body = {k: v for k, v in req.items() if k != "model"}

    def _post(b: dict[str, Any]) -> dict[str, Any]:
        r = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(b).encode("utf-8"),
                                   headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(r, timeout=timeout))

    try:
        try:
            resp = _post(body)
        except urllib.error.HTTPError as e:
            # 3.5-flash-lite 는 thinking_config 를 400 으로 거부(10/22) → 그 키만 빼고 한 번 더
            if e.code == 400 and "thinking_config" in body.get("generationConfig", {}):
                body = {**body, "generationConfig": {k: v for k, v in body["generationConfig"].items() if k != "thinking_config"}}
                resp = _post(body)
            else:
                raise
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code in (401, 403):
            raise ReadError(f"API 키가 틀리거나 권한 없음({e.code}): {detail}")
        if e.code == 429:
            raise ReadError(f"요청 한도(429) — 잠시 뒤 재시도: {detail}")
        raise ReadError(f"API 오류 {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise ReadError(f"네트워크 — 인터넷·프록시 확인: {e.reason}")
    except (TimeoutError, OSError) as e:                     # urlopen 의 read timeout 은 socket.timeout/TimeoutError 로 올라온다
        raise ReadError(f"타임아웃({timeout:.0f}s): {e}")

    cands = resp.get("candidates") or []
    if not cands:
        raise ReadError(f"응답에 candidates 가 없다(차단?): {json.dumps(resp)[:300]}")
    c = cands[0]
    text = "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []))
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        raise ReadError(f"JSON 이 아니다(finish={c.get('finishReason')}): {text[:120]!r}")
    u = resp.get("usageMetadata", {})
    meta = {"input_tokens": u.get("promptTokenCount"), "output_tokens": u.get("candidatesTokenCount"),
            "thinking_tokens": u.get("thoughtsTokenCount", 0), "total_tokens": u.get("totalTokenCount"),
            "finish_reason": c.get("finishReason"), "model_version": resp.get("modelVersion"),
            "thinking_off": "thinking_config" in body.get("generationConfig", {})}
    try:
        return validate_result(d), meta
    except ValueError as e:
        raise ReadError(f"스키마 밖 응답: {e}")


def call_claude(req: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """실제 호출. (결과 JSON, 메타{usage, request_id}) — SDK 는 여기서만 import(없는 PC 에서도 dry-run 은 돈다)."""
    try:
        import anthropic
    except ImportError:
        raise SystemExit("🔴 anthropic SDK 없음 → pip install anthropic  (또는 --dry-run)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("🔴 ANTHROPIC_API_KEY 가 없다 — 환경변수로만 넣는다(코드·리포에 키 금지)  (또는 --dry-run)")
    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(**req)
    except anthropic.AuthenticationError:
        raise SystemExit("🔴 API 키가 틀렸다")
    except anthropic.RateLimitError as e:
        raise SystemExit(f"🔴 요청 한도 — {e.response.headers.get('retry-after', '?')}초 뒤 재시도")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"🔴 API 오류 {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit("🔴 네트워크 — 인터넷·프록시 확인")
    if resp.stop_reason == "refusal":
        raise SystemExit(f"🔴 모델이 거부: {getattr(resp.stop_details, 'category', None)}")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit(f"🔴 JSON 이 아니다: {text[:200]!r}")
    meta = {"request_id": resp._request_id, "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens, "stop_reason": resp.stop_reason}
    return validate_result(d), meta


def fake_result(path: Path) -> dict[str, Any]:
    """dry-run 전용. 파일명에 wash/cure/idle/running/complete 가 있으면 그대로 돌려줘 채점 경로까지 시험된다."""
    name = path.stem.lower()
    dev = next((x for x in ("wash", "cure", "printer") if x in name), "unknown")
    st = next((x for x in ("running", "complete", "idle", "error") if x in name), "unknown")
    return {"device": dev, "state": st, "remaining_s": None, "progress_pct": None,
            "screen_text": "(dry-run · 화면을 읽지 않았다)", "confidence": 0.0,
            "reason": "dry-run — 파일명으로 채운 가짜 값", "dry_run": True}


def read_one(path: Path, *, dry_run: bool, model: str = MODEL, provider: str = "gemini",
             key: str | None = None, think: bool = False, fallback_model: str | None = None) -> dict[str, Any]:
    img, media = load_image_bytes(path)
    if provider == "gemini":
        req = build_request_gemini(img, media, model, think=think)
    else:
        req = build_request(img, media, model)
    t0 = time.perf_counter()
    if dry_run:
        res, meta = fake_result(path), {"dry_run": True, "attempts": 1}
    elif provider == "gemini":
        res, meta = call_gemini_robust(img, media, model, key=key or load_gemini_key(), think=think, fallback_model=fallback_model)
    else:
        res, meta = call_claude(req)
        meta["attempts"] = 1
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {"image": str(path), "image_bytes": len(img), "provider": provider, "model": meta.get("model_used", model), "latency_ms": latency_ms,
            "result": res, "meta": meta, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


RETRY_BACKOFF_S = (1.0, 3.0)                 # 503/429 뒤 기다리는 시간(초) — 최대 3회 시도. 10/22 2.5-flash 전수에서 215장 중 83장이 503("high demand")


def _is_transient(err: ReadError) -> bool:
    s = str(err)
    return s.startswith("API 오류 503") or s.startswith("요청 한도(429)") or s.startswith("타임아웃") or s.startswith("네트워크")


def _is_content(err: ReadError) -> bool:
    """모델이 답은 했는데 쓸 수 없는 경우 — 설정을 바꿔 다시 물을 가치가 있다. 키 오류(401/403)·기타 4xx 는 여기 안 들어가 바로 실패."""
    s = str(err)
    return s.startswith("JSON 이 아니다") or s.startswith("스키마 밖 응답") or s.startswith("응답에 candidates")


def call_gemini_robust(img: bytes, media: str, model: str, *, key: str, think: bool = False,
                       fallback_model: str | None = None, sleep=time.sleep) -> tuple[dict[str, Any], dict[str, Any]]:
    """한 장을 끝까지 읽어내는 호출 순서:
      ① 그대로 → ② 일시 오류(503·429·타임아웃·네트워크)면 1초·3초 쉬고 같은 요청 재시도(최대 3회) /
         JSON 깨짐·스키마 밖이면 추론 설정을 뒤집어 1회(temperature 0 이라 같은 요청은 같은 답이 또 나온다)
      ③ 그래도 안 되면 fallback_model 로 ①② 한 번 더
    meta 에 attempts · model_used · 재시도 사유를 남긴다 — 시험 중 어느 단계에서 살았는지가 증적이다."""
    log: list[str] = []
    for m in [model] + ([fallback_model] if fallback_model and fallback_model != model else []):
        attempts_left = 3
        use_think = think
        while attempts_left > 0:
            attempts_left -= 1
            try:
                res, meta = call_gemini(build_request_gemini(img, media, m, think=use_think), key=key)
                meta.update({"attempts": len(log) + 1, "model_used": m, "retried_after": log[-1][:160] if log else None, "retry_log": log})
                return res, meta
            except ReadError as e:
                log.append(f"{m}: {e}")
                if _is_transient(e):
                    if attempts_left > 0:
                        sleep(RETRY_BACKOFF_S[min(len(RETRY_BACKOFF_S) - 1, 2 - attempts_left)])
                    continue
                if _is_content(e) and attempts_left == 2:    # 내용 오류(JSON 깨짐 등)는 설정 뒤집어 1회만
                    use_think = not use_think
                    attempts_left = 1
                    continue
                break                                        # 키·권한·기타 4xx = 다시 보내도 같다
    raise ReadError(f"{len(log)}회 실패 — " + " / ".join(x[:140] for x in log))


# ---------------------------------------------------------------------------
# MQTT 발행 — 서버(web-api vision/mqtt_client.py)가 구독하는 그 토픽·그 필드(simulator.py 와 동일)
# ---------------------------------------------------------------------------
def to_status_payload(res: dict[str, Any], *, camera_id: str, request_id: str | None = None) -> tuple[str, dict[str, Any]] | None:
    """판정 → (토픽, 페이로드). 서버 enum(DeviceStatus) 밖이면 None — unknown/printer 는 발행하지 않는다(가짜 상태를 화면에 올리지 않기 위해)."""
    dev, st = res["device"], res["state"]
    if dev not in ("wash", "cure"):
        return None
    status = "error" if st == "error" else (f"{dev}_{st}" if st in ("idle", "running", "complete") else None)
    if status is None:
        return None
    try:
        cam_dev, cam_id = camera_id.rsplit("_", 1)
        device_id = int(cam_id)
    except ValueError:
        raise SystemExit(f"🔴 --camera-id 는 <device>_<번호> 꼴이어야 한다(예 wash_1): {camera_id!r}")
    if cam_dev != dev:
        print(f"  ⚠️ 카메라 {camera_id} 인데 판독은 {dev} — 토픽은 카메라 기준으로 간다(판독 device 는 payload 에 남김)")
    topic = f"factory/{cam_dev}/{device_id}/status"
    payload = {"camera_id": camera_id, "device_type": cam_dev, "device_id": device_id, "status": status,
               "confidence": float(res["confidence"]), "timestamp": time.time(),
               "consecutive_count": 1, "fps": 0.0, "mem_free": 0,
               "reader": {"device": dev, "state": st, "remaining_s": res.get("remaining_s"), "screen_text": res.get("screen_text")}}
    if request_id:
        payload["request_id"] = request_id
    return topic, payload


def publish_status(topic: str, payload: dict[str, Any], *, host: str, port: int) -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise SystemExit("🔴 paho-mqtt 없음 → pip install paho-mqtt  (web-api venv 엔 있음)")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(host, port, keepalive=10)
    except OSError as e:
        raise SystemExit(f"🔴 MQTT 브로커 {host}:{port} 연결 실패: {e}")
    client.loop_start()                       # qos=1 의 PUBACK 은 네트워크 루프가 돌아야 들어온다 — 없으면 보내고도 "확인 안 됨"(10/22 왕복 시험에서 잡음)
    info = client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)
    info.wait_for_publish(timeout=5)
    published = info.is_published()
    client.loop_stop()
    client.disconnect()
    if not published:
        raise SystemExit("🔴 MQTT 발행이 확인되지 않았다(브로커 응답 없음)")
    print(f"[발행] {topic} status={payload['status']} conf={payload['confidence']:.2f}" + (f" request_id={payload['request_id']}" if "request_id" in payload else ""))


# ---------------------------------------------------------------------------
# 채점 — 7/14 라벨 사진(<device>_<state>/*.jpg)
# ---------------------------------------------------------------------------
def estimate_cost_usd(model: str, in_tok: int, out_tok: int) -> float | None:
    p = PRICE_USD_PER_M.get(model)
    return round(in_tok / 1e6 * p[0] + out_tok / 1e6 * p[1], 4) if p else None


def evaluate(root: Path, *, dry_run: bool, limit_per_class: int, model: str, out: Path | None,
             provider: str = "gemini", workers: int = 1, think: bool = False, fallback_model: str | None = None) -> dict[str, Any]:
    jobs: list[tuple[Path, str, str]] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            dev, st = d.name.split("_", 1)
        except ValueError:
            print(f"  ⚪ 건너뜀(폴더명이 <device>_<state> 아님): {d.name}")
            continue
        if dev not in DEVICES or st not in STATES:
            print(f"  ⚪ 건너뜀(enum 밖): {d.name}")
            continue
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))[:limit_per_class]
        jobs += [(f, dev, st) for f in files]

    key = None if (dry_run or provider != "gemini") else load_gemini_key()

    def run(job: tuple[Path, str, str]) -> dict[str, Any]:
        f, dev, st = job
        t0 = time.perf_counter()
        try:
            r = read_one(f, dry_run=dry_run, model=model, provider=provider, key=key, think=think, fallback_model=fallback_model)
        except ReadError as e:
            # 그 장만 실패로 적고 계속 — 215장 중 1장 때문에 전체가 죽지 않게. pred 는 enum 밖 값이라 어느 클래스와도 안 맞는다.
            return {"file": str(f), "gt_device": dev, "gt_state": st, "pred_device": "api_error", "pred_state": "api_error",
                    "ok": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "confidence": 0.0,
                    "remaining_s": None, "screen_text": "", "reason": f"API 실패: {e}"[:300],
                    "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "attempts": 2, "api_error": True}
        pred, meta = r["result"], r["meta"]
        ok_dev, ok_st = pred["device"] == dev, pred["state"] == st
        return {"file": str(f), "gt_device": dev, "gt_state": st, "pred_device": pred["device"], "pred_state": pred["state"],
                "ok": ok_dev and ok_st, "latency_ms": r["latency_ms"], "confidence": pred["confidence"],
                "remaining_s": pred.get("remaining_s"), "screen_text": pred.get("screen_text", ""), "reason": pred["reason"],
                "input_tokens": meta.get("input_tokens") or 0, "output_tokens": meta.get("output_tokens") or 0,
                "thinking_tokens": meta.get("thinking_tokens") or 0, "attempts": meta.get("attempts", 1),
                "retried_after": meta.get("retried_after"), "model_used": meta.get("model_used", model)}

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for row in ex.map(run, jobs):          # 순서 보존 — 로그를 폴더 순으로 읽을 수 있게
            rows.append(row)
            mark = "🟢" if row["ok"] else "🔴"
            cls = f"{row['gt_device']}_{row['gt_state']}"
            print(f"  {mark} {cls}/{Path(row['file']).name}: {row['pred_device']}/{row['pred_state']} ({row['latency_ms']:.0f}ms)"
                  f"{'' if row['ok'] else ' ← ' + row['reason'][:70]}", flush=True)

    n = len(rows)
    acc = sum(r["ok"] for r in rows) / n if n else 0.0
    by: dict[str, list[bool]] = {}
    conf: dict[str, dict[str, int]] = {}                    # 혼동표: 정답 클래스 → 예측 클래스 → 개수
    for r in rows:
        g = f"{r['gt_device']}_{r['gt_state']}"
        by.setdefault(g, []).append(r["ok"])
        conf.setdefault(g, {})
        p = f"{r['pred_device']}_{r['pred_state']}"
        conf[g][p] = conf[g].get(p, 0) + 1
    lat = sorted(r["latency_ms"] for r in rows)
    in_tok = sum(r["input_tokens"] for r in rows)
    out_tok = sum(r["output_tokens"] for r in rows) + sum(r["thinking_tokens"] for r in rows)
    summary = {"n": n, "accuracy": round(acc, 4), "per_class": {k: f"{sum(v)}/{len(v)}" for k, v in by.items()},
               "confusion": conf,
               "api_errors": sum(1 for r in rows if r.get("api_error")), "retried": sum(1 for r in rows if r.get("attempts", 1) > 1 and not r.get("api_error")),
               "fallback_used": sum(1 for r in rows if r.get("model_used") not in (None, model)), "fallback_model": fallback_model,
               "latency_ms_median": lat[len(lat) // 2] if lat else None,
               "latency_ms_p90": lat[min(n - 1, int(n * 0.9))] if lat else None,
               "latency_ms_max": lat[-1] if lat else None,
               "input_tokens": in_tok, "output_tokens": out_tok,
               "tokens_per_image": round((in_tok + out_tok) / n, 1) if n else None,
               "cost_usd_est": estimate_cost_usd(model, in_tok, out_tok), "cost_note": "참고 단가(PRICE_USD_PER_M) 기준 추정 · 실제는 AI Studio 지출 화면",
               "dry_run": dry_run, "provider": provider, "model": model, "thinking_off": not think, "workers": workers, "rows": rows}
    print(f"\n[{model}] 정확도 {acc*100:.1f}% ({sum(r['ok'] for r in rows)}/{n}) · 클래스별 {summary['per_class']}"
          f" · API 실패 {summary['api_errors']} · 재시도 성공 {summary['retried']} · 대체 모델 사용 {summary['fallback_used']}"
          f"\n  지연 중앙값 {summary['latency_ms_median']}ms · p90 {summary['latency_ms_p90']}ms · 최대 {summary['latency_ms_max']}ms"
          f" · 토큰 입력 {in_tok} 출력 {out_tok} (장당 {summary['tokens_per_image']}) · 비용 추정 ${summary['cost_usd_est']}"
          + ("  ⚠️ dry-run = 파일명으로 채운 가짜 값 · 성과 아님" if dry_run else ""))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장 {out}")
    return summary


def main() -> int:
    try:
        from bin_picking.src.utils.console_utf8 import enable_utf8_console
        enable_utf8_console()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="장비 화면 사진 → 상태 JSON (Gemini VLM 기본 · Claude 선택) → (선택) MQTT 발행")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="사진 1장")
    src.add_argument("--camera", type=int, help="웹캠 번호(0,1,…) — 1프레임 찍어서 판독")
    src.add_argument("--eval", type=Path, help="라벨 폴더(<device>_<state>/*.jpg) 전수 채점")
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 전부 돌린다(가짜 응답 · 성과 아님)")
    ap.add_argument("--provider", choices=PROVIDERS, default="gemini")
    ap.add_argument("--model", default=None, help=f"기본 = gemini {MODEL_GEMINI} / anthropic {MODEL_ANTHROPIC}")
    ap.add_argument("--think", action="store_true", help="Gemini 추론(thinking) 켜기 — 기본은 끔(빠름)")
    ap.add_argument("--fallback-model", default=None, help="주 모델이 재시도 뒤에도 실패하면 이 모델로 1회 더(예 gemini-3.5-flash-lite)")
    ap.add_argument("--key-file", type=Path, default=KEY_FILE, help="Gemini 키 파일(환경변수 GEMINI_API_KEY 가 우선)")
    ap.add_argument("--limit", type=int, default=5, help="--eval: 클래스당 장수(비용 가드 · 전수는 999)")
    ap.add_argument("--workers", type=int, default=1, help="--eval: 동시 호출 수(채점 속도 · 지연 측정은 1 로)")
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 저장 경로")
    ap.add_argument("--capture-out", type=Path, default=Path("vision/screen_reader/captures/last.jpg"))
    ap.add_argument("--publish", action="store_true", help="판정을 MQTT factory/{device}/{id}/status 로 발행(--camera-id 필수)")
    ap.add_argument("--camera-id", default=None, help="발행 카메라 ID(wash_1 · wash_2 · cure_1 · cure_2)")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_BROKER_HOST", "127.0.0.1"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_BROKER_PORT", "1883")))
    ap.add_argument("--request-id", default=None, help="시험용 요청번호 — 서버가 화면 메시지에 그대로 돌려준다")
    a = ap.parse_args()
    model = a.model or (MODEL_GEMINI if a.provider == "gemini" else MODEL_ANTHROPIC)
    if a.key_file != KEY_FILE:
        globals()["KEY_FILE"] = a.key_file

    if a.eval:
        if not a.eval.is_dir():
            raise SystemExit(f"🔴 폴더 아님: {a.eval}")
        evaluate(a.eval, dry_run=a.dry_run, limit_per_class=a.limit, model=model, out=a.out,
                 provider=a.provider, workers=a.workers, think=a.think, fallback_model=a.fallback_model)
        return 0
    if a.publish and not a.camera_id:
        raise SystemExit("🔴 --publish 에는 --camera-id 가 필요하다(예 --camera-id wash_1)")
    path = a.image if a.image is not None else capture_webcam(a.camera, a.capture_out)
    if not path.exists():
        raise SystemExit(f"🔴 파일 없음: {path}")
    key = None if (a.dry_run or a.provider != "gemini") else load_gemini_key(a.key_file)
    try:
        r = read_one(path, dry_run=a.dry_run, model=model, provider=a.provider, key=key, think=a.think, fallback_model=a.fallback_model)
    except ReadError as e:
        raise SystemExit(f"🔴 {e}")
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장 {a.out}")
    if a.publish:
        tp = to_status_payload(r["result"], camera_id=a.camera_id, request_id=a.request_id)
        if tp is None:
            print(f"  ⚪ 발행 안 함 — 서버 상태 enum 밖(device={r['result']['device']} state={r['result']['state']})")
        else:
            publish_status(tp[0], tp[1], host=a.mqtt_host, port=a.mqtt_port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
