"""
Vision DB 모델
==============
SQLAlchemy ORM 모델 (vision_cameras, vision_events)
"""

from sqlalchemy import Column, String, Integer, Float, DateTime
from sqlalchemy.sql import func
import uuid

from app.local.models import Base


class VisionCamera(Base):
    """카메라 등록 정보"""
    __tablename__ = "vision_cameras"

    camera_id = Column(String(20), primary_key=True)  # wash_1, wash_2, cure_1, cure_2
    device_type = Column(String(10), nullable=False, index=True)  # wash / cure
    device_id = Column(Integer, nullable=False)  # 1 / 2
    name = Column(String(50), nullable=False)  # 표시 이름

    # 현재 상태
    status = Column(String(20), default="offline")
    confidence = Column(Float, default=0.0)
    is_online = Column(Integer, default=0)  # 0/1

    # 카메라 메타 정보
    firmware_version = Column(String(20), nullable=True)
    model_name = Column(String(100), nullable=True)
    ip_address = Column(String(15), nullable=True)
    wifi_rssi = Column(Integer, nullable=True)

    # 타임스탬프
    last_seen = Column(DateTime(timezone=True), nullable=True)
    last_status_change = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<VisionCamera {self.camera_id} ({self.status})>"


class VisionEvent(Base):
    """상태 변경 이벤트 이력"""
    __tablename__ = "vision_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String(20), nullable=False, index=True)
    device_type = Column(String(10), nullable=False, index=True)
    device_id = Column(Integer, nullable=False)
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<VisionEvent {self.camera_id}: {self.previous_status} -> {self.new_status}>"
