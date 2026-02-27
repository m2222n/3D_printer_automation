"""
Formlabs 원격제어 시스템 - FastAPI 애플리케이션
================================================
Phase 1: Web API 모니터링 시스템
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.services.polling_service import start_polling_service, stop_polling_service, get_polling_service
from app.services.notification_service import notification_handler
from app.api.routes import router as api_router
from app.local.routes import router as local_router
from app.local.database import init_local_db

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 라이프사이클 관리
    - 시작: 폴링 서비스 시작, 알림 핸들러 등록
    - 종료: 폴링 서비스 중지
    """
    settings = get_settings()
    
    # =====================
    # 시작 시
    # =====================
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 시작")
    logger.info("=" * 60)
    
    # 폴링 서비스 시작
    try:
        polling_service = await get_polling_service()
        
        # 알림 핸들러 등록 (기존 Email/Slack/FCM)
        polling_service.on_notification(notification_handler)

        # 알림 이벤트 DB 저장 핸들러 등록
        async def save_notification_to_db(notification):
            """알림 이벤트를 DB에 저장"""
            try:
                from app.local.database import get_local_db_session
                from app.local.models import NotificationEvent
                from app.schemas.printer import now_kst
                with get_local_db_session() as db:
                    event = NotificationEvent(
                        event_type=notification.type.value if hasattr(notification.type, 'value') else str(notification.type),
                        printer_serial=notification.printer_serial,
                        printer_name=notification.printer_name,
                        job_name=notification.job_name,
                        message=notification.message,
                        created_at=now_kst(),
                    )
                    db.add(event)
            except Exception as e:
                logger.error(f"알림 DB 저장 실패: {e}")

        polling_service.on_notification(save_notification_to_db)

        # Local API DB 초기화
        init_local_db()

        # 폴링 시작
        await start_polling_service()

        # 실제 조회된 프린터 수 표시
        current_data = polling_service.get_current_data()
        printer_count = len(current_data.printers) if current_data else 0
        logger.info(f"✅ 모니터링 대상 프린터: {printer_count}대")
        logger.info(f"✅ 폴링 주기: {settings.POLLING_INTERVAL_SECONDS}초")
        
    except Exception as e:
        logger.error(f"❌ 서비스 시작 실패: {e}")
        raise
    
    yield  # 애플리케이션 실행
    
    # =====================
    # 종료 시
    # =====================
    logger.info("🛑 애플리케이션 종료 중...")
    await stop_polling_service()
    logger.info("👋 정상 종료 완료")


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 팩토리"""
    
    settings = get_settings()
    
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="""
## Formlabs 3D프린터 원격제어 시스템 API

### 주요 기능
- 🖨️ 프린터 실시간 상태 모니터링
- 📊 대시보드 데이터 제공
- 🔔 프린트 완료/에러 알림
- 📜 프린트 이력 조회
- 🔌 WebSocket 실시간 업데이트

### Phase 1 (현재)
Web API 기반 모니터링 시스템

### 향후 계획
- Phase 2: Local API 연동 (원격 프린팅)
- Phase 3: HCR 로봇 연동
- Phase 4: YOLO 비전 검사
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    # CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # API 라우터 등록
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(local_router, prefix="/api/v1/local")

    # 프론트엔드 정적 파일 서빙
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        # 정적 자산 (CSS, JS, 이미지 등)
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        # SPA 폴백: API가 아닌 모든 경로에서 index.html 반환
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(request: Request, full_path: str):
            # API 경로는 제외
            if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc"):
                raise HTTPException(status_code=404, detail="Not found")

            # 정적 파일이 있으면 반환
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(file_path)

            # 그 외에는 index.html 반환 (SPA 라우팅)
            return FileResponse(frontend_dist / "index.html")

        logger.info(f"📦 프론트엔드 정적 파일 서빙 활성화: {frontend_dist}")

    return app


# 애플리케이션 인스턴스
app = create_app()


# 헬스체크 (루트) - 프론트엔드가 없을 때만 JSON 반환
@app.get("/", tags=["Health"])
async def root():
    """서비스 상태 확인 (프론트엔드가 없을 때)"""
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        return FileResponse(frontend_dist / "index.html")

    settings = get_settings()
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """상세 헬스체크"""
    settings = get_settings()
    
    # 폴링 서비스 상태 확인
    try:
        polling_service = await get_polling_service()
        current_data = polling_service.get_current_data()
        
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "polling_service": "running" if current_data else "initializing",
            "monitored_printers": len(settings.PRINTER_SERIALS),
            "last_update": current_data.last_update.isoformat() if current_data else None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
