"""로그인·인증 미들웨어 계약 테스트 (#1, #2)."""

from tests.conftest import TEST_USERNAME, TEST_PASSWORD


def test_login_success_returns_token(client):
    """올바른 자격증명 → 200 + access_token 발급."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in_days"] > 0


def test_login_wrong_password_401(client):
    """비번 오답 → 401 invalid_credentials."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_credentials"


def test_login_wrong_username_401(client):
    """없는 사용자 → 401."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 401


def test_protected_route_without_token_401(client):
    """토큰 없이 보호된 엔드포인트 → 401 (미들웨어 차단)."""
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 401


def test_me_with_valid_token_200(client, auth_headers):
    """유효 토큰으로 /me → 200 + 사용자명."""
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == TEST_USERNAME
