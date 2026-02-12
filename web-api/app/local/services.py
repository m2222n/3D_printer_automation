"""
프리셋 관리 서비스
==================
프리셋 CRUD 및 관리 로직
"""

import logging
from typing import Optional, List
from sqlalchemy.orm import Session
import uuid

from app.local.models import Preset, PrintJob
from app.local.schemas import (
    PresetCreate, PresetUpdate, PresetResponse,
    PrintSettings, PrintJobCreate, PrintJobResponse, PrintJobStatus
)

logger = logging.getLogger(__name__)


class PresetService:
    """프리셋 관리 서비스"""

    def __init__(self, db: Session):
        self.db = db

    # ===========================================
    # 프리셋 CRUD
    # ===========================================

    def create(self, data: PresetCreate) -> PresetResponse:
        """프리셋 생성"""
        preset = Preset(
            id=str(uuid.uuid4()),
            name=data.name,
            part_type=data.part_type,
            description=data.description,
            settings=data.settings.model_dump(),
            stl_filename=data.stl_filename
        )
        self.db.add(preset)
        self.db.commit()
        self.db.refresh(preset)

        logger.info(f"✅ 프리셋 생성: {preset.name} ({preset.part_type})")
        return self._to_response(preset)

    def get(self, preset_id: str) -> Optional[PresetResponse]:
        """프리셋 조회"""
        preset = self.db.query(Preset).filter(Preset.id == preset_id).first()
        if not preset:
            return None
        return self._to_response(preset)

    def get_by_part_type(self, part_type: str) -> Optional[PresetResponse]:
        """부품 타입으로 프리셋 조회"""
        preset = self.db.query(Preset).filter(Preset.part_type == part_type).first()
        if not preset:
            return None
        return self._to_response(preset)

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        part_type: Optional[str] = None
    ) -> tuple[List[PresetResponse], int]:
        """프리셋 목록 조회"""
        query = self.db.query(Preset)

        if part_type:
            query = query.filter(Preset.part_type == part_type)

        total = query.count()
        presets = query.order_by(Preset.updated_at.desc()).offset(skip).limit(limit).all()

        return [self._to_response(p) for p in presets], total

    def update(self, preset_id: str, data: PresetUpdate) -> Optional[PresetResponse]:
        """프리셋 수정"""
        preset = self.db.query(Preset).filter(Preset.id == preset_id).first()
        if not preset:
            return None

        if data.name is not None:
            preset.name = data.name
        if data.part_type is not None:
            preset.part_type = data.part_type
        if data.description is not None:
            preset.description = data.description
        if data.settings is not None:
            preset.settings = data.settings.model_dump()
        if data.stl_filename is not None:
            preset.stl_filename = data.stl_filename

        self.db.commit()
        self.db.refresh(preset)

        logger.info(f"✅ 프리셋 수정: {preset.name}")
        return self._to_response(preset)

    def delete(self, preset_id: str) -> bool:
        """프리셋 삭제"""
        preset = self.db.query(Preset).filter(Preset.id == preset_id).first()
        if not preset:
            return False

        self.db.delete(preset)
        self.db.commit()

        logger.info(f"🗑️ 프리셋 삭제: {preset.name}")
        return True

    def increment_print_count(self, preset_id: str):
        """프린트 카운트 증가"""
        preset = self.db.query(Preset).filter(Preset.id == preset_id).first()
        if preset:
            preset.print_count += 1
            self.db.commit()

    def _to_response(self, preset: Preset) -> PresetResponse:
        """DB 모델을 응답 스키마로 변환"""
        return PresetResponse(
            id=preset.id,
            name=preset.name,
            part_type=preset.part_type,
            description=preset.description,
            settings=PrintSettings(**preset.settings),
            stl_filename=preset.stl_filename,
            created_at=preset.created_at,
            updated_at=preset.updated_at,
            print_count=preset.print_count
        )


class PrintJobService:
    """프린트 작업 관리 서비스"""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: PrintJobCreate, stl_filename: str, settings: PrintSettings) -> PrintJobResponse:
        """프린트 작업 생성"""
        job = PrintJob(
            id=str(uuid.uuid4()),
            preset_id=data.preset_id,
            stl_filename=stl_filename,
            printer_serial=data.printer_serial,
            status=PrintJobStatus.PENDING.value,
            settings=settings.model_dump(),
            scheduled_at=data.scheduled_at
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"✅ 프린트 작업 생성: {job.id[:8]}")
        return self._to_response(job)

    def get(self, job_id: str) -> Optional[PrintJobResponse]:
        """프린트 작업 조회"""
        job = self.db.query(PrintJob).filter(PrintJob.id == job_id).first()
        if not job:
            return None
        return self._to_response(job)

    def list(self, skip: int = 0, limit: int = 20) -> List[PrintJobResponse]:
        """프린트 작업 목록 조회"""
        jobs = (
            self.db.query(PrintJob)
            .order_by(PrintJob.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [self._to_response(j) for j in jobs]

    def update_status(
        self,
        job_id: str,
        status: PrintJobStatus,
        scene_id: Optional[str] = None,
        error_message: Optional[str] = None,
        estimated_print_time_ms: Optional[int] = None,
        estimated_material_ml: Optional[float] = None
    ) -> Optional[PrintJobResponse]:
        """프린트 작업 상태 업데이트"""
        job = self.db.query(PrintJob).filter(PrintJob.id == job_id).first()
        if not job:
            return None

        job.status = status.value
        if scene_id is not None:
            job.scene_id = scene_id
        if error_message is not None:
            job.error_message = error_message
        if estimated_print_time_ms is not None:
            job.estimated_print_time_ms = estimated_print_time_ms
        if estimated_material_ml is not None:
            job.estimated_material_ml = estimated_material_ml

        self.db.commit()
        self.db.refresh(job)

        logger.info(f"📝 프린트 작업 상태 변경: {job.id[:8]} -> {status.value}")
        return self._to_response(job)

    def _to_response(self, job: PrintJob) -> PrintJobResponse:
        """DB 모델을 응답 스키마로 변환"""
        return PrintJobResponse(
            id=job.id,
            preset_id=job.preset_id,
            stl_filename=job.stl_filename,
            printer_serial=job.printer_serial,
            status=PrintJobStatus(job.status),
            settings=PrintSettings(**job.settings),
            scene_id=job.scene_id,
            error_message=job.error_message,
            scheduled_at=job.scheduled_at,
            created_at=job.created_at,
            updated_at=job.updated_at
        )
