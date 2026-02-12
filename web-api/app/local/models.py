"""
프리셋 DB 모델
==============
SQLAlchemy ORM 모델
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Preset(Base):
    """프리셋 DB 모델"""
    __tablename__ = "presets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, index=True)
    part_type = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # 프린트 설정 (JSON)
    settings = Column(JSON, nullable=False, default=dict)

    # 연결된 STL 파일
    stl_filename = Column(String(255), nullable=True)

    # 통계
    print_count = Column(Integer, default=0)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Preset {self.name} ({self.part_type})>"


class PrintJob(Base):
    """프린트 작업 DB 모델"""
    __tablename__ = "print_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    preset_id = Column(String(36), nullable=True)  # FK to presets
    stl_filename = Column(String(255), nullable=False)
    printer_serial = Column(String(100), nullable=False)

    # 상태
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)

    # PreFormServer 정보
    scene_id = Column(String(100), nullable=True)

    # 프린트 설정 스냅샷 (프리셋 변경 시에도 원래 설정 유지)
    settings = Column(JSON, nullable=False, default=dict)

    # 결과 정보
    estimated_print_time_ms = Column(Integer, nullable=True)
    estimated_material_ml = Column(Float, nullable=True)

    # 예약 출력 시간 (KST, None이면 즉시 출력)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # 타임스탬프
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PrintJob {self.id[:8]} - {self.status}>"
