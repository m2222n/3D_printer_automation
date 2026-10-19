"""
web-api 기동 스크립트 — Windows 에서 MQTT 가 돌 수 있는 이벤트 루프로 uvicorn 을 띄운다 (2026-10-19)

🎯 왜 있는가
  Windows 파이썬의 기본 루프(Proactor)는 `loop.add_reader/add_writer` 를 지원하지 않는데,
  MQTT 라이브러리(aiomqtt → paho)가 그것을 쓴다. 그래서 공장 PC 에서
    · 구독 = `MQTT 연결 끊김: Operation timed out` 5초마다 (TCP 는 붙는데 읽기 루프가 못 돈다)
    · 발행 = `POST /api/v1/vision/simulate` → NotImplementedError → HTTP 500
  이 났다(10/19 공장 PC 실측 · 10/13 리눅스 6000 리허설에선 안 보임).
  uvicorn 0.30+ 은 `Server.run()` 안에서 자기 loop_factory(Windows = Proactor)로 루프를 만들기 때문에
  앱 코드에서 정책을 바꿔도 늦고(`-m uvicorn` 은 루프를 만든 뒤 앱을 import 한다), 정책 자체도 무시된다.
  ⇒ 우리가 **Selector 루프를 직접 만들어 `Server.serve()` 를 그 위에서** 돌린다. uvicorn 버전과 무관.

사용
  python serve.py --host 0.0.0.0 --port 8085          # main.py(NSSM 런처)가 Windows 에서 이렇게 부른다
  FORCE_SELECTOR_LOOP=1 python serve.py --port 8087   # 리눅스에서 Windows 경로를 그대로 시험할 때

주의
  · Selector 루프는 asyncio 서브프로세스를 못 만든다 — web-api 는 안 쓴다(10/19 grep 0건). sequence_service 는 별도 프로세스라 무관.
  · 리눅스(6000·카카오)는 systemd 가 uvicorn 을 직접 띄우므로 이 파일을 거치지 않는다(기본 루프가 이미 Selector).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _need_selector_loop() -> bool:
    return sys.platform == "win32" or os.getenv("FORCE_SELECTOR_LOOP") == "1"


def main() -> int:
    ap = argparse.ArgumentParser(description="web-api 기동 (Windows: Selector 이벤트 루프)")
    ap.add_argument("--host", default=os.getenv("WEB_API_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.getenv("WEB_API_PORT", "8085")))
    ap.add_argument("--log-level", default="info")
    args = ap.parse_args()

    import uvicorn

    config = uvicorn.Config("app.main:app", host=args.host, port=args.port, log_level=args.log_level)
    server = uvicorn.Server(config)

    if not _need_selector_loop():
        server.run()
        return 0

    print(f"[serve] Selector 이벤트 루프로 기동 (platform={sys.platform} · MQTT add_reader 지원)", flush=True)
    if sys.version_info >= (3, 11):
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:  # 3.10 이하 — 정책으로만 가능
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        asyncio.run(server.serve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
