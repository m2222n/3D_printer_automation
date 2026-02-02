"""
Local API 데이터베이스 설정
===========================
SQLite + SQLAlchemy (프리셋/작업 관리)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import logging

from app.core.config import get_settings
from app.local.models import Base

logger = logging.getLogger(__name__)

# 엔진 생성
settings = get_settings()
engine = create_engine(
    settings.LOCAL_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite용
    echo=settings.DEBUG
)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_local_db():
    """데이터베이스 테이블 생성"""
    logger.info("📦 Local API 데이터베이스 초기화 중...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Local API 데이터베이스 초기화 완료")


def get_local_db() -> Session:
    """DB 세션 의존성 주입용"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_local_db_session():
    """컨텍스트 매니저로 DB 세션 사용"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
