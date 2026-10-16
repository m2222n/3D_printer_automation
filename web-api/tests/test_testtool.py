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
              "/api/v1/vision/events", "/api/v1/dashboard",
              "/api/v1/binpick/reports", "/api/v1/binpick/ws"):          # 셀B 빈피킹 경로(10/16 통합)
        assert p in html, f"페이지가 {p} 를 부르지 않는다"
        assert p in paths, f"서버에 {p} 라우트가 없다"


TEST_DATA = WEB_API_ROOT / "app" / "testtool" / "test_data_261016" / "events.json"
TEST_DATA_SHA256 = "D87C093EEEB7C63D7D219D2B3CB9FD8C55FCE658427696C9FF11314CC14E5BE6"


def test_events_test_data_locked():
    """시험항목 1 시험데이터(events.json · 셀A 18 + 셀B 12)는 규격서에 해시로 박히는 파일이다.
    ① 셀A: 서버 카메라·상태 정의와 일치 · 같은 설비의 연속 이벤트는 상태가 바뀜(서버는 변경만 전송) · 끝 상태 전부 idle(재실행 가능)
    ② 셀B: report 가 서버 수신 스키마(BinPickReportIn)로 그대로 파싱됨 · scene_id 고유 · 검출 ≥ 1
    ③ 해시 고정 — 바꾸려면 규격서도 같이."""
    import hashlib, json
    from app.binpick.schemas import BinPickReportIn
    from app.vision.simulator import CAMERA_MAP
    from app.vision.schemas import DeviceStatus

    raw = TEST_DATA.read_bytes()
    assert hashlib.sha256(raw).hexdigest().upper() == TEST_DATA_SHA256
    doc = json.loads(raw)
    events = doc["events"]
    assert [e["seq"] for e in events] == list(range(1, 31))
    cells = [e["cell"] for e in events]
    assert cells.count("A") == 18 and cells.count("B") == 12 == doc["counts"]["cell_b_binpick"]
    assert cells[:5] == ["A", "A", "B", "A", "B"], "순서 패턴 [A,A,B,A,B]"

    valid = {s.value for s in DeviceStatus}
    state = {c: f'{v["device_type"]}_idle' for c, v in CAMERA_MAP.items()}
    scenes: set[str] = set()
    for e in events:
        if e["cell"] == "A":
            assert e["kind"] == "vision" and e["camera_id"] in CAMERA_MAP
            assert e["status"] in valid and e["status"].startswith(CAMERA_MAP[e["camera_id"]]["device_type"] + "_")
            assert state[e["camera_id"]] != e["status"], f"변경 아님: {e}"
            state[e["camera_id"]] = e["status"]
        else:
            assert e["kind"] == "binpick"
            report = BinPickReportIn.model_validate(e["report"])       # 서버가 받는 스키마 그대로
            assert report.scene_id == e["scene_id"] and e["scene_id"] not in scenes
            scenes.add(e["scene_id"])
            assert len(report.detections) >= 1 and report.summary.n_detections == len(report.detections)
            assert report.scene_gate.verdict != "not_checked", "실물 결과는 게이트 판정이 있어야 한다"
    assert all(st.endswith("_idle") for st in state.values()), f"끝 상태가 idle 이 아님: {state}"


def test_cell_b_reports_ingest_201(client, auth_headers):
    """시험데이터의 셀B report 12건이 실제 수신 경로(POST /api/v1/binpick/reports)에서 201 로 저장되는지 —
    페이지는 이 응답과 무관하게 WS 로 수신을 재지만, 저장이 실패하면 WS 전송도 없다."""
    import json
    from app.local.database import init_local_db

    init_local_db()
    events = json.loads(TEST_DATA.read_text(encoding="utf-8"))["events"]
    for e in (x for x in events if x["cell"] == "B"):
        r = client.post("/api/v1/binpick/reports", json=e["report"], headers=auth_headers)
        assert r.status_code == 201, (e["scene_id"], r.text)
        body = r.json()
        assert body["scene_id"] == e["scene_id"] and body["n_detections_stored"] == len(e["report"]["detections"])


def test_devices_api_ok_after_status_change(client, auth_headers):
    """10/13 리허설에서 잡힌 500: 상태 변경이 한 번이라도 있으면 /vision/devices 가 터졌다
    (SQLite 가 tz 를 버려 naive 로 돌아온 last_status_change 를 aware now 와 뺌).
    MQTT 없이 camera_manager.handle_status 를 직접 불러 재현 → 200 + elapsed 정수."""
    import asyncio
    from app.local.database import init_local_db
    from app.vision.camera_manager import get_camera_manager
    from app.vision.schemas import MQTTStatusMessage

    init_local_db()
    m = get_camera_manager()
    for st in ("wash_idle", "wash_running"):
        asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="wash_1", device_type="wash", device_id=1, status=st, confidence=0.9, timestamp=0.0)))
    r = client.get("/api/v1/vision/devices", headers=auth_headers)
    assert r.status_code == 200, r.text
    d = next(x for x in r.json()["devices"] if x["camera_id"] == "wash_1")
    assert d["status"] == "wash_running" and isinstance(d["elapsed_since_change_s"], int) and d["elapsed_since_change_s"] >= 0
    r = client.get("/api/v1/vision/devices/wash/1", headers=auth_headers)
    assert r.status_code == 200, r.text


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
    binpick_src = (WEB_API_ROOT / "app" / "binpick" / "routes.py").read_text(encoding="utf-8")
    assert '"vision_status_change"' in manager_src
    assert 'vision_status_change' in html
    assert '"binpick_scene"' in binpick_src and '"scene_id"' in binpick_src   # 셀B 채널: 타입 + 매칭 키
    assert 'binpick_scene' in html


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
