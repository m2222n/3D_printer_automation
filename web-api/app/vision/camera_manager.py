"""
카메라 상태 관리자
=================
- 카메라 온라인/오프라인 판단
- 상태 변경 이벤트 생성 + DB 저장
- WebSocket broadcast
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.config import get_settings
from app.local.database import get_local_db_session
from app.vision.models import VisionCamera, VisionEvent
from app.vision.schemas import (
    MQTTStatusMessage,
    MQTTHeartbeatMessage,
    MQTTCameraInfoMessage,
    CameraResponse,
)

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 기본 카메라 설정
DEFAULT_CAMERAS = {
    "wash_1": {"device_type": "wash", "device_id": 1, "name": "세척기 1호"},
    "wash_2": {"device_type": "wash", "device_id": 2, "name": "세척기 2호"},
    "cure_1": {"device_type": "cure", "device_id": 1, "name": "경화기 1호"},
    "cure_2": {"device_type": "cure", "device_id": 2, "name": "경화기 2호"},
}


class CameraManager:
    """카메라 상태 관리 싱글톤"""

    def __init__(self):
        self._ws_clients: list[asyncio.Queue] = []
        self._heartbeat_check_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """DB에 기본 카메라 레코드 생성 (없으면)"""
        with get_local_db_session() as db:
            for camera_id, info in DEFAULT_CAMERAS.items():
                existing = db.query(VisionCamera).filter_by(camera_id=camera_id).first()
                if not existing:
                    camera = VisionCamera(
                        camera_id=camera_id,
                        device_type=info["device_type"],
                        device_id=info["device_id"],
                        name=info["name"],
                        status="offline",
                        is_online=0,
                    )
                    db.add(camera)
            logger.info("Vision 카메라 DB 초기화 완료 (4대)")

    async def start_heartbeat_checker(self):
        """주기적으로 하트비트 타임아웃 체크"""
        self._heartbeat_check_task = asyncio.create_task(self._heartbeat_check_loop())

    async def stop_heartbeat_checker(self):
        if self._heartbeat_check_task:
            self._heartbeat_check_task.cancel()
            try:
                await self._heartbeat_check_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_check_loop(self):
        """하트비트 타임아웃 체크 루프"""
        settings = get_settings()
        timeout = settings.CAMERA_HEARTBEAT_TIMEOUT

        while True:
            try:
                await asyncio.sleep(15)  # 15초마다 체크
                now = datetime.now(KST)
                with get_local_db_session() as db:
                    online_cameras = db.query(VisionCamera).filter_by(is_online=1).all()
                    for cam in online_cameras:
                        if cam.last_seen and (now - cam.last_seen).total_seconds() > timeout:
                            logger.warning(f"카메라 {cam.camera_id} 하트비트 타임아웃 -> offline")
                            old_status = cam.status
                            cam.status = "offline"
                            cam.is_online = 0
                            cam.last_status_change = now

                            event = VisionEvent(
                                camera_id=cam.camera_id,
                                device_type=cam.device_type,
                                device_id=cam.device_id,
                                previous_status=old_status,
                                new_status="offline",
                                confidence=0.0,
                            )
                            db.add(event)
                            await self._broadcast_ws({
                                "type": "vision_status_change",
                                "data": {
                                    "camera_id": cam.camera_id,
                                    "device_type": cam.device_type,
                                    "device_id": cam.device_id,
                                    "status": "offline",
                                    "confidence": 0.0,
                                    "timestamp": now.isoformat(),
                                },
                            })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"하트비트 체크 오류: {e}")

    async def handle_status(self, msg: MQTTStatusMessage):
        """상태 메시지 처리"""
        now = datetime.now(KST)

        with get_local_db_session() as db:
            camera = db.query(VisionCamera).filter_by(camera_id=msg.camera_id).first()
            if not camera:
                # 미등록 카메라 -> 자동 등록
                camera = VisionCamera(
                    camera_id=msg.camera_id,
                    device_type=msg.device_type,
                    device_id=msg.device_id,
                    name=f"{msg.device_type} {msg.device_id}",
                )
                db.add(camera)

            old_status = camera.status
            camera.status = msg.status
            camera.confidence = msg.confidence
            camera.is_online = 1
            camera.last_seen = now

            # 상태 변경 시에만 이벤트 저장
            if old_status != msg.status:
                camera.last_status_change = now

                event = VisionEvent(
                    camera_id=msg.camera_id,
                    device_type=msg.device_type,
                    device_id=msg.device_id,
                    previous_status=old_status,
                    new_status=msg.status,
                    confidence=msg.confidence,
                )
                db.add(event)

                logger.info(
                    f"[{msg.camera_id}] 상태 변경: {old_status} -> {msg.status} "
                    f"(confidence: {msg.confidence:.2f})"
                )

                await self._broadcast_ws({
                    "type": "vision_status_change",
                    "data": {
                        "camera_id": msg.camera_id,
                        "device_type": msg.device_type,
                        "device_id": msg.device_id,
                        "status": msg.status,
                        "confidence": msg.confidence,
                        "timestamp": now.isoformat(),
                    },
                })

    async def handle_heartbeat(self, msg: MQTTHeartbeatMessage):
        """하트비트 메시지 처리"""
        now = datetime.now(KST)

        with get_local_db_session() as db:
            camera = db.query(VisionCamera).filter_by(camera_id=msg.camera_id).first()
            if not camera:
                return

            was_offline = camera.is_online == 0
            camera.is_online = 1
            camera.last_seen = now
            camera.wifi_rssi = msg.wifi_rssi

            if was_offline:
                logger.info(f"[{msg.camera_id}] 온라인 복귀")
                await self._broadcast_ws({
                    "type": "vision_camera_online",
                    "data": {
                        "camera_id": msg.camera_id,
                        "timestamp": now.isoformat(),
                    },
                })

    async def handle_camera_info(self, msg: MQTTCameraInfoMessage):
        """카메라 정보 메시지 처리 (부팅 시 1회)"""
        with get_local_db_session() as db:
            camera = db.query(VisionCamera).filter_by(camera_id=msg.camera_id).first()
            if not camera:
                return

            camera.firmware_version = msg.firmware_version
            camera.model_name = msg.model_name
            camera.ip_address = msg.ip_address
            camera.is_online = 1
            camera.last_seen = datetime.now(KST)

            logger.info(
                f"[{msg.camera_id}] 카메라 정보 등록: fw={msg.firmware_version}, "
                f"model={msg.model_name}, ip={msg.ip_address}"
            )

    def get_all_cameras(self) -> list[CameraResponse]:
        """모든 카메라 상태 조회"""
        with get_local_db_session() as db:
            cameras = db.query(VisionCamera).all()
            return [
                CameraResponse(
                    camera_id=c.camera_id,
                    device_type=c.device_type,
                    device_id=c.device_id,
                    name=c.name,
                    status=c.status,
                    confidence=c.confidence or 0.0,
                    is_online=bool(c.is_online),
                    last_seen=c.last_seen,
                    last_status_change=c.last_status_change,
                    firmware_version=c.firmware_version,
                    wifi_rssi=c.wifi_rssi,
                )
                for c in cameras
            ]

    def get_camera(self, camera_id: str) -> Optional[CameraResponse]:
        """특정 카메라 상태 조회"""
        with get_local_db_session() as db:
            c = db.query(VisionCamera).filter_by(camera_id=camera_id).first()
            if not c:
                return None
            return CameraResponse(
                camera_id=c.camera_id,
                device_type=c.device_type,
                device_id=c.device_id,
                name=c.name,
                status=c.status,
                confidence=c.confidence or 0.0,
                is_online=bool(c.is_online),
                last_seen=c.last_seen,
                last_status_change=c.last_status_change,
                firmware_version=c.firmware_version,
                wifi_rssi=c.wifi_rssi,
            )

    # WebSocket 관리
    def register_ws(self, queue: asyncio.Queue):
        self._ws_clients.append(queue)

    def unregister_ws(self, queue: asyncio.Queue):
        if queue in self._ws_clients:
            self._ws_clients.remove(queue)

    async def _broadcast_ws(self, message: dict):
        """모든 WebSocket 클라이언트에 메시지 브로드캐스트"""
        for q in self._ws_clients:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass


# 싱글톤
_camera_manager: Optional[CameraManager] = None


def get_camera_manager() -> CameraManager:
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
