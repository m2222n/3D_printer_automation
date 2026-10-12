"""장비 화면 판독기 — 사진 1장(또는 웹캠 1프레임) → 클라우드 VLM(Claude) → 상태 JSON.

무엇 · 왜 (10/12 회의)
  "모니터 안의 텍스트를 읽는다 · 클라우드로 · 학습이 필요 없을 수도" + "최소한의 비전을 받아 다음 단계로 넘어가는 과정을 시연에 보여야"
  세척기(Form Wash)·경화기(Form Cure)는 API 가 없다 ⇒ 화면을 읽어야 "끝났다" 를 시스템이 안다(산출물 ③ 상태감시 · 정량목표 3).
  7/17: 분류 모델은 다른 날 데이터에서 0.34~0.70 으로 무너짐(배경 외움) → 룰베이스+OCR. 이번엔 OCR 자리에 VLM 을 넣어 본다.

설계 원칙
  · 입력 = 이미지 바이트. 카메라 종류·PC 종류에 매이지 않는다(C270 USB · HQ 카메라 · 폰 사진 전부 같은 길).
  · 출력 = 고정 스키마 JSON(아래 SCHEMA). 상태는 **enum** 이라 다음 단계가 문자열 파싱 없이 분기한다.
  · `--dry-run` = API 없이 요청 본문·스키마·파일 쓰기까지 전부 돈다(키 없는 PC·테스트용). 가짜 응답은 `"dry_run": true` 로 표시 — 성과로 읽지 않는다.
  · 지연시간(ms)을 결과에 남긴다 — 시험성적서 「시간 반응성」 측정값(화면 촬영 → 상태 판정)이 여기서 나온다.
  · `--eval <폴더>` = 7/14 라벨 사진(`<device>_<state>/*.jpg`) 전수 채점 → 정확도 표. "학습이 필요한가" 의 답은 이 숫자다.

실행
  python vision/screen_reader/read_screen.py --image photo.jpg [--dry-run] [--out result.json]
  python vision/screen_reader/read_screen.py --camera 0 --out result.json            # 웹캠 1프레임(cv2)
  python vision/screen_reader/read_screen.py --eval /data/jtm/synth_out/maixcam_capture_0714/MaixCam_0714 --limit 5 [--dry-run]
  실제 호출 전제 = pip install anthropic · 환경변수 ANTHROPIC_API_KEY (키는 코드·리포에 두지 않는다 — 보안 원칙)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

MODEL = "claude-opus-5-5"            # 10/12 claude-api 스킬 기준 기본 모델 · 비용은 Haiku 로 낮출 수 있으나 정확도 먼저
DEVICES = ("wash", "cure", "printer", "unknown")
STATES = ("idle", "running", "complete", "error", "unknown")

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

SYSTEM = """You read photos of post-processing equipment screens in a 3D-printing factory and report the machine state as JSON.
Equipment: Formlabs Form Wash (IPA washer), Form Cure (UV cure), Form 4 printer touchscreen.
Rules:
- Decide `device` from the screen layout/wording. If none of the three, use "unknown".
- `state`: running = a timer is counting down or a progress bar/animation is active; complete = the screen says done/finished/remove parts or a finished timer (00:00) with a completion message; idle = home/ready screen with no job; error = any error/warning dialog. Use "unknown" only when the screen is unreadable (glare, blur, off).
- Read numbers exactly as shown. A remaining time shown as MM:SS becomes seconds in `remaining_s`.
- `screen_text` must contain the visible text verbatim; do not translate it.
- Be strict: if you cannot read the screen, say "unknown" with low confidence instead of guessing."""

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
def build_request(image: bytes, media_type: str, model: str = MODEL) -> dict[str, Any]:
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


def read_one(path: Path, *, dry_run: bool, model: str = MODEL) -> dict[str, Any]:
    img, media = load_image_bytes(path)
    req = build_request(img, media, model)
    t0 = time.perf_counter()
    if dry_run:
        res, meta = fake_result(path), {"dry_run": True}
    else:
        res, meta = call_claude(req)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {"image": str(path), "image_bytes": len(img), "model": model, "latency_ms": latency_ms,
            "result": res, "meta": meta, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


# ---------------------------------------------------------------------------
# 채점 — 7/14 라벨 사진(<device>_<state>/*.jpg)
# ---------------------------------------------------------------------------
def evaluate(root: Path, *, dry_run: bool, limit_per_class: int, model: str, out: Path | None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
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
        for f in files:
            r = read_one(f, dry_run=dry_run, model=model)
            pred = r["result"]
            ok_dev, ok_st = pred["device"] == dev, pred["state"] == st
            rows.append({"file": str(f), "gt_device": dev, "gt_state": st, "pred_device": pred["device"],
                         "pred_state": pred["state"], "ok": ok_dev and ok_st, "latency_ms": r["latency_ms"],
                         "confidence": pred["confidence"], "reason": pred["reason"]})
            mark = "🟢" if (ok_dev and ok_st) else "🔴"
            print(f"  {mark} {d.name}/{f.name}: {pred['device']}/{pred['state']} ({r['latency_ms']:.0f}ms) {'' if ok_dev and ok_st else '← ' + pred['reason'][:60]}")
    n = len(rows)
    acc = sum(r["ok"] for r in rows) / n if n else 0.0
    by: dict[str, list[bool]] = {}
    for r in rows:
        by.setdefault(f"{r['gt_device']}_{r['gt_state']}", []).append(r["ok"])
    lat = sorted(r["latency_ms"] for r in rows)
    summary = {"n": n, "accuracy": round(acc, 4), "per_class": {k: f"{sum(v)}/{len(v)}" for k, v in by.items()},
               "latency_ms_median": lat[len(lat) // 2] if lat else None, "latency_ms_max": lat[-1] if lat else None,
               "dry_run": dry_run, "model": model, "rows": rows}
    print(f"\n정확도 {acc*100:.1f}% ({sum(r['ok'] for r in rows)}/{n}) · 클래스별 {summary['per_class']}"
          f" · 지연 중앙값 {summary['latency_ms_median']}ms 최대 {summary['latency_ms_max']}ms"
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
    ap = argparse.ArgumentParser(description="장비 화면 사진 → 상태 JSON (Claude VLM)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="사진 1장")
    src.add_argument("--camera", type=int, help="웹캠 번호(0,1,…) — 1프레임 찍어서 판독")
    src.add_argument("--eval", type=Path, help="라벨 폴더(<device>_<state>/*.jpg) 전수 채점")
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 전부 돌린다(가짜 응답 · 성과 아님)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=5, help="--eval: 클래스당 장수(비용 가드 · 전수는 999)")
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 저장 경로")
    ap.add_argument("--capture-out", type=Path, default=Path("vision/screen_reader/captures/last.jpg"))
    a = ap.parse_args()

    if a.eval:
        if not a.eval.is_dir():
            raise SystemExit(f"🔴 폴더 아님: {a.eval}")
        evaluate(a.eval, dry_run=a.dry_run, limit_per_class=a.limit, model=a.model, out=a.out)
        return 0
    path = a.image if a.image is not None else capture_webcam(a.camera, a.capture_out)
    if not path.exists():
        raise SystemExit(f"🔴 파일 없음: {path}")
    r = read_one(path, dry_run=a.dry_run, model=a.model)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
