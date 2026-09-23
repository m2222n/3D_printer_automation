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
