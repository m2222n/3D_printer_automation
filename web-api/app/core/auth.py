"""
Formlabs Web API 인증 모듈
===========================
- OAuth 2.0 Client Credentials 방식
- Access Token 24시간 유효
- 자동 갱신 로직 포함
"""

import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FormlabsAuthManager:
    """
    Formlabs API 인증 관리자
    
    사용법:
        auth = FormlabsAuthManager()
        await auth.initialize()
        token = await auth.get_valid_token()
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
        
    @property
    def token_endpoint(self) -> str:
        """토큰 발급 엔드포인트"""
        return f"{self.settings.FORMLABS_API_BASE_URL}/developer/v1/o/token/"
    
    async def initialize(self) -> bool:
        """
        초기화 - 최초 토큰 발급
        
        Returns:
            bool: 성공 여부
        """
        logger.info("🔐 Formlabs API 인증 초기화 중...")
        return await self._refresh_token()
    
    async def get_valid_token(self) -> str:
        """
        유효한 Access Token 반환
        - 만료 임박 시 자동 갱신
        
        Returns:
            str: Access Token
            
        Raises:
            RuntimeError: 토큰 발급 실패 시
        """
        async with self._lock:
            # 토큰이 없거나 만료 임박한 경우 갱신
            if self._should_refresh():
                success = await self._refresh_token()
                if not success:
                    raise RuntimeError("Formlabs API 토큰 갱신 실패")
            
            return self._access_token
    
    def _should_refresh(self) -> bool:
        """토큰 갱신 필요 여부 확인"""
        if self._access_token is None or self._token_expires_at is None:
            return True
        
        # 만료 N초 전에 미리 갱신
        margin = timedelta(seconds=self.settings.TOKEN_REFRESH_MARGIN_SECONDS)
        return datetime.now() >= (self._token_expires_at - margin)
    
    async def _refresh_token(self) -> bool:
        """
        Access Token 발급/갱신
        
        Formlabs OAuth 2.0 Client Credentials Flow:
        POST /developer/v1/o/token/
        - grant_type: client_credentials
        - client_id: [Dashboard에서 발급]
        - client_secret: [Dashboard에서 발급]
        
        응답:
        {
            "access_token": "...",
            "token_type": "bearer",
            "expires_in": 86400  // 24시간
        }
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.token_endpoint,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.settings.FORMLABS_CLIENT_ID,
                        "client_secret": self.settings.FORMLABS_CLIENT_SECRET,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self._access_token = data["access_token"]
                    
                    # expires_in은 초 단위 (일반적으로 86400 = 24시간)
                    expires_in = data.get("expires_in", 86400)
                    self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    
                    logger.info(
                        f"✅ Formlabs API 토큰 발급 성공 "
                        f"(만료: {self._token_expires_at.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    return True
                
                elif response.status_code == 401:
                    logger.error("❌ 인증 실패 - Client ID/Secret 확인 필요")
                    logger.error(f"응답: {response.text}")
                    return False
                
                else:
                    logger.error(f"❌ 토큰 발급 실패 - 상태 코드: {response.status_code}")
                    logger.error(f"응답: {response.text}")
                    return False
                    
        except httpx.TimeoutException:
            logger.error("❌ Formlabs API 연결 타임아웃")
            return False
        except httpx.RequestError as e:
            logger.error(f"❌ 네트워크 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 예상치 못한 오류: {e}")
            return False
    
    def get_auth_headers(self) -> dict:
        """
        API 요청에 사용할 인증 헤더 반환
        
        Returns:
            dict: Authorization 헤더
        """
        if self._access_token is None:
            raise RuntimeError("토큰이 초기화되지 않음. initialize() 먼저 호출 필요")
        
        return {
            "Authorization": f"bearer {self._access_token}",
            "Content-Type": "application/json"
        }
    
    @property
    def token_status(self) -> dict:
        """현재 토큰 상태 정보"""
        if self._token_expires_at is None:
            return {
                "valid": False,
                "expires_at": None,
                "remaining_seconds": 0
            }
        
        remaining = (self._token_expires_at - datetime.now()).total_seconds()
        return {
            "valid": remaining > 0,
            "expires_at": self._token_expires_at.isoformat(),
            "remaining_seconds": max(0, int(remaining))
        }


# 전역 인증 관리자 (싱글톤)
_auth_manager: Optional[FormlabsAuthManager] = None


async def get_auth_manager() -> FormlabsAuthManager:
    """인증 관리자 싱글톤 반환"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = FormlabsAuthManager()
        await _auth_manager.initialize()
    return _auth_manager
