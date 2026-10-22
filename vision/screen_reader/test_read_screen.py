"""read_screen 검증 — 네트워크·키 없이 도는 부분 전부 (실행: python vision/screen_reader/test_read_screen.py)

① 요청 본문 = 이미지가 base64 로 들어가고 스키마가 output_config 에 실린다(SDK 호출 모양 · 키 이름)
①' Gemini 본문(10/22) = system_instruction · inline_data · response_json_schema · thinking_budget 0 — 키 이름 하나 틀리면 400 이라 여기서 잡는다
② validate_result 가 조용히 틀린 값을 막는다(enum 밖 · 키 누락 · 범위)
③ dry-run 이 파일 → 결과 JSON 까지 끝까지 돈다 · dry_run 표시가 붙는다
④ 채점(evaluate) 이 라벨 폴더를 읽고 정확도를 낸다(dry-run 으로 100% = 채점 경로 자체의 검사이지 성능이 아니다) · workers>1 도 순서·개수 보존
⑤ 🧪 그물: 폴더명을 enum 밖으로 바꾸면 건너뛰고, 가짜 응답의 state 를 틀리게 하면 정확도가 떨어진다
⑥ MQTT 페이로드(10/22) = 서버 MQTTStatusMessage 필드·토픽 꼴 · enum 밖(unknown/printer)은 None · request_id 가 실린다
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

OK = True


def check(name: str, cond: bool) -> None:
    global OK
    print(("  🟢 " if cond else "  🔴 ") + name)
    OK = OK and bool(cond)


def _jpg(path: Path, text: str = "WASHING 12:34") -> Path:
    import cv2
    im = np.full((360, 640, 3), 30, np.uint8)
    cv2.putText(im, text, (40, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (240, 240, 240), 3)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), im)
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        img = _jpg(td / "wash_running_1.jpg")
        print("① 요청 본문")
        data, media = rs.load_image_bytes(img)
        req = rs.build_request(data, media)
        c = req["messages"][0]["content"]
        check("model(anthropic 기본) · max_tokens · system 이 있다", req["model"] == rs.MODEL_ANTHROPIC and req["max_tokens"] > 0 and "Form Wash" in req["system"])
        check("첫 블록이 image/base64/jpeg", c[0]["type"] == "image" and c[0]["source"]["type"] == "base64" and c[0]["source"]["media_type"] == "image/jpeg")
        check("base64 가 원본 바이트를 복원한다", __import__("base64").b64decode(c[0]["source"]["data"]) == data)
        check("스키마가 output_config.format.json_schema 에", req["output_config"]["format"]["type"] == "json_schema" and req["output_config"]["format"]["schema"] is rs.SCHEMA)
        check("스키마 additionalProperties False · required 7", rs.SCHEMA["additionalProperties"] is False and len(rs.SCHEMA["required"]) == 7)

        print("①' Gemini 요청 본문")
        g = rs.build_request_gemini(data, media)
        gp = g["contents"][0]["parts"]
        check("model 기본 = gemini · system_instruction 에 Form Wash", g["model"] == rs.MODEL_GEMINI and "Form Wash" in g["system_instruction"]["parts"][0]["text"])
        check("첫 파트 inline_data(jpeg) · 둘째 파트 text", gp[0]["inline_data"]["mime_type"] == "image/jpeg" and gp[1]["text"] == rs.USER_TEXT)
        check("base64 가 원본 바이트를 복원한다", __import__("base64").b64decode(gp[0]["inline_data"]["data"]) == data)
        gc = g["generationConfig"]
        check("JSON 강제 = response_mime_type + response_json_schema(SCHEMA 그대로)", gc["response_mime_type"] == "application/json" and gc["response_json_schema"] is rs.SCHEMA)
        check("temperature 0 · thinking_budget 0(기본) · --think 면 빠짐", gc["temperature"] == 0 and gc["thinking_config"] == {"thinking_budget": 0}
              and "thinking_config" not in rs.build_request_gemini(data, media, think=True)["generationConfig"])
        check("model 키는 URL 용 — 본문 키와 겹치지 않는다", "model" not in gc and set(g) == {"model", "system_instruction", "contents", "generationConfig"})

        print("② validate_result")
        good = {"device": "wash", "state": "running", "remaining_s": 754, "progress_pct": 40.0,
                "screen_text": "WASHING | 12:34", "confidence": 0.9, "reason": "timer counting"}
        check("정상 값 통과", rs.validate_result(dict(good)) == good)
        for bad, why in (({**good, "state": "washing"}, "enum 밖 state"), ({**good, "confidence": 1.5}, "confidence>1"),
                         ({k: v for k, v in good.items() if k != "reason"}, "키 누락"), ({**good, "remaining_s": -1}, "음수 시간")):
            raised = False
            try:
                rs.validate_result(bad)
            except ValueError:
                raised = True
            check(f"거부: {why}", raised)

        print("③ dry-run 끝까지")
        r = rs.read_one(img, dry_run=True)
        check("결과에 dry_run 표시 · latency_ms · result", r["result"].get("dry_run") is True and "latency_ms" in r and r["result"]["state"] == "running")
        check("파일명에서 device/state 를 읽었다(채점 경로용)", r["result"]["device"] == "wash")

        print("④ 채점")
        root = td / "labeled"
        for cls in ("wash_idle", "wash_running", "cure_complete"):
            for i in range(2):
                _jpg(root / cls / f"{cls}_{i}.jpg", cls.replace("_", " ").upper())
        s = rs.evaluate(root, dry_run=True, limit_per_class=5, model=rs.MODEL, out=td / "eval.json")
        check("6장 · dry-run 정확도 1.0(채점 경로 검사)", s["n"] == 6 and s["accuracy"] == 1.0)
        check("클래스별 표 3개 · 혼동표 · 저장됨", len(s["per_class"]) == 3 and s["confusion"]["wash_idle"] == {"wash_idle": 2} and (td / "eval.json").exists())
        s4 = rs.evaluate(root, dry_run=True, limit_per_class=5, model=rs.MODEL, out=None, workers=3)
        check("workers=3 도 같은 6장 · 같은 순서", s4["n"] == 6 and [r["file"] for r in s4["rows"]] == [r["file"] for r in s["rows"]])
        check("비용 추정 = 단가표에 있는 모델만 숫자", rs.estimate_cost_usd("gemini-2.5-flash", 1_000_000, 0) == 0.30 and rs.estimate_cost_usd("없는모델", 1, 1) is None)

        print("⑤ 그물")
        (root / "wash_washing").mkdir()
        _jpg(root / "wash_washing" / "wash_washing_0.jpg")
        s2 = rs.evaluate(root, dry_run=True, limit_per_class=5, model=rs.MODEL, out=None)
        check("enum 밖 폴더는 건너뛴다(n 그대로 6)", s2["n"] == 6)
        orig = rs.fake_result
        rs.fake_result = lambda p: {**orig(p), "state": "idle"}      # 전부 idle 로 답하는 가짜
        try:
            s3 = rs.evaluate(root, dry_run=True, limit_per_class=5, model=rs.MODEL, out=None)
        finally:
            rs.fake_result = orig
        check(f"틀린 답이면 정확도가 떨어진다({s3['accuracy']})", s3["accuracy"] < 1.0 and s3["per_class"]["wash_idle"] == "2/2")

        print("⑤' API 실패 1장은 그 장만 실패로 적고 채점이 계속된다(10/22 전수 채점 사망 재발 방지)")
        orig_read = rs.read_one
        def boom(p, **kw):
            if "cure_complete_0" in p.name:
                raise rs.ReadError("JSON 이 아니다(finish=MAX_TOKENS)")
            return orig_read(p, **kw)
        rs.read_one = boom
        try:
            s5 = rs.evaluate(root, dry_run=True, limit_per_class=5, model=rs.MODEL, out=None, workers=2)
        finally:
            rs.read_one = orig_read
        bad = [r for r in s5["rows"] if r.get("api_error")]
        check("n 그대로 6 · api_errors 1 · 그 행은 ok False · pred=api_error", s5["n"] == 6 and s5["api_errors"] == 1 and len(bad) == 1
              and bad[0]["ok"] is False and bad[0]["pred_state"] == "api_error" and "MAX_TOKENS" in bad[0]["reason"])
        check("정확도 5/6 · 혼동표에 api_error 열", s5["per_class"]["cure_complete"] == "1/2" and s5["confusion"]["cure_complete"].get("api_error_api_error") == 1)

        print("⑤'' 재시도·대체 모델 순서(call_gemini_robust · 가짜 call_gemini · sleep 0)")
        calls: list[tuple[str, bool]] = []
        def fake_call(req, *, key):
            m = req["model"]; think = "thinking_config" not in req["generationConfig"]
            calls.append((m, think))
            plan = script.pop(0)
            if plan == "ok":
                return dict(good), {"input_tokens": 1, "output_tokens": 1}
            raise rs.ReadError(plan)
        orig_call = rs.call_gemini; rs.call_gemini = fake_call
        try:
            script = ["API 오류 503: busy", "API 오류 503: busy", "ok"]; calls.clear()
            res, meta = rs.call_gemini_robust(data, media, "A", key="k", sleep=lambda s: None)
            check("503 두 번 → 같은 모델·같은 설정으로 3번째에 성공 · attempts 3", calls == [("A", False)] * 3 and meta["attempts"] == 3 and meta["model_used"] == "A")
            script = ["JSON 이 아니다(finish=MAX_TOKENS)", "ok"]; calls.clear()
            res, meta = rs.call_gemini_robust(data, media, "A", key="k", sleep=lambda s: None)
            check("JSON 깨짐 → 추론 설정 뒤집어 1회 → 성공", calls == [("A", False), ("A", True)] and meta["attempts"] == 2)
            script = ["JSON 이 아니다", "JSON 이 아니다", "ok"]; calls.clear()
            res, meta = rs.call_gemini_robust(data, media, "A", key="k", fallback_model="B", sleep=lambda s: None)
            check("내용 오류 2회 → 대체 모델 B 로 성공 · model_used=B", [c[0] for c in calls] == ["A", "A", "B"] and meta["model_used"] == "B")
            script = ["API 오류 503"] * 3 + ["API 오류 503"] * 3; calls.clear(); raised = None
            try:
                rs.call_gemini_robust(data, media, "A", key="k", fallback_model="B", sleep=lambda s: None)
            except rs.ReadError as e:
                raised = str(e)
            check("503 ×3 + 대체 503 ×3 → 6회 실패로 ReadError", raised is not None and raised.startswith("6회 실패") and len(calls) == 6)
            script = ["API 키가 틀리거나 권한 없음(403)"]; calls.clear(); raised = None
            try:
                rs.call_gemini_robust(data, media, "A", key="k", sleep=lambda s: None)
            except rs.ReadError as e:
                raised = str(e)
            check("403 은 재시도 없이 바로 실패(1회)", raised is not None and len(calls) == 1)
            slept: list[float] = []
            script = ["타임아웃(60s)", "타임아웃(60s)", "ok"]; calls.clear()
            rs.call_gemini_robust(data, media, "A", key="k", sleep=slept.append)
            check("일시 오류 사이 대기 1초·3초", slept == [1.0, 3.0])
        finally:
            rs.call_gemini = orig_call

        print("⑥ MQTT 페이로드")
        tp = rs.to_status_payload(good, camera_id="wash_1", request_id="req-7")
        check("토픽 factory/wash/1/status", tp is not None and tp[0] == "factory/wash/1/status")
        pl = tp[1]
        check("서버 필수 필드 전부 · status=wash_running · device_id int", {"camera_id", "device_type", "device_id", "status", "confidence", "timestamp"} <= set(pl)
              and pl["status"] == "wash_running" and pl["device_id"] == 1 and isinstance(pl["timestamp"], float))
        check("request_id 가 실린다 · 없으면 키 자체가 없다", pl["request_id"] == "req-7" and "request_id" not in rs.to_status_payload(good, camera_id="wash_1")[1])
        check("error → status 'error'(서버 enum)", rs.to_status_payload({**good, "state": "error"}, camera_id="cure_2")[1]["status"] == "error")
        check("unknown / printer 는 발행 안 함(None)", rs.to_status_payload({**good, "state": "unknown"}, camera_id="wash_1") is None
              and rs.to_status_payload({**good, "device": "printer"}, camera_id="wash_1") is None)
        check("페이로드가 JSON 직렬화된다", json.loads(json.dumps(pl))["status"] == "wash_running")

    print("  ✅ 통과" if OK else "  🔴 실패")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
