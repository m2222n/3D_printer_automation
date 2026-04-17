"""
Basic Auth ASGI Middleware
==========================
HTTP + WebSocket 모두 보호하는 Raw ASGI 미들웨어.
BASIC_AUTH_USERNAME / BASIC_AUTH_PASSWORD 둘 다 설정되어 있을 때만 활성화.
"""

import base64
import secrets

from starlette.responses import Response


class BasicAuthMiddleware:

    def __init__(self, app, username: str, password: str):
        self.app = app
        self.username = username
        self.password = password
        self.enabled = bool(username and password)

    async def __call__(self, scope, receive, send):
        if not self.enabled or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # CORS preflight (OPTIONS) 는 인증 없이 통과
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()

        if self._check_auth(auth_header):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            response = Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Formlabs Remote Control"'},
                content="Unauthorized",
            )
            await response(scope, receive, send)
        else:
            # WebSocket: close
            await send({"type": "websocket.close", "code": 4003})

    def _check_auth(self, auth_header: str) -> bool:
        if not auth_header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            provided_user, provided_pass = decoded.split(":", 1)
            return (
                secrets.compare_digest(provided_user, self.username)
                and secrets.compare_digest(provided_pass, self.password)
            )
        except Exception:
            return False
