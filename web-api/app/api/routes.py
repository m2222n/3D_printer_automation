"""
API 라우터
==========
- REST API 엔드포인트
- WebSocket 실시간 업데이트
"""

import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query

from app.core.config import get_settings
from app.core.auth import get_auth_manager
from app.services.formlabs_client import get_formlabs_client
from app.services.polling_service import get_polling_service
from app.schemas.printer import (
    PrinterSummary, DashboardData, PrintHistoryItem,
    PrintHistoryResponse, PrintStatus
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ===========================================
# 대시보드 API
# ===========================================

@router.get(
    "/dashboard",
    response_model=DashboardData,
    tags=["Dashboard"],
    summary="대시보드 데이터 조회",
    description="4대 프린터의 실시간 상태 요약 정보를 반환합니다."
)
async def get_dashboard():
    """
    대시보드 데이터 조회
    
    Returns:
        - printers: 프린터별 요약 정보 (상태, 진행률, 레진 잔량 등)
        - 통계: 총 프린터 수, 출력 중/대기 중/에러/오프라인 수
    """
    try:
        polling_service = await get_polling_service()
        data = polling_service.get_current_data()
        
        if not data:
            raise HTTPException(
                status_code=503,
                detail="데이터 초기화 중입니다. 잠시 후 다시 시도해주세요."
            )
        
        return data
        
    except Exception as e:
        logger.error(f"대시보드 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# 프린터 API
# ===========================================

@router.get(
    "/printers",
    response_model=List[PrinterSummary],
    tags=["Printers"],
    summary="프린터 목록 조회",
    description="모니터링 중인 모든 프린터의 상태를 조회합니다."
)
async def get_printers():
    """프린터 목록 조회"""
    try:
        polling_service = await get_polling_service()
        data = polling_service.get_current_data()
        
        if not data:
            return []
        
        return data.printers
        
    except Exception as e:
        logger.error(f"프린터 목록 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}",
    response_model=PrinterSummary,
    tags=["Printers"],
    summary="특정 프린터 상태 조회",
    description="시리얼 번호로 특정 프린터의 상세 상태를 조회합니다."
)
async def get_printer(serial: str):
    """특정 프린터 상태 조회"""
    try:
        polling_service = await get_polling_service()
        summary = polling_service.get_printer_summary(serial)
        
        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"프린터를 찾을 수 없습니다: {serial}"
            )
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"프린터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}/refresh",
    response_model=PrinterSummary,
    tags=["Printers"],
    summary="프린터 상태 새로고침",
    description="폴링 주기와 관계없이 즉시 프린터 상태를 갱신합니다."
)
async def refresh_printer(serial: str):
    """프린터 상태 즉시 새로고침"""
    try:
        client = await get_formlabs_client()
        printer = await client.get_printer(serial)
        
        if not printer:
            raise HTTPException(
                status_code=404,
                detail=f"프린터를 찾을 수 없습니다: {serial}"
            )
        
        return client.printer_to_summary(printer)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"프린터 새로고침 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# 프린트 이력 API
# ===========================================

