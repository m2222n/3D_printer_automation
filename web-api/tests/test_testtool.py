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


TEST_DATA = WEB_API_ROOT / "app" / "testtool" / "test_data_261020" / "events.json"
TEST_DATA_SHA256 = "633642F9F94542862911E3E88510F8FB323EF7B1A3E0710150734E19DDBD95DA"


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


# ===== 10/19 요청번호(request_id) 1:1 대응 — 시험기관 지적("요청과 웹소켓 응답이 1:1 이라는 근거") =====

def test_vision_ws_echoes_request_id(monkeypatch):
    """셀A: 측정 도구가 붙인 요청번호가 MQTT 메시지를 거쳐 화면(WS) 메시지에 그대로 돌아온다.
    실제 카메라 메시지(요청번호 없음)는 None — 운영 동작 불변."""
    import asyncio
    from app.local.database import init_local_db
    from app.vision import camera_manager as cm
    from app.vision.schemas import MQTTStatusMessage

    init_local_db()
    m = cm.get_camera_manager()
    sent = []

    async def capture(message):
        sent.append(message)
    monkeypatch.setattr(m, "_broadcast_ws", capture)
    asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="cure_2", device_type="cure", device_id=2, status="cure_idle", timestamp=0.0)))
    asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="cure_2", device_type="cure", device_id=2, status="cure_running", timestamp=0.0,
                                                  request_id="R20261019-000000-007")))
    asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="cure_2", device_type="cure", device_id=2, status="cure_complete", timestamp=0.0)))
    changes = [x["data"] for x in sent if x["type"] == "vision_status_change"]
    assert changes[-2]["status"] == "cure_running" and changes[-2]["request_id"] == "R20261019-000000-007"
    assert changes[-1]["status"] == "cure_complete" and changes[-1]["request_id"] is None


def test_simulate_payload_carries_request_id(monkeypatch):
    """시뮬레이터 API → MQTT 발행 payload 에 요청번호가 실린다(없으면 키 자체가 없다)."""
    import asyncio
    from app.vision import simulator

    published = []

    class FakeMqtt:
        async def publish(self, topic, payload, qos=1):
            published.append(payload)
    monkeypatch.setattr(simulator, "get_mqtt_client", lambda: FakeMqtt())
    asyncio.run(simulator.publish_simulated_status("wash_1", "wash_running", request_id="R-1"))
    asyncio.run(simulator.publish_simulated_status("wash_1", "wash_complete"))
    assert published[0]["request_id"] == "R-1"
    assert "request_id" not in published[1]


def test_binpick_ws_echoes_request_id(client, auth_headers, monkeypatch):
    """셀B: 인식 결과 보고에 붙인 요청번호가 화면(WS) 메시지에 그대로 돌아온다 · 실제 모듈 보고(없음)는 None."""
    import json
    from app.local.database import init_local_db
    from app.binpick import routes as br

    init_local_db()
    sent = []

    async def capture(message):
        sent.append(message)
    monkeypatch.setattr(br, "_broadcast_ws", capture)
    events = json.loads(TEST_DATA.read_text(encoding="utf-8"))["events"]
    rep = next(x for x in events if x["cell"] == "B")["report"]
    r = client.post("/api/v1/binpick/reports", json={**rep, "scene_id": "rid_test_1", "request_id": "R20261019-000000-003"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/binpick/reports", json={**rep, "scene_id": "rid_test_2"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    scenes = [x for x in sent if x["type"] == "binpick_scene"]
    assert scenes[-2]["scene_id"] == "rid_test_1" and scenes[-2]["request_id"] == "R20261019-000000-003"
    assert scenes[-1]["request_id"] is None


def test_latency_page_matches_only_by_request_id():
    """측정 페이지가 내용(설비+상태)이 아니라 요청번호로만 대응하는지 — 옛 내용 키가 남아 있으면 실패."""
    html = (Path(__file__).resolve().parents[1] / "app" / "testtool" / "latency.html").read_text(encoding="utf-8")
    assert "resolvePending(m.data.request_id" in html and "resolvePending(m.request_id" in html
    assert '"v:" + m.data.camera_id' not in html and '"b:" + m.scene_id' not in html
    assert "publish(ev, key)" in html and "body.request_id = request_id" in html and "{ ...report, request_id }" in html


def test_cert_evidence_lines_server_side(client, auth_headers, caplog):
    """10/20 시험 증적: 요청번호가 있는 요청은 서버 로그에 REQ_IN·WS_OUT(셀B)과
    WS_OUT·NO_CHANGE(셀A) 줄을 남기고, 요청번호가 없는 운영 호출은 아무것도 남기지 않는다."""
    import asyncio, json, logging
    from app.local.database import init_local_db
    from app.vision.camera_manager import get_camera_manager
    from app.vision.schemas import MQTTStatusMessage

    init_local_db()
    caplog.set_level(logging.INFO, logger="cert.evidence")

    # 셀B — 실제 수신 경로
    e = next(x for x in json.loads(TEST_DATA.read_text(encoding="utf-8"))["events"] if x["cell"] == "B")
    rep = dict(e["report"], request_id="R-TEST-B-001", scene_id=e["scene_id"] + "_ev")
    assert client.post("/api/v1/binpick/reports", json=rep, headers=auth_headers).status_code == 201
    # 셀A — MQTT 수신 처리(handle_status)를 직접 호출: 변경 1회 → WS_OUT, 같은 상태 재수신 → NO_CHANGE
    m = get_camera_manager()
    for st in ("wash_idle", "wash_running", "wash_running"):
        asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="wash_2", device_type="wash", device_id=2,
                                                      status=st, confidence=0.9, timestamp=0.0, request_id="R-TEST-A-" + st)))
    # 요청번호 없는 운영 호출 — 증적 0
    asyncio.run(m.handle_status(MQTTStatusMessage(camera_id="wash_2", device_type="wash", device_id=2,
                                                  status="wash_complete", confidence=0.9, timestamp=0.0)))

    lines = [r.getMessage() for r in caplog.records if r.name == "cert.evidence"]
    assert any("stage=REQ_IN cell=B rid=R-TEST-B-001" in l for l in lines), lines
    assert any("stage=WS_OUT cell=B rid=R-TEST-B-001" in l for l in lines), lines
    assert any("stage=WS_OUT cell=A rid=R-TEST-A-wash_running target=wash_2 value=wash_running" in l for l in lines), lines
    assert any("stage=NO_CHANGE cell=A rid=R-TEST-A-wash_running" in l for l in lines), lines
    assert all("rid=None" not in l and "wash_complete" not in l for l in lines), lines
    assert all(l.startswith("CERT ") and "+09:00" in l for l in lines), lines
