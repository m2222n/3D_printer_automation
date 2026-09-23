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
