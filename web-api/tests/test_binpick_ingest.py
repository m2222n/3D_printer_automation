"""빈피킹 수신 라우터 계약 테스트 (2026-08-13 신설)

⭐⭐ **이 테스트의 핵심 = 손으로 만든 dict를 쓰지 않는다.**
8/7에 게이트 키를 `valid_pct`로 추측해서 틀렸는데 **테스트가 통과했다.**
이유는 *"손으로 만든 가짜 dict가 코드와 같은 오타를 공유"* 했기 때문이다.
⇒ 그래서 여기서는 **진짜 `build_bin_picking_payload()`를 import해서 돌리고**
   그 출력을 그대로 POST한다. 모듈과 서버의 키 이름이 어긋나면 여기서 깨진다.

🚨 이 파일이 잠그는 계약 = **모듈이 만든 payload를 서버가 손실 없이 저장한다.**
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# bin_picking 모듈(송신부)을 import 경로에 올린다 — 진짜 payload 생성기를 쓰기 위해.
REPO_ROOT = Path(__file__).resolve().parents[2]
BIN_PICKING = REPO_ROOT / "bin_picking"
if str(BIN_PICKING) not in sys.path:
    sys.path.insert(0, str(BIN_PICKING))


@pytest.fixture(scope="module")
def real_payload_builder():
    """실제 송신부의 payload 빌더. 없으면 테스트를 건너뛴다(경로 문제와 구분)."""
    try:
        from src.communication.web_reporter import build_bin_picking_payload
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"web_reporter를 import할 수 없음: {exc}")
    return build_bin_picking_payload


@pytest.fixture
def six_like():
    """6요소 결과 형태. ⭐ 게이트 키는 `input_gate.check_scene()` 반환을 따른다.

    🚨 여기서도 키를 추측하면 안 되므로, 게이트 관련 키 이름은
       `_scene_verdict()`가 읽는 것과 같은 이름을 쓴다(`gate_summary`/`gate_scene`).
    """
    return {
        "scene_id": "c1_shot_007",
        "recognition_track": "depth_track",
        "gate_summary": {"scene_verdict": "in_distribution", "n_dropped": 2},
        "gate_scene": {
            "trusted": True,
            "valid_ratio_pct": 5.55,
            "note": "학습 분포 안",
        },
        "detections": [
            {"x": 320.5, "y": 210.0, "z": 452.1, "angle": 37.4,
             "label": "01_sol_block_a", "confidence": 0.81,
             "edge": [[1, 2], [3, 4], [5, 6], [7, 8]],
             "camera_3d": {"Xc": -109.4, "Yc": 12.0, "Zc": 452.1}},
            {"x": 180.0, "y": 300.2, "z": 461.7, "angle": 112.9,
             "label": "18_button", "confidence": 0.74,
             "edge": [[1, 2], [3, 4], [5, 6], [7, 8]],
             "camera_3d": {"Xc": 40.1, "Yc": -8.3, "Zc": 461.7}},
        ],
    }


@pytest.fixture
def client():
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def _post(client, payload):
    """loopback 인증 면제를 타고 들어간다(TestClient는 client host가 testclient라
    면제 대상이 아니므로, 인증이 켜져 있으면 토큰을 붙인다)."""
    from tests.conftest import TEST_USERNAME, TEST_PASSWORD
    r = client.post("/api/v1/auth/login",
                    json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    headers = {}
    if r.status_code == 200:
        headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return client.post("/api/v1/binpick/reports", json=payload, headers=headers)


def _auth_headers(client):
    from tests.conftest import TEST_USERNAME, TEST_PASSWORD
    r = client.post("/api/v1/auth/login",
                    json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    if r.status_code == 200:
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return {}


# ===== ⭐ 진짜 송신부와의 교차 검증 =====

def test_real_payload_is_accepted_without_loss(client, real_payload_builder, six_like):
    """⭐⭐ 모듈이 만든 payload를 서버가 그대로 받아 저장하는가.

    이 테스트가 8/7 유형의 버그(키 이름 어긋남)를 잡는 그물이다.
    """
    payload = real_payload_builder(six_like, latency_ms=2670.4)

    resp = _post(client, payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["n_detections_stored"] == 2
    assert body["scene_id"] == "c1_shot_007"
    # 🚨 게이트 판정이 살아서 도착했는가 (not_checked로 떨어지지 않았는가)
    assert body["gate_verdict"] == "in_distribution"
    assert body["warnings"] == [], f"불일치 경고가 있으면 안 된다: {body['warnings']}"

    # 상세 조회로 유효율까지 왕복 확인 — ⭐ 8/7엔 이 값이 조용히 None이 됐다.
    detail = client.get(f"/api/v1/binpick/scenes/{body['scene_pk']}",
                        headers=_auth_headers(client))
    assert detail.status_code == 200
    d = detail.json()
    assert d["scene_gate"]["valid_ratio_pct"] == pytest.approx(5.55)
    assert d["scene_gate"]["trusted"] is True
    assert d["scene_gate"]["n_dropped_by_size_gate"] == 2
    assert d["latency_ms"] == pytest.approx(2670.4)
    assert d["recognition_track"] == "depth_track"


def test_gate_keys_match_sender_exactly(real_payload_builder, six_like):
    """⭐ 송신부가 내는 게이트 키 이름과 수신 스키마 필드가 일치하는가.

    🚨 8/7 교훈 = 키를 추측하면 조용히 None이 된다. 이름 집합을 직접 대조한다.
    """
    from app.binpick.schemas import SceneGateIn

    payload = real_payload_builder(six_like)
    sent_keys = set(payload["scene_gate"].keys())
    schema_keys = set(SceneGateIn.model_fields.keys())

    missing = sent_keys - schema_keys
    assert not missing, (
        f"송신부가 보내는데 수신 스키마에 없는 게이트 키: {missing} "
        f"— 이 필드는 조용히 버려진다")


def test_detection_fields_match_sender(real_payload_builder, six_like):
    """검출 필드도 같은 방식으로 대조한다."""
    from app.binpick.schemas import DetectionIn

    payload = real_payload_builder(six_like)
    sent_keys = set(payload["detections"][0].keys())
    schema_keys = set(DetectionIn.model_fields.keys())

    missing = sent_keys - schema_keys
    assert not missing, f"수신 스키마에 없는 검출 키: {missing}"


def test_robot_only_fields_are_not_sent(real_payload_builder, six_like):
    """⭐ 설계원칙 2 회귀 검사 — `edge`·`camera_3d`가 웹으로 흘러가지 않는가.

    six_like에는 둘 다 들어 있는데 payload에는 없어야 한다.
    """
    payload = real_payload_builder(six_like)
    for det in payload["detections"]:
        assert "edge" not in det
        assert "camera_3d" not in det


# ===== 불일치·미실행 게이트 처리 =====

def test_count_mismatch_is_accepted_with_warning(client, real_payload_builder, six_like):
    """⭐ summary와 실제 길이가 어긋나면 **받아들이고 경고**한다.

    거부하면 데이터를 잃고, 조용히 넘기면 그럴싸한 값이 굳는다.
    """
    payload = real_payload_builder(six_like)
    payload["summary"]["n_detections"] = 99  # 모듈 버그를 흉내낸다

    resp = _post(client, payload)
    assert resp.status_code == 201
    body = resp.json()

    assert body["n_detections_stored"] == 2, "실제 길이를 저장해야 한다"
    assert any("99" in w for w in body["warnings"]), body["warnings"]


def test_not_checked_gate_is_flagged(client):
    """🚨 게이트 미실행을 "통과"로 저장하지 않는가.

    판정이 없는 것과 판정이 통과인 것은 다르다.
    """
    payload = {
        "schema_version": "1.0.0",
        "module": "bin_picking",
        "scene_id": "no_gate_scene",
        "timestamp": "2026-08-13T10:00:00",
        "summary": {"n_detections": 0, "n_unique_labels": 0},
        "scene_gate": {"verdict": "not_checked"},
        "detections": [],
    }
    resp = _post(client, payload)
    assert resp.status_code == 201
    body = resp.json()

    assert body["gate_verdict"] == "not_checked"
    assert any("not_checked" in w for w in body["warnings"]), body["warnings"]


def test_unknown_extra_fields_do_not_break_ingest(client):
    """⭐ 설계원칙 1 — 모듈이 필드를 더 보내도 수신이 깨지지 않는다."""
    payload = {
        "schema_version": "1.1.0",
        "module": "bin_picking",
        "scene_id": "future_scene",
        "timestamp": "2026-08-13T10:00:00",
        "summary": {"n_detections": 1, "n_unique_labels": 1,
                    "brand_new_metric": 42},
        "scene_gate": {"verdict": "in_distribution", "trusted": True,
                       "valid_ratio_pct": 4.2, "some_new_gate": "x"},
        "detections": [{"x": 1.0, "y": 2.0, "z": 450.0, "angle": 10.0,
                        "label": "main_body", "confidence": 0.9,
                        "unheard_of_field": True}],
        "top_level_novelty": {"a": 1},
    }
    resp = _post(client, payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["n_detections_stored"] == 1


# ===== 조회 =====

def test_latest_scene_returns_null_when_empty_not_404(client):
    """⚠️ 아직 안 온 것은 오류가 아니다."""
    resp = client.get("/api/v1/binpick/scenes/latest", headers=_auth_headers(client))
    assert resp.status_code == 200
    # 다른 테스트가 먼저 넣었을 수 있으므로 null 또는 정상 객체 둘 다 허용
    assert resp.json() is None or "scene_pk" in resp.json()


def test_scene_list_and_gate_filter(client, real_payload_builder, six_like):
    """게이트 판정으로 필터가 되는가 — c3 같은 장면을 골라낼 수 있어야 한다."""
    good = real_payload_builder(six_like)
    good["scene_id"] = "gate_ok"
    _post(client, good)

    bad_six = dict(six_like)
    bad_six["scene_id"] = "gate_bad"
    bad_six["gate_summary"] = {"scene_verdict": "out_of_distribution", "n_dropped": 9}
    bad_six["gate_scene"] = {"trusted": False, "valid_ratio_pct": 89.1,
                             "note": "유효율 상한 초과"}
    _post(client, real_payload_builder(bad_six))

    headers = _auth_headers(client)
    resp = client.get("/api/v1/binpick/scenes",
                      params={"gate_verdict": "out_of_distribution"},
                      headers=headers)
    assert resp.status_code == 200
    scenes = resp.json()["scenes"]
    assert scenes, "out_of_distribution 장면이 조회돼야 한다"
    assert all(s["scene_gate"]["verdict"] == "out_of_distribution" for s in scenes)

    # trusted_only는 그 장면을 빼야 한다
    resp2 = client.get("/api/v1/binpick/scenes",
                       params={"trusted_only": True}, headers=headers)
    ids = [s["scene_id"] for s in resp2.json()["scenes"]]
    assert "gate_bad" not in ids


def test_detection_order_is_preserved(client, real_payload_builder, six_like):
    """⭐ idx 순서 = grasp_plan 인덱스 대응이 계약이다.

    🚨 순서가 섞이면 엉뚱한 부품의 벌림을 보고하게 된다(8/5 원칙).
    """
    payload = real_payload_builder(six_like)
    payload["scene_id"] = "order_check"
    resp = _post(client, payload)
    pk = resp.json()["scene_pk"]

    detail = client.get(f"/api/v1/binpick/scenes/{pk}", headers=_auth_headers(client))
    dets = detail.json()["detections"]
    assert [d["idx"] for d in dets] == [0, 1]
    assert dets[0]["label"] == "01_sol_block_a"
    assert dets[1]["label"] == "18_button"


def test_health_counts_untrusted(client, real_payload_builder, six_like):
    """⭐ 게이트가 못 믿겠다고 한 장면이 쌓이면 보이는가."""
    bad = dict(six_like)
    bad["scene_id"] = "health_bad"
    bad["gate_summary"] = {"scene_verdict": "out_of_distribution", "n_dropped": 4}
    bad["gate_scene"] = {"trusted": False, "valid_ratio_pct": 94.7, "note": "이탈"}
    _post(client, real_payload_builder(bad))

    resp = client.get("/api/v1/binpick/health", headers=_auth_headers(client))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["scenes_total"] >= 1
    assert body["scenes_untrusted"] >= 1


def test_missing_scene_returns_404(client):
    resp = client.get("/api/v1/binpick/scenes/does-not-exist",
                      headers=_auth_headers(client))
    assert resp.status_code == 404
