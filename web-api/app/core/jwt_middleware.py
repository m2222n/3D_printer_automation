"""
JWT 인증 ASGI 미들웨어
======================
HTTP + WebSocket 모두 보호.

활성화 조건: AUTH_USERNAME, AUTH_PASSWORD_HASH, JWT_SECRET 셋 다 설정되어 있을 때만.
하나라도 비면 비활성 → 로컬 개발 시 .env 비워두면 인증 없이 동작.

예외 경로:
- /api/v1/auth/login (로그인 엔드포인트 자체)
- /api/v1/auth/me (토큰 검증용, 내부에서 검증 처리)
- OPTIONS (CORS preflight)
- 정적 파일 (/, /assets/*, /index.html 등 — 프론트엔드는 누구나 로드 가능, 보호는 API 레이어)

응답 헤더 X-New-Token: sliding refresh로 갱신된 새 토큰을 반환해서 프론트가 교체 저장.
"""

import logging
from typing import Optional

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import user_auth


logger = logging.getLogger(__name__)


# 인증 없이 통과시킬 API 경로 (정확히 일치 또는 prefix)
PUBLIC_API_PATHS = {
    "/api/v1/auth/login",
}


def _is_protected_path(path: str) -> bool:
    """API 경로만 보호. 프론트 정적 파일은 누구나 로드 가능 (어차피 API 호출 시 401 받음)."""
    if not path.startswith("/api/"):
        return False
    if path in PUBLIC_API_PATHS:
        return False
    return True


def _extract_bearer_token(headers: dict) -> Optional[str]:
    """Authorization: Bearer <token> 에서 토큰 추출."""
    auth = headers.get(b"authorization", b"").decode()
    if not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip()


def _extract_websocket_token(scope: Scope, headers: dict) -> Optional[str]:
    """
    WebSocket: 쿼리스트링 ?token=... 또는 Sec-WebSocket-Protocol 헤더에서 추출.
    프론트 EventSource/WebSocket 생성 시 ?token=... 권장.
    """
    # 1) 쿼리스트링
    query = scope.get("query_string", b"").decode()
    for pair in query.split("&"):
        if pair.startswith("token="):
            return pair[6:]
    # 2) Authorization 헤더 (지원 안 하는 클라이언트 많지만 시도)
    return _extract_bearer_token(headers)


class JWTAuthMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        username: str,
        password_hash: str,
        jwt_secret: str,
        jwt_algorithm: str,
        expire_days: int,
        absolute_max_days: int,
    ):
        self.app = app
        self.username = username
        self.password_hash = password_hash
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.expire_days = expire_days
        self.absolute_max_days = absolute_max_days
        self.enabled = bool(username and password_hash and jwt_secret)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if not self.enabled or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # CORS preflight 통과
        if scope["type"] == "http" and method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # 보호 대상이 아니면 통과
        if not _is_protected_path(path):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))

        # 토큰 추출
        if scope["type"] == "websocket":
            token = _extract_websocket_token(scope, headers)
        else:
            token = _extract_bearer_token(headers)

        # 토큰 검증
        payload = user_auth.decode_token(token, self.jwt_secret, self.jwt_algorithm) if token else None

        if not payload:
            await self._reject(scope, send, "missing_or_invalid_token")
            return

        # 사용자명 확인
        if payload.get("sub") != self.username:
            await self._reject(scope, send, "user_mismatch")
            return

        # 절대 최대 기간 체크
        if not user_auth.is_within_absolute_max(payload, self.absolute_max_days):
            await self._reject(scope, send, "absolute_max_exceeded")
            return

        # Sliding refresh: 새 토큰 발급 (iat 보존)
        new_token: Optional[str] = None
        if scope["type"] == "http" and user_auth.should_refresh_token(payload, self.expire_days):
            from datetime import datetime, timezone
            iat = payload.get("iat")
            issued_at = datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None
            new_token = user_auth.create_access_token(
                username=self.username,
                secret=self.jwt_secret,
                algorithm=self.jwt_algorithm,
                expire_days=self.expire_days,
                issued_at=issued_at,  # iat 유지 → 절대 최대 기간 누적 계산 정확
            )

        # 통과 — 응답 헤더에 새 토큰 첨부 (있을 때)
        if new_token:
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers_list = list(message.get("headers", []))
                    headers_list.append((b"x-new-token", new_token.encode()))
                    # CORS 노출 헤더 (프론트가 읽을 수 있게)
                    headers_list.append((b"access-control-expose-headers", b"X-New-Token"))
                    message["headers"] = headers_list
                await send(message)
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, send: Send, reason: str):
        if scope["type"] == "http":
            response = JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized", "reason": reason},
            )
            await response(scope, receive=None, send=send)
        else:
            # WebSocket: close with policy violation code
            await send({"type": "websocket.close", "code": 4401})
