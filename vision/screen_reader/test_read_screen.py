"""read_screen 검증 — 네트워크·키 없이 도는 부분 전부 (실행: python vision/screen_reader/test_read_screen.py)

① 요청 본문 = 이미지가 base64 로 들어가고 스키마가 output_config 에 실린다(SDK 호출 모양 · 키 이름)
② validate_result 가 조용히 틀린 값을 막는다(enum 밖 · 키 누락 · 범위)
③ dry-run 이 파일 → 결과 JSON 까지 끝까지 돈다 · dry_run 표시가 붙는다
④ 채점(evaluate) 이 라벨 폴더를 읽고 정확도를 낸다(dry-run 으로 100% = 채점 경로 자체의 검사이지 성능이 아니다)
⑤ 🧪 그물: 폴더명을 enum 밖으로 바꾸면 건너뛰고, 가짜 응답의 state 를 틀리게 하면 정확도가 떨어진다
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
        check("model · max_tokens · system 이 있다", req["model"] == rs.MODEL and req["max_tokens"] > 0 and "Form Wash" in req["system"])
        check("첫 블록이 image/base64/jpeg", c[0]["type"] == "image" and c[0]["source"]["type"] == "base64" and c[0]["source"]["media_type"] == "image/jpeg")
        check("base64 가 원본 바이트를 복원한다", __import__("base64").b64decode(c[0]["source"]["data"]) == data)
        check("스키마가 output_config.format.json_schema 에", req["output_config"]["format"]["type"] == "json_schema" and req["output_config"]["format"]["schema"] is rs.SCHEMA)
        check("스키마 additionalProperties False · required 7", rs.SCHEMA["additionalProperties"] is False and len(rs.SCHEMA["required"]) == 7)

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
        check("클래스별 표 3개 · 저장됨", len(s["per_class"]) == 3 and (td / "eval.json").exists())

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

    print("  ✅ 통과" if OK else "  🔴 실패")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
