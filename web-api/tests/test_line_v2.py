"""라인 MES v2 (/api/v2) 계약 — R4.

- LINE_DSN 이 비어 있으면 503 LINE_MES_OFF (FE 가 이걸로 v2 탭을 끈다). PG 없이 돈다.
- LINE_DSN 이 주어지면(개발 DB) 실제 행 구조를 본다. 없으면 skip.
"""
import os

import pytest


@pytest.fixture
def v2_client(settings):
    from app.line import db
    from app.main import create_app
    from fastapi.testclient import TestClient
    db._pool = None                      # 이전 테스트가 연 풀을 버린다
    return TestClient(create_app())


def test_r4_is_503_when_line_mes_off(v2_client, settings, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "LINE_DSN", "")
    r = v2_client.get("/api/v2/lines/RESIN-1-ASIS/control-menu", headers=auth_headers)
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["code"] == "LINE_MES_OFF"


def test_r4_requires_jwt_even_from_loopback(v2_client):
    # v2 는 loopback 면제 대상이 아니다(/api/v1/ 만) — 토큰 없으면 401
    r = v2_client.get("/api/v2/lines/RESIN-1-ASIS/control-menu")
    assert r.status_code == 401, r.text


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_r4_rows_from_dev_db(v2_client, settings, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    r = v2_client.get(f"/api/v2/lines/{settings.LINE_ID}/control-menu", headers=auth_headers)
    assert r.status_code == 200, r.text
    menu = r.json()["menu"]
    assert menu and all(m["node_count"] == len(m["node_ids"]) for m in menu)
    assert [m["step_order"] for m in menu] == sorted(m["step_order"] for m in menu)
    r2 = v2_client.get("/api/v2/lines/NOPE/control-menu", headers=auth_headers)
    assert r2.status_code == 404 and r2.json()["detail"]["code"] == "LINE_NOT_FOUND"


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_p1_reads_from_dev_db(v2_client, settings, auth_headers, monkeypatch):
    """R2 R11 R1 R3 R5 — 응답이 FE 계약(types/line.ts) 모양인지. 값은 DB 상태에 따라 다르므로 구조만."""
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    L = settings.LINE_ID
    g = lambda p: v2_client.get(f"/api/v2{p}", headers=auth_headers)

    nodes = g(f"/lines/{L}/nodes"); assert nodes.status_code == 200, nodes.text
    ns = nodes.json()["nodes"]; assert ns
    assert all(isinstance(n["display_ids"], list) for n in ns), "display_ids 는 배열(§5-1)"
    racks = [n for n in ns if n["node_kind"] == "RACK"]; stations = [n for n in ns if n["node_kind"] == "STATION"]
    assert racks and all(n["ui_kind"] is None and isinstance(n["slots"], list) for n in racks), "RACK: ui_kind null · slots 배열"
    assert all(n["slots"] is None for n in stations)
    assert all(isinstance(sl["contents"], list) for n in racks for sl in n["slots"]), "slot.contents 는 배열(§5-3)"
    assert [n["step_order"] for n in ns] == sorted(n["step_order"] for n in ns)

    tr = g(f"/lines/{L}/transporters"); assert tr.status_code == 200, tr.text
    ts = tr.json()["transporters"]; assert ts
    assert all(t["kind"] in ("ROBOT", "OPERATOR", "CONVEYOR") for t in ts), "ROBOT_ARM 은 ROBOT 으로"
    assert all(t["status"] in ("IDLE", "BUSY", "ERROR", "OFFLINE") for t in ts)

    cmd = g(f"/transporters/{ts[0]['transporter_id']}/commands"); assert cmd.status_code == 200, cmd.text
    c = cmd.json(); assert isinstance(c["node_ids"], list) and isinstance(c["commands"], list)
    assert all("command_id" in x and "id" not in x for x in c["commands"]), "yaml id → command_id"
    assert g("/transporters/NOPE/commands").status_code == 404

    w = g(f"/lines/{L}/wip"); assert w.status_code == 200, w.text
    assert all(isinstance(r["waiting"], bool) and r["ref_kind"] in ("UNIT", "GROUP") for r in w.json()["wip"])

    ib = g(f"/nodes/{stations[0]['node_id']}/inbound"); assert ib.status_code == 200, ib.text
    assert all(r["key"].split(":")[0] == r["ref_kind"].lower() for r in ib.json()["inbound"])


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_p2_reads_from_dev_db(v2_client, settings, auth_headers, monkeypatch):
    """R6 R7 R8 R9 R10 R12 — 구조만(값은 DB 상태 따라). 빈 목록도 정상 응답이어야 한다."""
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    L = settings.LINE_ID
    g = lambda p: v2_client.get(f"/api/v2{p}", headers=auth_headers)
    ns = g(f"/lines/{L}/nodes").json()["nodes"]
    racks = [n for n in ns if n["node_kind"] == "RACK"]; stations = [n for n in ns if n["node_kind"] == "STATION"]

    for st in stations:
        r6 = g(f"/nodes/{st['node_id']}/source-racks"); assert r6.status_code == 200, r6.text
        assert all(set(x) == {"node_id", "label", "capacity", "occupancy", "slot_count"} for x in r6.json()["racks"])

    rk = racks[0]["node_id"]
    r7 = g(f"/racks/{rk}/slots"); assert r7.status_code == 200, r7.text
    slots = r7.json()["slots"]; assert slots and all(isinstance(s["contents"], list) for s in slots)
    assert all((s["head_display_id"] is None) == (s["occupancy"] == 0) for s in slots), "head 는 든 칸에만"
    assert g(f"/racks/{stations[0]['node_id']}/slots").status_code == 404, "설비는 칸이 없다"

    r8 = g(f"/racks/{rk}/slots/{slots[0]['slot_no']}/queue"); assert r8.status_code == 200, r8.text
    q = r8.json()["queue"]
    assert len(q) == slots[0]["occupancy"], "대기열 길이 = 칸 점유(빈 자리는 안 낸다)"
    assert all(x["kinds"] == len(x["contents"]) and x["unit_id"] and x["display_id"] for x in q)
    assert all(x["pos_no"] == 1 for x in q if x["retrievable"]) or not q, "FIFO 랙은 pos 1 만 반출 가능"

    for st in stations:
        r9 = g(f"/nodes/{st['node_id']}/groups"); assert r9.status_code == 200, r9.text
        for grp in r9.json()["groups"]:
            assert isinstance(grp["sources"], list) and all(isinstance(s["parts"], dict) for s in grp["sources"]), "sources 는 jsonb 배열(§5-6)"
            assert isinstance(grp["capacity"], int) and isinstance(grp["closed"], bool)
        r10 = g(f"/nodes/{st['node_id']}/parts"); assert r10.status_code == 200, r10.text
        for pr in r10.json()["parts"]:
            assert set(pr) >= {"unit_id", "display_id", "part_no", "measure_spec", "tol", "verdict", "value", "judged_at"}
            assert pr["tol"] is None or set(pr["tol"]) <= {"nominal_mm", "tol_mm"}

    r12 = g("/parts"); assert r12.status_code == 200 and isinstance(r12.json()["parts"], list)


# ── 쓰기 W1~W5 ──────────────────────────────────────────────

def test_write_validation_without_db(v2_client, auth_headers):
    """입력 검증은 DB 앞에서 — PG 없이 422."""
    r = v2_client.post("/api/v2/nodes/PRT-01/state", headers=auth_headers, json={"status": "XX", "actor": "t"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_STATUS"
    r = v2_client.post("/api/v2/moves", headers=auth_headers,
                       json={"unit_id": "u", "group_id": "g", "from_node": "a", "to_node": "b", "actor": "t"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "BAD_REF"
    r = v2_client.post("/api/v2/judgements", headers=auth_headers,
                       json={"unit_id": "u", "node_id": "n", "verdict": "MAYBE", "value": None, "note": None, "actor": "t"})
    assert r.status_code == 422


def test_write_is_503_when_line_mes_off(v2_client, settings, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "LINE_DSN", "")
    r = v2_client.post("/api/v2/commands", headers=auth_headers, json={"kind": "MODE_CHANGE", "target": "x", "payload": {}, "actor": "t"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "LINE_MES_OFF"


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_writes_on_dev_db(v2_client, settings, auth_headers, monkeypatch):
    """W3 · W2 거부 · W5 — 되읽기로 확인(계획 §4). 개발 DB 상태를 바꾼다."""
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    L = settings.LINE_ID
    g = lambda p: v2_client.get(f"/api/v2{p}", headers=auth_headers)
    p = lambda path, body: v2_client.post(f"/api/v2{path}", headers=auth_headers, json=body)
    nodes = g(f"/lines/{L}/nodes").json()["nodes"]
    busy = next((n for n in nodes if n["node_kind"] == "STATION" and n["occupancy"]), None)
    empty = next(n for n in nodes if n["node_kind"] == "STATION" and not n["occupancy"])

    r = p(f"/nodes/{empty['node_id']}/state", {"status": "DONE", "actor": "t"})
    assert r.status_code == 200 and r.json()["ok"] is False, "개체 없는 노드는 ok=false 로 알려준다"
    if busy:
        r = p(f"/nodes/{busy['node_id']}/state", {"status": "RUN", "duration_s": 600, "actor": "t"})
        b = r.json(); assert r.status_code == 200 and b["ok"] and b["event_ids"] and len(b["unit_ids"]) == busy["occupancy"]
        after = next(n for n in g(f"/lines/{L}/nodes").json()["nodes"] if n["node_id"] == busy["node_id"])
        assert after["status"] == "RUN", "되읽기: 상태가 RUN 으로"
        # 경로에 없는 이동은 엔진이 409 로 거부한다
        uid = v2_client.get(f"/api/v2/lines/{L}/wip", headers=auth_headers).json()["wip"][0]["ref"]
        r = p("/moves", {"unit_id": uid, "from_node": busy["node_id"], "to_node": "NOPE-NODE", "actor": "t"})
        assert r.status_code in (404, 409), r.text

    r = p("/commands", {"kind": "MODE_CHANGE", "target": "ARM-A", "payload": {"auto": False}, "actor": "t"})
    assert r.status_code == 200 and r.json()["ok"]
    r = p("/commands", {"kind": "GROUP_CLOSE", "target": "BOX-NOPE", "payload": {}, "actor": "t"})
    assert r.status_code == 409


# ── W6 · ETag ───────────────────────────────────────────────

@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_w6_records_but_does_not_send(v2_client, settings, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    from app.line import db
    L = settings.LINE_ID
    ts = v2_client.get(f"/api/v2/lines/{L}/transporters", headers=auth_headers).json()["transporters"]
    auto = next((t for t in ts if t["auto_dispatch"]), None); manual = next((t for t in ts if not t["auto_dispatch"]), None)
    p = lambda tid, cid: v2_client.post(f"/api/v2/transporters/{tid}/commands/{cid}", headers=auth_headers, json={"actor": "t"})
    assert p("NOPE", "x").status_code == 404
    if manual:
        assert p(manual["transporter_id"], "x").json()["detail"]["code"] == "MANUAL_TRANSPORTER"
    if auto:
        cmds = v2_client.get(f"/api/v2/transporters/{auto['transporter_id']}/commands", headers=auth_headers).json()["commands"]
        assert p(auto["transporter_id"], "no-such-cmd").json()["detail"]["code"] == "COMMAND_NOT_FOUND"
        ok = next((c for c in cmds if c["verified"]), None); bad = next((c for c in cmds if not c["verified"]), None)
        if bad:
            assert p(auto["transporter_id"], bad["command_id"]).json()["detail"]["code"] == "UNVERIFIED_COMMAND"
        if ok:
            before = db.rows("SELECT count(*) AS c FROM command_log WHERE kind='DEVICE'")[0]["c"]
            r = p(auto["transporter_id"], ok["command_id"]); b = r.json()
            assert r.status_code == 200 and b["ok"] is False and b["warnings"], "보내지 않았으면 ok=false 로 말한다"
            assert db.rows("SELECT count(*) AS c FROM command_log WHERE kind='DEVICE'")[0]["c"] == before + 1


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_etag_304_on_polled_reads(v2_client, settings, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "LINE_DSN", os.environ["LINE_DSN"])
    L = settings.LINE_ID
    for path in (f"/lines/{L}/nodes", f"/lines/{L}/wip"):
        r1 = v2_client.get(f"/api/v2{path}", headers=auth_headers)
        assert r1.status_code == 200 and r1.headers.get("etag"), path
        r2 = v2_client.get(f"/api/v2{path}", headers={**auth_headers, "If-None-Match": r1.headers["etag"]})
        assert r2.status_code == 304, f"{path}: 같은 상태면 304"
        r3 = v2_client.get(f"/api/v2{path}", headers={**auth_headers, "If-None-Match": '"stale"'})
        assert r3.status_code == 200
