"""
Formlabs Web API authentication module.

- OAuth 2.0 Client Credentials flow
- Access token lifecycle management
- Automatic refresh before expiration
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FormlabsAuthManager:
    """
    Authentication manager for Formlabs Web API.
    """

    def __init__(self):
        self.settings = get_settings()
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def token_endpoint(self) -> str:
        return f"{self.settings.FORMLABS_API_BASE_URL}/developer/v1/o/token/"

    async def initialize(self) -> bool:
        logger.info("Initializing Formlabs API authentication...")
        return await self._refresh_token()

    async def get_valid_token(self) -> str:
        async with self._lock:
            if self._should_refresh():
                success = await self._refresh_token()
                if not success:
                    raise RuntimeError("Formlabs API token refresh failed")
            return str(self._access_token)

    def _should_refresh(self) -> bool:
        if self._access_token is None or self._token_expires_at is None:
            return True

        margin = timedelta(seconds=self.settings.TOKEN_REFRESH_MARGIN_SECONDS)
        return datetime.now() >= (self._token_expires_at - margin)

    async def _refresh_token(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_endpoint,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.settings.FORMLABS_CLIENT_ID,
                        "client_secret": self.settings.FORMLABS_CLIENT_SECRET,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code == 200:
                    data = response.json()
                    self._access_token = data["access_token"]
                    expires_in = data.get("expires_in", 86400)
                    self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    logger.info(
                        "Formlabs API token issued successfully (expires: %s)",
                        self._token_expires_at.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    return True

                if response.status_code == 401:
                    logger.error("Authentication failed - check FORMLABS_CLIENT_ID/SECRET")
                    logger.error("Response: %s", response.text)
                    return False

                logger.error("Token request failed - status code: %s", response.status_code)
                logger.error("Response: %s", response.text)
                return False

        except httpx.TimeoutException:
            logger.error("Formlabs API connection timed out")
            return False
        except httpx.RequestError as e:
            logger.error("Network request error: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected auth error: %s", e)
            return False

    def get_auth_headers(self) -> dict:
        if self._access_token is None:
            raise RuntimeError("Token is not initialized. Call initialize() first.")
        return {
            "Authorization": f"bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    @property
    def token_status(self) -> dict:
        if self._token_expires_at is None:
            return {"valid": False, "expires_at": None, "remaining_seconds": 0}

        remaining = (self._token_expires_at - datetime.now()).total_seconds()
        return {
            "valid": remaining > 0,
            "expires_at": self._token_expires_at.isoformat(),
            "remaining_seconds": max(0, int(remaining)),
        }


_auth_manager: Optional[FormlabsAuthManager] = None


async def get_auth_manager() -> FormlabsAuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = FormlabsAuthManager()
        await _auth_manager.initialize()
    return _auth_manager

