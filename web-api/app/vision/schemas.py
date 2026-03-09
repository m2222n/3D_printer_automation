"""
Vision Pydantic 스키마
=====================
요청/응답 모델 정의
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DeviceType(str, Enum):
    WASH = "wash"
    CURE = "cure"


class DeviceStatus(str, Enum):
    WASH_IDLE = "wash_idle"
    WASH_RUNNING = "wash_running"
    WASH_COMPLETE = "wash_complete"
    CURE_IDLE = "cure_idle"
    CURE_RUNNING = "cure_running"
    CURE_COMPLETE = "cure_complete"
    OFFLINE = "offline"
    ERROR = "error"


# ===== MQTT 메시지 스키마 =====

class MQTTStatusMessage(BaseModel):
    """MQTT 상태 메시지 (카메라 -> 서버)"""
    camera_id: str
    device_type: str
    device_id: int
    status: str
    confidence: float = 0.0
    timestamp: str
    consecutive_count: int = 0
    fps: float = 0.0
    mem_free: int = 0


class MQTTHeartbeatMessage(BaseModel):
    """MQTT 하트비트 메시지"""
    camera_id: str
    uptime_s: int = 0
    mem_free: int = 0
    temperature_c: float = 0.0
    wifi_rssi: int = 0
    timestamp: str


class MQTTCameraInfoMessage(BaseModel):
    """MQTT 카메라 정보 메시지 (부팅 시 1회)"""
    camera_id: str
    firmware_version: str = ""
    model_name: str = ""
    model_classes: list[str] = []
    ip_address: str = ""


# ===== API 응답 스키마 =====

class CameraResponse(BaseModel):
    """카메라 상태 응답"""
    camera_id: str
    device_type: str
    device_id: int
    name: str
    status: str
    confidence: float
    is_online: bool
    last_seen: Optional[datetime] = None
    last_status_change: Optional[datetime] = None
    firmware_version: Optional[str] = None
    wifi_rssi: Optional[int] = None

    class Config:
        from_attributes = True


class CameraListResponse(BaseModel):
    """카메라 목록 응답"""
    cameras: list[CameraResponse]
    total: int
    online: int
    offline: int


class DeviceResponse(BaseModel):
    """장비 상태 응답"""
    type: str
    id: int
    name: str
    status: str
    camera_id: str
    is_online: bool
    last_status_change: Optional[datetime] = None
    elapsed_since_change_s: Optional[int] = None


class DeviceListResponse(BaseModel):
    """장비 목록 응답"""
    devices: list[DeviceResponse]


class EventResponse(BaseModel):
    """이벤트 응답"""
    id: str
    camera_id: str
    device_type: str
    device_id: int
    previous_status: Optional[str] = None
    new_status: str
    confidence: float
    timestamp: datetime

    class Config:
        from_attributes = True


class EventListResponse(BaseModel):
    """이벤트 목록 응답"""
    events: list[EventResponse]
    total: int
    page: int
    page_size: int


class SimulateRequest(BaseModel):
    """시뮬레이터 요청"""
    camera_id: str = Field(..., description="카메라 ID (wash_1, wash_2, cure_1, cure_2)")
    status: str = Field(..., description="상태 값 (wash_running, wash_complete 등)")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class SimulateScenarioRequest(BaseModel):
    """시뮬레이터 시나리오 요청"""
    scenario: str = Field(default="full_cycle", description="시나리오 이름")
    interval_seconds: int = Field(default=10, ge=1, le=300)


class VisionHealthResponse(BaseModel):
    """Vision 모듈 상태 응답"""
    status: str
    mqtt_connected: bool
    cameras_total: int
    cameras_online: int
    simulator_enabled: bool
