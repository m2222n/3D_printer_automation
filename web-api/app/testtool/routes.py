"""
시험 도구 페이지
================
KTR SW 성능 시험(정량목표 2 · 통합 모니터링 응답속도 3초)용 측정 페이지를 서버 안에서 제공한다.

- GET /test/latency : 모니터링 응답시간 측정 페이지(정적 HTML 1장, 외부 의존 0)
  · 페이지 자체는 /api/ 밖이라 JWT 검사 대상이 아니다(인증 토글과 무관하게 열린다)
  · 페이지가 부르는 API(/api/v1/vision/simulate · /devices · WS /api/v1/vision/ws)는 평소대로 보호된다
    — 시험 서버 브라우저(localhost)는 loopback 면제, 원격이면 페이지의 로그인으로 토큰을 받는다
- 시험 방식은 2026-02 KTR 의뢰(ITTR) 때와 같다: 의뢰자가 만든 도구 페이지에 시험기관이 접속해 수행
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(prefix="/test", tags=["Test Tool"], include_in_schema=False)

_HERE = Path(__file__).resolve().parent
LATENCY_PAGE = _HERE / "latency.html"


@router.get("/latency")
async def latency_page():
    """모니터링 응답시간 측정 페이지"""
    return FileResponse(LATENCY_PAGE, media_type="text/html; charset=utf-8")
