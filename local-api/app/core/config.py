"""
Local API 설정
==============
PreFormServer 연동 및 프리셋 관리 설정
"""

from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Local API 설정"""

    # 앱 정보
    APP_NAME: str = "Formlabs Local API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # PreFormServer 설정
    PREFORM_SERVER_HOST: str = "localhost"
    PREFORM_SERVER_PORT: int = 44388
    PREFORM_SERVER_TIMEOUT: int = 60  # 초 (STL 처리 시간 고려)

    # 파일 업로드 설정
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: list = [".stl", ".obj", ".form"]

    # 프리셋 DB 설정
    DATABASE_URL: str = "sqlite:///./presets.db"

    # Form 4 기본 설정
    DEFAULT_MACHINE_TYPE: str = "FORM-4-0"
    DEFAULT_LAYER_THICKNESS_MM: float = 0.05

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings()
