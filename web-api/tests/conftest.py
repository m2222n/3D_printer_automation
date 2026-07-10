"""
web-api 계약 테스트 공용 픽스처
================================
리팩터링(프린터 어댑터 도입) 안전망. 외부 API(Formlabs/PreForm)는 mock하고
핵심 경로(로그인·모니터링·프린터·로봇 계약)의 응답 계약을 잠근다.

⚠️ 이 테스트들의 목적 = "어댑터로 뜯어도 계약이 안 깨졌음"을 증명하는 그물.
   특히 PrinterSummary 5필드(status/is_online/has_error/is_ready/ready_to_print)는
   로봇 핸드셰이크 계약이라 절대 깨지면 안 됨.
"""

import os
import sys
from pathlib import Path

import pytest

# web-api/ 를 import 경로에 추가 (app.* 임포트용)
WEB_API_ROOT = Path(__file__).resolve().parent.parent
if str(WEB_API_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_API_ROOT))


# 테스트용 인증 설정 (실제 .env 로드 전에 환경변수로 주입)
TEST_USERNAME = "testadmin"
TEST_PASSWORD = "testpw123!"
TEST_JWT_SECRET = "test-secret-do-not-use-in-prod"


@pytest.fixture(scope="session", autouse=True)
def _test_env():
    """테스트 세션 동안 인증을 활성화된 상태로 고정.

    get_settings()가 @lru_cache라, 환경변수를 먼저 세팅한 뒤 캐시를 비우고
    Settings를 다시 만들도록 한다.
    """
    from app.core import user_auth
    from app.core.config import get_settings

    os.environ["AUTH_USERNAME"] = TEST_USERNAME
    os.environ["AUTH_PASSWORD_HASH"] = user_auth.hash_password(TEST_PASSWORD)
    os.environ["JWT_SECRET"] = TEST_JWT_SECRET
    # 외부 접속을 시도하지 않도록 더미 Formlabs 설정
    os.environ.setdefault("FORMLABS_CLIENT_ID", "test-client")
    os.environ.setdefault("FORMLABS_CLIENT_SECRET", "test-secret")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(_test_env):
    from app.core.config import get_settings
    return get_settings()


@pytest.fixture
def auth_token(settings):
    """유효한 JWT 토큰 발급 (인증 필요한 요청용)."""
    from app.core import user_auth
    return user_auth.create_access_token(
        username=settings.AUTH_USERNAME,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        expire_days=settings.JWT_EXPIRE_DAYS,
    )


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def client(_test_env):
    """FastAPI TestClient.

    ⚠️ lifespan(폴링 서비스 시작)을 띄우지 않도록 raise_server_exceptions는 기본,
    TestClient를 context manager 없이 생성하면 lifespan이 실행되지 않는다.
    폴링 서비스는 각 테스트가 monkeypatch로 stub한다.
    """
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_polling_singleton():
    """각 테스트 후 폴링 서비스 싱글톤을 초기화 (테스트 간 오염 방지)."""
    yield
    import app.services.polling_service as ps
    ps._polling_service = None
