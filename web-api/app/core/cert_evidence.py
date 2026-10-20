"""
시험 증적 로그 — 요청번호(request_id)를 서버 쪽에도 남긴다
==========================================================
SW 성능 시험에서 응답시간·일치 여부는 측정 페이지(브라우저)가 기록한다. 이 모듈은
**같은 요청번호가 서버를 언제 지나갔는지**를 서버 로그에 한 줄씩 남겨, 시험기관이
브라우저 CSV 와 서버 기록을 서로 대조할 수 있게 한다.

- request_id 가 없는 호출(실제 카메라·실제 빈피킹 모듈)은 아무것도 남기지 않는다 → 운영 영향 0
- 단계(stage)
    REQ_IN   = 서버가 발행 요청을 받은 시각
    NO_CHANGE = 셀A 상태가 바뀌지 않아 화면 전송을 하지 않은 경우(시험 데이터 규칙 위반 탐지용)
    WS_OUT   = 서버가 화면(WebSocket)으로 보낸 시각
- 형식(한 줄 · grep "CERT " 으로 추출)
    CERT stage=WS_OUT cell=A rid=R20261020-190501-007 target=wash_1 value=wash_running t=2026-10-20T19:05:01.123+09:00
- 환경변수 CERT_EVIDENCE_LOG 에 파일 경로를 주면 그 파일에도 같은 줄을 쓴다(시험 인스턴스 전용)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

KST = timezone(timedelta(hours=9))

logger = logging.getLogger("cert.evidence")

_path = os.environ.get("CERT_EVIDENCE_LOG", "").strip()
if _path and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    _fh = logging.FileHandler(_path, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.INFO)


def format_line(stage: str, cell: str, rid: str, target: str, value: str,
                at: Optional[datetime] = None) -> str:
    t = (at or datetime.now(KST)).astimezone(KST).isoformat(timespec="milliseconds")
    return f"CERT stage={stage} cell={cell} rid={rid} target={target} value={value} t={t}"


def evidence(stage: str, cell: str, rid: Optional[str], target: str, value: str) -> None:
    """request_id 가 있을 때만 증적 한 줄을 남긴다."""
    if not rid:
        return
    logger.info(format_line(stage, cell, rid, target, value))
