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
