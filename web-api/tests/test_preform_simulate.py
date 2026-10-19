"""
PREFORM_SIMULATE 계약 테스트 (2026-10-19)
=====================================
목적 = "공장 밖에서 .env 한 줄로 출력 흐름이 끝까지 도는가"를 **실제 PreFormServerClient** 로 증명한다.
가짜 dict 가 아니라 운영 코드(prepare_scene · prepare_and_print · 업로드 · 스크린샷)를 그대로 태운다.

🚨 운영 안전 = 기본값 False 에서는 가짜 전송 계층이 **끼어들지 않아야 한다**(마지막 테스트).
"""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from app.core.config import get_settings


@pytest.fixture
def sim_env():
    """PREFORM_SIMULATE=true 로 settings 재생성 · 끝나면 원복."""
    import app.local.preform_simulator as sim
    os.environ["PREFORM_SIMULATE"] = "true"
    get_settings.cache_clear()
    sim._singleton = None
    yield get_settings()
    os.environ.pop("PREFORM_SIMULATE", None)
    get_settings.cache_clear()
    sim._singleton = None


@pytest.fixture
def stl_file():
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
        f.write(b"solid sim\n" + b"x" * 200_000 + b"\nendsolid sim\n")   # ≈0.2MB → 가짜 예측에 반영
        path = f.name
    yield path
    os.unlink(path)


def _client():
    from app.local.preform_client import PreFormServerClient
    return PreFormServerClient()


def test_flag_default_off_and_no_transport_injected():
    """기본값 False · 가짜 전송 계층 미주입 — 운영 .env 가 그대로면 아무것도 안 바뀐다."""
    os.environ.pop("PREFORM_SIMULATE", None)
    get_settings.cache_clear()
    s = get_settings()
    assert s.PREFORM_SIMULATE is False
    assert _client()._transport_kwargs() == {}


def test_health_materials_printers(sim_env):
    c = _client()
    assert asyncio.run(c.health_check()) is True
    mats = asyncio.run(c.list_materials())
    codes = {m["code"] for m in mats}
    assert "FLGPGR05" in codes and len(mats) >= 3
    printers = asyncio.run(c.discover_printers())
    # PRINTER_SERIAL_MAP 에 등록된 수만큼(비어 있으면 기본 1대) · 전부 online
    assert len(printers) == max(1, len(sim_env.PRINTER_SERIAL_MAP))
    assert all(p.is_online for p in printers)


def test_prepare_scene_full_flow(sim_env, stl_file):
    """Scene 생성 → 업로드 → import → auto-* → 예측 → 검증 → 간섭 → 스크린샷 까지 운영 코드 그대로."""
    c = _client()
    r = asyncio.run(c.prepare_scene(stl_file, hollow=True))
    assert r["success"] is True, r
    est = r["estimate"]
    assert est.model_count == 1
    assert est.estimated_print_time_ms and est.estimated_print_time_ms > 0
    assert est.estimated_material_ml and est.estimated_material_ml > 0
    assert est.precise_total_s and est.precise_total_s > est.precise_preprint_s
    assert est.validation.get("valid") is True
    assert est.interferences == []
    assert est.screenshot_url and est.screenshot_url.endswith(f"{r['scene_id']}.png")

    # 스크린샷이 진짜 PNG 바이트로 내려온다(file_receiver 경로도 가짜가 받는다)
    png = asyncio.run(c._download_screenshot_from_factory(f"{r['scene_id']}.png"))
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"

    # 업로드 경로는 공장 PC 와 같은 모양(C:\STL_Files\<원래 파일명>)
    from app.local.preform_simulator import get_simulator
    assert any(k.endswith(Path(stl_file).name) for k in get_simulator().uploads)

    assert asyncio.run(c.delete_scene(r["scene_id"])) is True


def test_prepare_and_print_returns_job(sim_env, stl_file):
    """프린터 전송까지 success — 단 아무 데도 안 보내고 job 만 기록된다."""
    from app.local.preform_simulator import get_simulator
    from app.local.schemas import PrintSettings
    c = _client()
    serial = asyncio.run(c.discover_printers())[0].serial
    r = asyncio.run(c.prepare_and_print(stl_file, serial, PrintSettings()))
    assert r["success"] is True, r
    assert r["estimated_print_time_ms"] > 0
    jobs = get_simulator().jobs
    assert jobs and jobs[-1]["printer"] == serial and jobs[-1]["job_id"].startswith("sim-")


def test_duplicate_and_unknown_scene(sim_env, stl_file):
    c = _client()
    sid = asyncio.run(c.create_scene())
    assert asyncio.run(c.import_model(sid, stl_file)) is True
    models = asyncio.run(c.get_scene_models(sid))
    assert len(models) == 1
    assert asyncio.run(c.duplicate_model(sid, models[0]["id"], count=3)) is True
    assert len(asyncio.run(c.get_scene_models(sid))) == 4
    # 없는 scene 은 404 → 운영 코드가 None/False 로 받는다(예외 X)
    assert asyncio.run(c.get_scene_info("nope")) is None


def test_health_route_reports_simulated(sim_env, client, auth_headers):
    """운영 화면·동료가 '지금 가짜인가' 를 알 수 있어야 한다."""
    import app.local.preform_client as pc
    pc._preform_client = None
    r = client.get("/api/v1/local/health", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True
    assert body["preform_server"] == "connected"
    pc._preform_client = None
