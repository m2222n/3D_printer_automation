"""
시험 도구 페이지(/test/latency) 계약 테스트
==========================================
KTR 성능 시험 때 시험기관이 여는 페이지라, 다음이 깨지면 시험 당일에 발견된다:
① 인증이 켜져 있어도 토큰 없이 열린다(/api/ 밖 경로)
② 페이지가 부르는 서버 경로가 실제 라우터와 일치한다(문자열 하드코딩 → 라우터 변경 시 조용히 어긋남)
③ 페이지가 받는 WebSocket 메시지 타입이 서버가 보내는 것과 같다
"""

from pathlib import Path

WEB_API_ROOT = Path(__file__).resolve().parent.parent


def test_latency_page_served_without_token(client):
    r = client.get("/test/latency")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "모니터링 응답시간 측정" in r.text


def test_latency_page_targets_real_routes(client):
    """페이지의 하드코딩 경로가 서버 라우터에 실제로 있는지 — 라우터를 옮기면 여기서 잡힌다."""
    html = client.get("/test/latency").text
    paths = {route.path for route in client.app.routes}
    for p in ("/api/v1/vision/simulate", "/api/v1/vision/devices", "/api/v1/vision/ws", "/api/v1/auth/login",
              "/api/v1/vision/events", "/api/v1/dashboard"):
        assert p in html, f"페이지가 {p} 를 부르지 않는다"
        assert p in paths, f"서버에 {p} 라우트가 없다"


def test_t3_query_apis_respond_200(client, auth_headers):
    """시험항목 2 대상 조회 API 2종(설비·이벤트)이 비어 있는 서버에서도 200 — 대시보드는 Formlabs 데이터 전이라 503 허용.
    원격 접속(비 loopback)은 토큰이 있어야 한다 = 페이지의 로그인 흐름이 필요한 이유."""
    for p in ("/api/v1/vision/devices", "/api/v1/vision/events?page=1&page_size=50"):
        assert client.get(p).status_code == 401, f"{p} 가 토큰 없이 열리면 안 된다"
        r = client.get(p, headers=auth_headers)
        assert r.status_code == 200, p
    r = client.get("/api/v1/dashboard", headers=auth_headers)
    assert r.status_code in (200, 503), r.status_code


def test_latency_page_ws_message_type_matches_server():
    """camera_manager 가 보내는 WS 타입 문자열과 페이지가 거르는 타입이 같아야 한다."""
    html = (WEB_API_ROOT / "app" / "testtool" / "latency.html").read_text(encoding="utf-8")
    manager_src = (WEB_API_ROOT / "app" / "vision" / "camera_manager.py").read_text(encoding="utf-8")
    assert '"vision_status_change"' in manager_src
    assert 'vision_status_change' in html


def test_latency_page_simulator_cameras_match_server():
    """페이지의 카메라 4대·상태 값이 서버 시뮬레이터 CAMERA_MAP·DeviceStatus 와 같아야 한다."""
    from app.vision.simulator import CAMERA_MAP
    from app.vision.schemas import DeviceStatus

    html = (WEB_API_ROOT / "app" / "testtool" / "latency.html").read_text(encoding="utf-8")
    for cam in CAMERA_MAP:
        assert cam in html, f"페이지에 카메라 {cam} 없음"
    for st in ("wash_idle", "wash_running", "wash_complete", "cure_idle", "cure_running", "cure_complete"):
        assert st in html
        assert st in {s.value for s in DeviceStatus}
