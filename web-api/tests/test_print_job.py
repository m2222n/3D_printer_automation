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