@router.get(
    "/prints",
    response_model=PrintHistoryResponse,
    tags=["Print History"],
    summary="프린트 이력 조회",
    description="전체 프린트 이력을 조회합니다. 필터링 가능."
)
async def get_print_history(
    printer_serial: Optional[str] = Query(None, description="특정 프린터로 필터링"),
    status: Optional[PrintStatus] = Query(None, description="상태로 필터링"),
    date_from: Optional[datetime] = Query(None, description="시작 날짜 (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="종료 날짜 (ISO 8601)"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지당 항목 수")
):
    """프린트 이력 조회"""
    try:
        client = await get_formlabs_client()
        
        # 전체 또는 특정 프린터 이력 조회
        items = await client.get_print_history(
            printer_serial=printer_serial,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=page_size * page  # 간단한 페이지네이션
        )
        
        # 페이지네이션 적용
        start_idx = (page - 1) * page_size
        paginated_items = items[start_idx:start_idx + page_size]
        
        return PrintHistoryResponse(
            items=paginated_items,
            total_count=len(items),
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"프린트 이력 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}/prints",
    response_model=List[PrintHistoryItem],
    tags=["Print History"],
    summary="특정 프린터 이력 조회",
    description="특정 프린터의 프린트 이력을 조회합니다."
)
async def get_printer_history(
    serial: str,
    limit: int = Query(20, ge=1, le=100, description="조회할 항목 수")
):
    """특정 프린터 이력 조회"""
    try:
        client = await get_formlabs_client()
        items = await client.get_print_history(
            printer_serial=serial,
            limit=limit
        )
        return items
        
    except Exception as e:
        logger.error(f"프린터 이력 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# 시스템 API
# ===========================================

@router.get(
    "/system/token-status",
    tags=["System"],
    summary="API 토큰 상태",
    description="Formlabs API 인증 토큰 상태를 확인합니다."
)
async def get_token_status():
    """토큰 상태 확인"""
    try:
        auth = await get_auth_manager()
        return auth.token_status
        
    except Exception as e:
        logger.error(f"토큰 상태 확인 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/system/debug/raw-printer/{serial}",
    tags=["System"],
    summary="프린터 원본 데이터 조회 (디버그용)",
    description="Formlabs API에서 받은 원본 데이터를 확인합니다."
)
async def get_raw_printer_data(serial: str):
    """Formlabs API 원본 응답 확인 (디버그용)"""
    try:
        from app.core.auth import get_auth_manager
        import httpx

        auth = await get_auth_manager()
        token = await auth.get_valid_token()
        settings = get_settings()

        url = f"{settings.FORMLABS_API_BASE_URL}/developer/v1/printers/{serial}/"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"bearer {token}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": response.status_code, "detail": response.text}

    except Exception as e:
        logger.error(f"원본 데이터 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/system/config",
    tags=["System"],
    summary="시스템 설정 조회",
    description="현재 시스템 설정을 조회합니다 (민감정보 제외)."
)
async def get_system_config():
    """시스템 설정 조회 (민감정보 제외)"""
    settings = get_settings()
    
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "polling_interval_seconds": settings.POLLING_INTERVAL_SECONDS,
        "monitored_printers": len(settings.PRINTER_SERIALS),
        "printer_serials": settings.PRINTER_SERIALS,
        "notifications": {
            "on_print_complete": settings.NOTIFY_ON_PRINT_COMPLETE,
            "on_print_error": settings.NOTIFY_ON_PRINT_ERROR,
            "on_low_resin": settings.NOTIFY_ON_LOW_RESIN,
            "low_resin_threshold_ml": settings.LOW_RESIN_THRESHOLD_ML,
        }
    }


# ===========================================
# WebSocket 실시간 업데이트
# ===========================================

class ConnectionManager:
    """WebSocket 연결 관리자"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🔌 WebSocket 연결 (총 {len(self.active_connections)}개)")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"🔌 WebSocket 연결 해제 (총 {len(self.active_connections)}개)")
    
    async def broadcast(self, data: dict):
        """모든 연결에 데이터 전송"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)
        
        # 끊어진 연결 정리
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 실시간 업데이트
    
    연결 후 자동으로 대시보드 데이터를 주기적으로 전송합니다.
    
    메시지 타입:
    - dashboard_update: 대시보드 전체 데이터
    - notification: 알림 (프린트 완료, 에러 등)
    """
    await manager.connect(websocket)
    
    try:
        # 초기 데이터 전송
        polling_service = await get_polling_service()
        initial_data = polling_service.get_current_data()
        
        if initial_data:
            await websocket.send_json({
                "type": "dashboard_update",
                "data": initial_data.model_dump(mode="json")
            })
        
        # 업데이트 핸들러 등록
        async def send_update(data: DashboardData):
            try:
                await websocket.send_json({
                    "type": "dashboard_update",
                    "data": data.model_dump(mode="json")
                })
            except Exception:
                pass
        
        polling_service.on_update(send_update)
        
        # 연결 유지 (클라이언트 메시지 대기)
        while True:
            try:
                # 클라이언트 메시지 수신 (ping/pong 또는 명령)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # 60초 타임아웃
                )
                
                # ping 응답
                if data == "ping":
                    await websocket.send_text("pong")
                
            except asyncio.TimeoutError:
                # 타임아웃 시 ping 전송
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
    finally:
        manager.disconnect(websocket)
