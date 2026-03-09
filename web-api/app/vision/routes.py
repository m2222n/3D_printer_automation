"""
Vision REST API + WebSocket 라우터
===================================
/api/v1/vision/* 엔드포인트
"""

import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query

from app.core.config import get_settings
from app.local.database import get_local_db_session
from app.vision.models import VisionEvent
from app.vision.schemas import (
    CameraListResponse,
    CameraResponse,
    DeviceListResponse,
    DeviceResponse,
    EventListResponse,
    EventResponse,
    SimulateRequest,
    SimulateScenarioRequest,
    VisionHealthResponse,
)
from app.vision.camera_manager import get_camera_manager
from app.vision.mqtt_client import get_mqtt_client

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/vision", tags=["Vision"])


# ===== Health =====

@router.get("/health", response_model=VisionHealthResponse)
async def vision_health():
    """Vision 모듈 상태 확인"""
    settings = get_settings()
    manager = get_camera_manager()
    mqtt = get_mqtt_client()
    cameras = manager.get_all_cameras()

    return VisionHealthResponse(
        status="healthy",
        mqtt_connected=mqtt.is_connected,
        cameras_total=len(cameras),
        cameras_online=sum(1 for c in cameras if c.is_online),
        simulator_enabled=settings.VISION_SIMULATOR_ENABLED,
    )


# ===== Cameras =====

@router.get("/cameras", response_model=CameraListResponse)
async def list_cameras():
    """등록된 카메라 목록 + 현재 상태"""
    manager = get_camera_manager()
    cameras = manager.get_all_cameras()

    return CameraListResponse(
        cameras=cameras,
        total=len(cameras),
        online=sum(1 for c in cameras if c.is_online),
        offline=sum(1 for c in cameras if not c.is_online),
    )


@router.get("/cameras/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: str):
    """특정 카메라 상세"""
    manager = get_camera_manager()
    camera = manager.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail=f"카메라 '{camera_id}' 없음")
    return camera


# ===== Devices =====

@router.get("/devices", response_model=DeviceListResponse)
async def list_devices():
    """세척기/경화기 장비 상태 목록"""
    manager = get_camera_manager()
    cameras = manager.get_all_cameras()
    now = datetime.now(KST)

    devices = []
    for c in cameras:
        elapsed = None
        if c.last_status_change:
            elapsed = int((now - c.last_status_change).total_seconds())

        devices.append(DeviceResponse(
            type=c.device_type,
            id=c.device_id,
            name=c.name,
            status=c.status,
            camera_id=c.camera_id,
            is_online=c.is_online,
            last_status_change=c.last_status_change,
            elapsed_since_change_s=elapsed,
        ))

    return DeviceListResponse(devices=devices)


@router.get("/devices/{device_type}/{device_id}", response_model=DeviceResponse)
async def get_device(device_type: str, device_id: int):
    """특정 장비 상세 (예: wash/1)"""
    manager = get_camera_manager()
    camera_id = f"{device_type}_{device_id}"
    c = manager.get_camera(camera_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"장비 '{device_type}/{device_id}' 없음")

    now = datetime.now(KST)
    elapsed = None
    if c.last_status_change:
        elapsed = int((now - c.last_status_change).total_seconds())

    return DeviceResponse(
        type=c.device_type,
        id=c.device_id,
        name=c.name,
        status=c.status,
        camera_id=c.camera_id,
        is_online=c.is_online,
        last_status_change=c.last_status_change,
        elapsed_since_change_s=elapsed,
    )


# ===== Events =====

@router.get("/events", response_model=EventListResponse)
async def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    device_type: Optional[str] = None,
    camera_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """상태 변경 이벤트 이력"""
    with get_local_db_session() as db:
        query = db.query(VisionEvent)

        if device_type:
            query = query.filter(VisionEvent.device_type == device_type)
        if camera_id:
            query = query.filter(VisionEvent.camera_id == camera_id)
        if status:
            query = query.filter(VisionEvent.new_status == status)

        total = query.count()
        events = (
            query
            .order_by(VisionEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return EventListResponse(
            events=[
                EventResponse(
                    id=e.id,
                    camera_id=e.camera_id,
                    device_type=e.device_type,
                    device_id=e.device_id,
                    previous_status=e.previous_status,
                    new_status=e.new_status,
                    confidence=e.confidence or 0.0,
                    timestamp=e.created_at,
                )
                for e in events
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/events/latest")
async def latest_events(limit: int = Query(default=10, ge=1, le=50)):
    """최근 이벤트 N건"""
    with get_local_db_session() as db:
        events = (
            db.query(VisionEvent)
            .order_by(VisionEvent.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            EventResponse(
                id=e.id,
                camera_id=e.camera_id,
                device_type=e.device_type,
                device_id=e.device_id,
                previous_status=e.previous_status,
                new_status=e.new_status,
                confidence=e.confidence or 0.0,
                timestamp=e.created_at,
            )
            for e in events
        ]


# ===== Simulator =====

@router.post("/simulate")
async def simulate_status(req: SimulateRequest):
    """시뮬레이터: 가짜 상태 변경 MQTT 발행"""
    settings = get_settings()
    if not settings.VISION_SIMULATOR_ENABLED:
        raise HTTPException(status_code=403, detail="시뮬레이터 비활성화 상태")

    from app.vision.simulator import publish_simulated_status
    await publish_simulated_status(req.camera_id, req.status, req.confidence)

    return {"message": f"시뮬레이션 전송: {req.camera_id} -> {req.status}"}


@router.post("/simulate/scenario")
async def simulate_scenario(req: SimulateScenarioRequest):
    """시뮬레이터: 시나리오 모드 (백그라운드)"""
    settings = get_settings()
    if not settings.VISION_SIMULATOR_ENABLED:
        raise HTTPException(status_code=403, detail="시뮬레이터 비활성화 상태")

    from app.vision.simulator import run_scenario
    asyncio.create_task(run_scenario(req.scenario, req.interval_seconds))

    return {"message": f"시나리오 '{req.scenario}' 시작 (간격: {req.interval_seconds}초)"}


# ===== WebSocket =====

@router.websocket("/ws")
async def vision_websocket(websocket: WebSocket):
    """Vision 실시간 상태 WebSocket"""
    await websocket.accept()
    manager = get_camera_manager()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    manager.register_ws(queue)

    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Vision WebSocket 오류: {e}")
    finally:
        manager.unregister_ws(queue)
