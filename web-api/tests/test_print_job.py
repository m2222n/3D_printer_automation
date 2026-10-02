"""출력 작업 계약 테스트 (#7) — simul_mode 경로.

/api/v1/local/print 의 시뮬레이션 경로(장비 없이 job 생성→SENT)를 검증.
= 배포 검증 루틴의 "시뮬 CMD 1회"와 같은 경로. 인메모리 SQLite로 격리.
"""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.local.models import Base


@pytest.fixture
def temp_db():
    """인메모리 SQLite + 테이블 생성.

    StaticPool = 단일 연결 공유 (인메모리 DB가 세션마다 초기화되는 것 방지).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    return _override


@pytest.fixture
def upload_dir(monkeypatch):
    """업로드 디렉토리를 임시 폴더로 바꾸고 더미 STL을 둔다."""
    d = tempfile.mkdtemp()
    stl = Path(d) / "dummy.stl"
    stl.write_text("solid dummy\nendsolid dummy\n")
    # start_print_job이 참조하는 settings.UPLOAD_DIR을 임시로 교체
    import app.local.routes as routes_mod
    monkeypatch.setattr(routes_mod.settings, "UPLOAD_DIR", d)
    return d


def test_simul_print_creates_sent_job(client, auth_headers, temp_db, upload_dir):
    """simul_mode=True → 장비 없이 job 생성되고 SENT 상태로 반환."""
    from app.main import create_app
    from app.local.database import get_local_db
    from fastapi.testclient import TestClient

    app = create_app()
    app.dependency_overrides[get_local_db] = temp_db
    c = TestClient(app)

    resp = c.post(
        "/api/v1/local/print",
        headers=auth_headers,
        json={
            "printer_serial": "Form4-Test",
            "stl_file": "dummy.stl",
            "simul_mode": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] in ("SENT", "sent")


def test_simul_print_missing_stl_404(client, auth_headers, temp_db, upload_dir):
    """simul_mode인데 존재하지 않는 STL → 404."""
    from app.main import create_app
    from app.local.database import get_local_db
    from fastapi.testclient import TestClient

    app = create_app()
    app.dependency_overrides[get_local_db] = temp_db
    c = TestClient(app)

    resp = c.post(
        "/api/v1/local/print",
        headers=auth_headers,
        json={
            "printer_serial": "Form4-Test",
            "stl_file": "does_not_exist.stl",
            "simul_mode": True,
        },
    )
    assert resp.status_code == 404


# ── 라인 MES Spawn 연동 (2026-09-22) ─────────────────────────────────────
# "프린터가 받았다" 분기에서 Spawn 한 건. 실패해도 프린터는 돌고 있으므로 삼키되
# print_jobs.error_message 에 LINE_UNTRACKED 로 남겨야 한다 (조용히 사라지는 배치 방지).

def _run_process(temp_db, monkeypatch, spawn_impl, cmd_id=None, part_type=None):
    import asyncio
    import app.local.routes as routes_mod
    from app.local.models import PrintJob
    pub = pytest.importorskip("app.local.line_publish")   # 발행 모듈이 없는 체크아웃에선 이 두 테스트만 건너뛴다

    db = next(temp_db())
    job = PrintJob(stl_filename="dummy.stl", printer_serial="Form4-Test", settings={}, status="pending")
    db.add(job); db.commit()

    class _Client:
        async def prepare_and_print(self, **kw):
            return {"success": True, "scene_id": "s1"}
    async def _get_client():
        return _Client()
    monkeypatch.setattr(routes_mod, "get_preform_client", _get_client)

    calls = []
    def _spawn(printer_serial, cmd_id=None, part_type=None, qty=1):
        calls.append((printer_serial, cmd_id, part_type, qty)); return spawn_impl()
    monkeypatch.setattr(pub, "spawn_for_print", _spawn)

    asyncio.run(routes_mod._process_print_job(job.id, "/x/dummy.stl", "Form4-Test", None, db, cmd_id, part_type))
    db.refresh(job)
    return job, calls


def test_print_sent_publishes_spawn_with_cmd_id(temp_db, monkeypatch):
    """성공 → Spawn 1회 · cmd_id · 프리셋 part_type 전달 · 에러 없음."""
    job, calls = _run_process(temp_db, monkeypatch, lambda: "unit-1", cmd_id="cmd-7", part_type="bracket")
    assert calls == [("Form4-Test", "cmd-7", "bracket", 1)]
    assert job.status in ("SENT", "sent") and job.error_message is None


def test_spawn_failure_is_recorded_not_raised(temp_db, monkeypatch):
    """Spawn 이 죽어도 job 은 SENT 유지 + error_message 에 LINE_UNTRACKED — 프린터는 이미 돈다."""
    def boom(): raise RuntimeError("PG down")
    job, _ = _run_process(temp_db, monkeypatch, boom)
    assert job.status in ("SENT", "sent")
    assert job.error_message and job.error_message.startswith("LINE_UNTRACKED: PG down")
