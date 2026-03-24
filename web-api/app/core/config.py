"""
Formlabs Web API 시스템 설정
================================
- Formlabs API 인증 정보
- 폴링 주기 설정
- 알림 설정
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # ===========================================
    # 앱 기본 설정
    # ===========================================
    APP_NAME: str = "Formlabs 원격제어 시스템"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _parse_debug(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"1", "true", "yes", "y", "on", "debug", "development"}:
                return True
            if s in {"0", "false", "no", "n", "off", "release", "prod", "production"}:
                return False
        return bool(v)
    
    # ===========================================
    # Formlabs API 설정
    # ===========================================
    # Dashboard > Developer Tools에서 발급
    FORMLABS_CLIENT_ID: str = ""
    FORMLABS_CLIENT_SECRET: str = ""
    FORMLABS_API_BASE_URL: str = "https://api.formlabs.com"
    
    # 토큰 관리
    TOKEN_REFRESH_MARGIN_SECONDS: int = 3600  # 만료 1시간 전 갱신
    
    # ===========================================
    # 폴링 설정
    # ===========================================
    # Rate Limit: IP당 100 req/sec, 사용자당 1500 req/hr
    # 권장: 10초 이상
    POLLING_INTERVAL_SECONDS: int = 15  # 프린터 상태 폴링 주기
    
    # ===========================================
    # 프린터 설정
    # ===========================================
    # Form 4 프린터 4대 시리얼 번호 (실제 값으로 교체 필요)
    PRINTER_SERIALS: list[str] = [
        "Form4-CapableGecko",
        "Form4-HeavenlyTuna",
        "Form4-CorrectPelican",
        "Form4-ShrewdStork"
    ]
    
    # ===========================================
    # 데이터베이스 설정
    # ===========================================
    DATABASE_URL: str = "postgresql://localhost:5432/formlabs_db"
    
    # ===========================================
    # 알림 설정
    # ===========================================
    # 이메일 알림
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    NOTIFICATION_EMAIL_TO: list[str] = []
    
    # 푸시 알림 (FCM)
    FCM_SERVER_KEY: Optional[str] = None
    
    # 슬랙 알림
    SLACK_WEBHOOK_URL: Optional[str] = None
    
    # ===========================================
    # 알림 트리거 조건
    # ===========================================
    NOTIFY_ON_PRINT_COMPLETE: bool = True
    NOTIFY_ON_PRINT_ERROR: bool = True
    NOTIFY_ON_LOW_RESIN: bool = True
    LOW_RESIN_THRESHOLD_ML: int = 100  # 레진 100ml 이하 시 알림

    # ===========================================
    # Phase 2: Local API 설정 (PreFormServer 연동)
    # ===========================================
    PREFORM_SERVER_HOST: str = "localhost"
    PREFORM_SERVER_PORT: int = 44388
    PREFORM_SERVER_TIMEOUT: int = 60  # 초 (STL 처리 시간 고려)

    # 파일 업로드 설정
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: list[str] = [".stl", ".obj", ".form"]

    # 공장 PC 파일 수신 서버 (file_receiver.py)
    FILE_RECEIVER_HOST: str = "localhost"
    FILE_RECEIVER_PORT: int = 8089

    # 프리셋 DB 설정 (SQLite)
    LOCAL_DATABASE_URL: str = "sqlite:///./presets.db"

    # Form 4 기본 설정
    DEFAULT_MACHINE_TYPE: str = "FORM-4-0"
    DEFAULT_LAYER_THICKNESS_MM: float = 0.05

    # Sequence service DB (MySQL) for automation tab
    SEQUENCE_MYSQL_DSN: str = "mysql+pymysql://root:root@127.0.0.1:3306/automation"

    # Manual TCP send targets for automation manual tab
    ROBOT_TCP_HOST: str = "127.0.0.1"
    ROBOT_TCP_PORT: int = 9100
    VISION_TCP_HOST: str = "127.0.0.1"
    VISION_TCP_PORT: int = 9200
    MANUAL_TCP_TIMEOUT_SECONDS: float = 5.0

    # Ajin IO (AXL.dll) for automation manual IO page
    AJIN_SIMULATION: bool = True
    AJIN_IRQ_NO: int = 7
    AJIN_DLL_PATH: str = "../sequence_service/app/io/bin/AXL.dll"
    AJIN_IO_CSV_PATH: str = "../sequence_service/app/io/IO.csv"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings()
