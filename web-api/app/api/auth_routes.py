"""
사용자 로그인 API
=================
- POST /api/v1/auth/login   : ID/PW로 JWT 발급
- GET  /api/v1/auth/me      : 현재 토큰의 사용자 정보 (프론트가 토큰 유효성 체크용)
- POST /api/v1/auth/logout  : 클라이언트 측 토큰 폐기 (서버는 stateless이라 별도 저장 안 함)
"""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.core import user_auth
from app.core.config import get_settings


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_days: int


class MeResponse(BaseModel):
    username: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    settings = get_settings()

    # 인증 비활성화 (.env 미설정) 시 로그인 거부 — 의도치 않은 우회 방지
    if not settings.AUTH_USERNAME or not settings.AUTH_PASSWORD_HASH or not settings.JWT_SECRET:
        logger.warning("로그인 시도 — 인증 미설정 상태")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth_not_configured",
        )

    if body.username != settings.AUTH_USERNAME:
        logger.info(f"로그인 실패 — 사용자명 불일치: {body.username!r}")
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if not user_auth.verify_password(body.password, settings.AUTH_PASSWORD_HASH):
        logger.info(f"로그인 실패 — 비번 불일치: {body.username!r}")
        raise HTTPException(status_code=401, detail="invalid_credentials")

    token = user_auth.create_access_token(
        username=settings.AUTH_USERNAME,
        secret=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        expire_days=settings.JWT_EXPIRE_DAYS,
    )
    logger.info(f"로그인 성공 — {body.username!r}")
    return LoginResponse(
        access_token=token,
        expires_in_days=settings.JWT_EXPIRE_DAYS,
    )


@router.get("/me", response_model=MeResponse)
async def me(request: Request):
    """
    현재 토큰이 유효한지 확인 + 사용자명 반환.
    미들웨어가 이미 검증해서 통과시켰으면 200, 아니면 401.
    """
    settings = get_settings()
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None

    payload = user_auth.decode_token(token, settings.JWT_SECRET, settings.JWT_ALGORITHM) if token else None
    if not payload or payload.get("sub") != settings.AUTH_USERNAME:
        raise HTTPException(status_code=401, detail="invalid_token")

    return MeResponse(username=payload["sub"])


@router.post("/logout")
async def logout():
    """
    JWT는 stateless라 서버 측 토큰 폐기 없음.
    클라이언트가 토큰을 삭제하면 즉시 로그아웃 효과.
    이 엔드포인트는 명시적 의도 표현용 (감사 로그).
    """
    logger.info("로그아웃 요청 수신")
    return {"detail": "logged_out"}
