"""
Local API 메인 애플리케이션
===========================
PreFormServer 연동 및 프리셋 관리
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db
from app.api.routes import router
from app.services.preform_client import get_preform_client

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 이벤트"""
    # 시작
    logger.info("🚀 Local API 시작 중...")
    logger.info(f"📋 앱 이름: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"🖨️ PreFormServer: {settings.PREFORM_SERVER_HOST}:{settings.PREFORM_SERVER_PORT}")

    # DB 초기화
    init_db()

    # 업로드 디렉토리 생성
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 업로드 디렉토리: {upload_dir.absolute()}")

    # PreFormServer 연결 테스트
    client = await get_preform_client()
    if await client.health_check():
        logger.info("✅ PreFormServer 연결 성공")
    else:
        logger.warning("⚠️ PreFormServer 연결 실패 - 나중에 재시도 필요")

    logger.info("✅ Local API 시작 완료")

    yield

    # 종료
    logger.info("🛑 Local API 종료 중...")
    client = await get_preform_client()
    await client.close()
    logger.info("👋 Local API 종료 완료")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Formlabs PreFormServer 연동 API - STL 업로드, 프리셋 관리, 원격 프린트",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 프로덕션에서 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(router, prefix="/api/v1/local")


# 루트 엔드포인트
@app.get("/")
async def root():
    """API 루트"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api_prefix": "/api/v1/local"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8086,
        reload=settings.DEBUG
    )
