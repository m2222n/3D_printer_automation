"""
프리셋 스키마
=============
부품별 프린트 설정 저장/관리
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class MaterialCode(str, Enum):
    """Formlabs 레진 종류"""
    GREY_V5 = "FLGPGR05"
    CLEAR_V5 = "FLGPCL05"
    WHITE_V5 = "FLGPWH05"
    BLACK_V5 = "FLGPBK05"
    TOUGH_1500 = "FLTO1500"
    TOUGH_2000 = "FLTOTL02"
    DURABLE = "FLDUCL01"
    FLEXIBLE_80A = "FLFX8001"
    ELASTIC_50A = "FLEL5001"


class SupportDensity(str, Enum):
    """서포트 밀도"""
    LIGHT = "light"
    NORMAL = "normal"
    HEAVY = "heavy"


class OrientationSettings(BaseModel):
    """모델 방향 설정"""
    x_rotation: float = 0.0
    y_rotation: float = 0.0
    z_rotation: float = 0.0


class SupportSettings(BaseModel):
    """서포트 설정"""
    density: SupportDensity = SupportDensity.NORMAL
    touchpoint_size: float = 0.5  # mm
    internal_supports: bool = False


class PrintSettings(BaseModel):
    """프린트 설정"""
    machine_type: str = "FORM-4-0"
    material_code: MaterialCode = MaterialCode.GREY_V5
    layer_thickness_mm: float = 0.05
    orientation: OrientationSettings = Field(default_factory=OrientationSettings)
    support: SupportSettings = Field(default_factory=SupportSettings)


# ===========================================
# 프리셋 CRUD 스키마
# ===========================================

class PresetBase(BaseModel):
    """프리셋 기본 정보"""
    name: str = Field(..., min_length=1, max_length=100, description="프리셋 이름")
    part_type: str = Field(..., min_length=1, max_length=50, description="부품 종류 (예: cover_a)")
    description: Optional[str] = Field(None, max_length=500, description="설명")


class PresetCreate(PresetBase):
    """프리셋 생성 요청"""
    settings: PrintSettings = Field(default_factory=PrintSettings)
    stl_filename: Optional[str] = None  # 연결된 STL 파일명


class PresetUpdate(BaseModel):
    """프리셋 수정 요청"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    part_type: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[PrintSettings] = None
    stl_filename: Optional[str] = None


class PresetResponse(PresetBase):
    """프리셋 응답"""
    id: str
    settings: PrintSettings
    stl_filename: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    print_count: int = 0  # 이 프리셋으로 출력한 횟수

    class Config:
        from_attributes = True


class PresetListResponse(BaseModel):
    """프리셋 목록 응답"""
    items: List[PresetResponse]
    total: int


# ===========================================
# 프린트 작업 스키마
# ===========================================

class PrintJobCreate(BaseModel):
    """프린트 작업 생성 요청"""
    preset_id: Optional[str] = None  # 프리셋 사용 시
    stl_file: Optional[str] = None  # 직접 업로드 시
    printer_serial: str = Field(..., description="대상 프린터 시리얼")
    copies: int = Field(default=1, ge=1, le=10, description="복사본 수")

    # 프리셋 없이 직접 설정 시
    settings: Optional[PrintSettings] = None


class PrintJobStatus(str, Enum):
    """프린트 작업 상태"""
    PENDING = "pending"
    PREPARING = "preparing"  # 서포트 생성 중
    READY = "ready"  # 전송 준비 완료
    SENDING = "sending"  # 프린터로 전송 중
    SENT = "sent"  # 전송 완료
    FAILED = "failed"


class PrintJobResponse(BaseModel):
    """프린트 작업 응답"""
    id: str
    preset_id: Optional[str]
    stl_filename: str
    printer_serial: str
    status: PrintJobStatus
    settings: PrintSettings
    scene_id: Optional[str] = None  # PreFormServer scene ID
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ===========================================
# PreFormServer 관련 스키마
# ===========================================

class DiscoveredPrinter(BaseModel):
    """검색된 프린터"""
    serial: str
    name: str
    ip_address: str
    machine_type: str
    is_online: bool


class SceneInfo(BaseModel):
    """PreFormServer Scene 정보"""
    scene_id: str
    machine_type: str
    material_code: str
    model_count: int
    estimated_print_time_ms: Optional[int] = None
    estimated_material_ml: Optional[float] = None
