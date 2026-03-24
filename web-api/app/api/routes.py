"""
API ?쇱슦??
==========
- REST API ?붾뱶?ъ씤??
- WebSocket ?ㅼ떆媛??낅뜲?댄듃
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
    PrintHistoryResponse, PrintStatus, now_kst
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ===========================================
# ??쒕낫??API
# ===========================================

@router.get(
    "/dashboard",
    response_model=DashboardData,
    tags=["Dashboard"],
    summary="??쒕낫???곗씠??議고쉶",
    description="4? ?꾨┛?곗쓽 ?ㅼ떆媛??곹깭 ?붿빟 ?뺣낫瑜?諛섑솚?⑸땲??"
)
async def get_dashboard():
    """
    ??쒕낫???곗씠??議고쉶
    
    Returns:
        - printers: ?꾨┛?곕퀎 ?붿빟 ?뺣낫 (?곹깭, 吏꾪뻾瑜? ?덉쭊 ?붾웾 ??
        - ?듦퀎: 珥??꾨┛???? 異쒕젰 以??湲?以??먮윭/?ㅽ봽?쇱씤 ??
    """
    try:
        polling_service = await get_polling_service()
        data = polling_service.get_current_data()
        
        if not data:
            return DashboardData(
                printers=[],
                total_printers=0,
                printers_printing=0,
                printers_idle=0,
                printers_error=0,
                printers_offline=0,
                last_update=now_kst(),
            )
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"??쒕낫??議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# ?꾨┛??API
# ===========================================

@router.get(
    "/printers",
    response_model=List[PrinterSummary],
    tags=["Printers"],
    summary="?꾨┛??紐⑸줉 議고쉶",
    description="紐⑤땲?곕쭅 以묒씤 紐⑤뱺 ?꾨┛?곗쓽 ?곹깭瑜?議고쉶?⑸땲??"
)
async def get_printers():
    """?꾨┛??紐⑸줉 議고쉶"""
    try:
        polling_service = await get_polling_service()
        data = polling_service.get_current_data()
        
        if not data:
            return []
        
        return data.printers
        
    except Exception as e:
        logger.error(f"?꾨┛??紐⑸줉 議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}",
    response_model=PrinterSummary,
    tags=["Printers"],
    summary="?뱀젙 ?꾨┛???곹깭 議고쉶",
    description="?쒕━??踰덊샇濡??뱀젙 ?꾨┛?곗쓽 ?곸꽭 ?곹깭瑜?議고쉶?⑸땲??"
)
async def get_printer(serial: str):
    """?뱀젙 ?꾨┛???곹깭 議고쉶"""
    try:
        polling_service = await get_polling_service()
        summary = polling_service.get_printer_summary(serial)
        
        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"Printer not found: {serial}"
            )
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"?꾨┛??議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}/refresh",
    response_model=PrinterSummary,
    tags=["Printers"],
    summary="?꾨┛???곹깭 ?덈줈怨좎묠",
    description="?대쭅 二쇨린? 愿怨꾩뾾??利됱떆 ?꾨┛???곹깭瑜?媛깆떊?⑸땲??"
)
async def refresh_printer(serial: str):
    """?꾨┛???곹깭 利됱떆 ?덈줈怨좎묠"""
    try:
        client = await get_formlabs_client()
        printer = await client.get_printer(serial)
        
        if not printer:
            raise HTTPException(
                status_code=404,
                detail=f"Printer not found: {serial}"
            )
        
        return client.printer_to_summary(printer)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"?꾨┛???덈줈怨좎묠 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# ?꾨┛???대젰 API
# ===========================================

@router.get(
    "/prints",
    response_model=PrintHistoryResponse,
    tags=["Print History"],
    summary="?꾨┛???대젰 議고쉶",
    description="?꾩껜 ?꾨┛???대젰??議고쉶?⑸땲?? ?꾪꽣留?媛??"
)
async def get_print_history(
    printer_serial: Optional[str] = Query(None, description="Filter by printer serial"),
    status: Optional[PrintStatus] = Query(None, description="Filter by print status"),
    date_from: Optional[datetime] = Query(None, description="?쒖옉 ?좎쭨 (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="醫낅즺 ?좎쭨 (ISO 8601)"),
    page: int = Query(1, ge=1, description="?섏씠吏 踰덊샇"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
):
    """?꾨┛???대젰 議고쉶"""
    try:
        client = await get_formlabs_client()
        
        # ?꾩껜 ?먮뒗 ?뱀젙 ?꾨┛???대젰 議고쉶
        items = await client.get_print_history(
            printer_serial=printer_serial,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=page_size * page  # 媛꾨떒???섏씠吏?ㅼ씠??
        )
        
        # ?섏씠吏?ㅼ씠???곸슜
        start_idx = (page - 1) * page_size
        paginated_items = items[start_idx:start_idx + page_size]
        
        return PrintHistoryResponse(
            items=paginated_items,
            total_count=len(items),
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"?꾨┛???대젰 議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/printers/{serial}/prints",
    response_model=List[PrintHistoryItem],
    tags=["Print History"],
    summary="?뱀젙 ?꾨┛???대젰 議고쉶",
    description="?뱀젙 ?꾨┛?곗쓽 ?꾨┛???대젰??議고쉶?⑸땲??"
)
async def get_printer_history(
    serial: str,
    limit: int = Query(20, ge=1, le=100, description="Max history items"),
):
    """?뱀젙 ?꾨┛???대젰 議고쉶"""
    try:
        client = await get_formlabs_client()
        items = await client.get_print_history(
            printer_serial=serial,
            limit=limit
        )
        return items
        
    except Exception as e:
        logger.error(f"?꾨┛???대젰 議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# ?듦퀎 API
# ===========================================

@router.get(
    "/statistics",
    tags=["Statistics"],
    summary="?꾨┛???듦퀎 議고쉶",
    description="湲곌컙蹂??꾨┛???듦퀎瑜?議고쉶?⑸땲??"
)
async def get_statistics(
    printer_serial: Optional[str] = Query(None, description="Filter by printer serial"),
    date_from: Optional[datetime] = Query(None, description="?쒖옉 ?좎쭨 (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="醫낅즺 ?좎쭨 (ISO 8601)"),
):
    """?꾨┛???듦퀎 議고쉶 (?щ즺 ?ъ슜?? ?쇰퀎 異쒕젰 異붿씠, ?꾨┛?곕퀎 ?듦퀎)"""
    try:
        client = await get_formlabs_client()
        polling_service = await get_polling_service()

        # ?꾩껜 ?대젰 議고쉶
        items = await client.get_print_history(
            printer_serial=printer_serial,
            date_from=date_from,
            date_to=date_to,
            limit=500
        )

        # 1. Material Usage 吏묎퀎
        material_usage: dict = {}
        for item in items:
            code = item.material_code or 'UNKNOWN'
            name = item.material_name or code
            ml = item.volume_ml or 0
            if code not in material_usage:
                material_usage[code] = {"code": code, "name": name, "total_ml": 0, "count": 0}
            material_usage[code]["total_ml"] += ml
            material_usage[code]["count"] += 1

        # 2. Prints Over Time (?쇰퀎 吏묎퀎)
        daily_counts: dict = {}
        for item in items:
            if item.started_at:
                day = item.started_at.strftime('%Y-%m-%d') if isinstance(item.started_at, datetime) else str(item.started_at)[:10]
                if day not in daily_counts:
                    daily_counts[day] = 0
                daily_counts[day] += 1

        # ?좎쭨???뺣젹
        sorted_daily = sorted(daily_counts.items())

        # 3. ?꾨┛?곕퀎 ?듦퀎
        printer_stats: dict = {}
        current_data = polling_service.get_current_data()
        printer_names = {}
        if current_data:
            for p in current_data.printers:
                printer_names[p.serial] = p.name

        for item in items:
            serial = item.printer_serial
            if serial not in printer_stats:
                printer_stats[serial] = {
                    "serial": serial,
                    "name": printer_names.get(serial, serial),
                    "total_prints": 0,
                    "completed": 0,
                    "failed": 0,
                    "total_duration_minutes": 0,
                    "total_material_ml": 0,
                    "print_days": set(),
                }
            stats = printer_stats[serial]
            stats["total_prints"] += 1
            if item.status and item.status.value == "FINISHED":
                stats["completed"] += 1
            elif item.status and item.status.value in ("ERROR", "ABORTED"):
                stats["failed"] += 1
            if item.duration_minutes and item.duration_minutes > 0:
                stats["total_duration_minutes"] += item.duration_minutes
            if item.volume_ml:
                stats["total_material_ml"] += item.volume_ml
            if item.started_at:
                day_str = item.started_at.strftime('%Y-%m-%d') if isinstance(item.started_at, datetime) else str(item.started_at)[:10]
                stats["print_days"].add(day_str)

        # set??count濡?蹂??
        for stats in printer_stats.values():
            stats["days_printed"] = len(stats["print_days"])
            del stats["print_days"]
            # 媛?숇쪧 怨꾩궛 (議고쉶 湲곌컙 ?鍮?
            if date_from and date_to:
                total_days = max((date_to - date_from).days, 1)
            elif sorted_daily:
                from datetime import datetime as dt
                first = dt.fromisoformat(sorted_daily[0][0])
                last = dt.fromisoformat(sorted_daily[-1][0])
                total_days = max((last - first).days + 1, 1)
            else:
                total_days = 90
            stats["total_days"] = total_days
            stats["utilization_percent"] = round(
                (stats["total_duration_minutes"] / 60) / (total_days * 24) * 100, 1
            )
            stats["total_material_ml"] = round(stats["total_material_ml"], 1)

        total_ml = sum(m["total_ml"] for m in material_usage.values())

        return {
            "total_prints": len(items),
            "total_material_ml": round(total_ml, 1),
            "material_usage": list(material_usage.values()),
            "prints_over_time": [{"date": d, "count": c} for d, c in sorted_daily],
            "printer_stats": list(printer_stats.values()),
        }

    except Exception as e:
        logger.error(f"?듦퀎 議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# ?쒖뒪??API
# ===========================================

@router.get(
    "/system/token-status",
    tags=["System"],
    summary="API ?좏겙 ?곹깭",
    description="Formlabs API ?몄쬆 ?좏겙 ?곹깭瑜??뺤씤?⑸땲??"
)
async def get_token_status():
    """?좏겙 ?곹깭 ?뺤씤"""
    try:
        auth = await get_auth_manager()
        return auth.token_status
        
    except Exception as e:
        logger.error(f"?좏겙 ?곹깭 ?뺤씤 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/system/debug/raw-printer/{serial}",
    tags=["System"],
    summary="?꾨┛???먮낯 ?곗씠??議고쉶 (?붾쾭洹몄슜)",
    description="Formlabs API?먯꽌 諛쏆? ?먮낯 ?곗씠?곕? ?뺤씤?⑸땲??"
)
async def get_raw_printer_data(serial: str):
    """Formlabs API ?먮낯 ?묐떟 ?뺤씤 (?붾쾭洹몄슜)"""
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
        logger.error(f"?먮낯 ?곗씠??議고쉶 ?ㅻ쪟: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/system/config",
    tags=["System"],
    summary="?쒖뒪???ㅼ젙 議고쉶",
    description="?꾩옱 ?쒖뒪???ㅼ젙??議고쉶?⑸땲??(誘쇨컧?뺣낫 ?쒖쇅)."
)
async def get_system_config():
    """?쒖뒪???ㅼ젙 議고쉶 (誘쇨컧?뺣낫 ?쒖쇅)"""
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
# WebSocket ?ㅼ떆媛??낅뜲?댄듃
# ===========================================

class ConnectionManager:
    """WebSocket ?곌껐 愿由ъ옄"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"?뵆 WebSocket ?곌껐 (珥?{len(self.active_connections)}媛?")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"?뵆 WebSocket ?곌껐 ?댁젣 (珥?{len(self.active_connections)}媛?")
    
    async def broadcast(self, data: dict):
        """紐⑤뱺 ?곌껐???곗씠???꾩넚"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)
        
        # ?딆뼱吏??곌껐 ?뺣━
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket ?ㅼ떆媛??낅뜲?댄듃
    
    ?곌껐 ???먮룞?쇰줈 ??쒕낫???곗씠?곕? 二쇨린?곸쑝濡??꾩넚?⑸땲??
    
    硫붿떆吏 ???
    - dashboard_update: ??쒕낫???꾩껜 ?곗씠??
    - notification: ?뚮┝ (?꾨┛???꾨즺, ?먮윭 ??
    """
    await manager.connect(websocket)
    
    try:
        # 珥덇린 ?곗씠???꾩넚
        polling_service = await get_polling_service()
        initial_data = polling_service.get_current_data()
        
        if initial_data:
            await websocket.send_json({
                "type": "dashboard_update",
                "data": initial_data.model_dump(mode="json")
            })
        
        # ?낅뜲?댄듃 ?몃뱾???깅줉
        async def send_update(data: DashboardData):
            try:
                await websocket.send_json({
                    "type": "dashboard_update",
                    "data": data.model_dump(mode="json")
                })
            except Exception:
                pass
        
        polling_service.on_update(send_update)
        
        # ?곌껐 ?좎? (?대씪?댁뼵??硫붿떆吏 ?湲?
        while True:
            try:
                # ?대씪?댁뼵??硫붿떆吏 ?섏떊 (ping/pong ?먮뒗 紐낅졊)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # 60珥???꾩븘??
                )
                
                # ping ?묐떟
                if data == "ping":
                    await websocket.send_text("pong")
                
            except asyncio.TimeoutError:
                # ??꾩븘????ping ?꾩넚
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket ?ㅻ쪟: {e}")
    finally:
        manager.disconnect(websocket)

