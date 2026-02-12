"""
Formlabs 프린터 상태 스키마
============================
Web API 응답 데이터 구조 정의
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum

# 한국 표준시 (KST = UTC+9)
KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    """현재 한국 시간 반환"""
    return datetime.now(KST)


# ===========================================
# 열거형 정의
# ===========================================

class PrintStatus(str, Enum):
    """프린트 작업 상태"""
    QUEUED = "QUEUED"           # 대기열
    PREPRINT = "PREPRINT"       # 준비 중
    PRINTING = "PRINTING"       # 출력 중
    PAUSED = "PAUSED"           # 일시정지
    FINISHED = "FINISHED"       # 완료
    ABORTED = "ABORTED"         # 취소됨
    ERROR = "ERROR"             # 오류


class PrinterReadyState(str, Enum):
    """프린터 준비 상태"""
    READY = "READY"
    NOT_READY = "NOT_READY"
    # Formlabs API 실제 응답 값
    READY_TO_PRINT_READY = "READY_TO_PRINT_READY"
    READY_TO_PRINT_NOT_READY = "READY_TO_PRINT_NOT_READY"


class BuildPlatformState(str, Enum):
    """빌드 플랫폼 상태"""
    EMPTY = "EMPTY"
    HAS_PARTS = "HAS_PARTS"
    # Formlabs API 실제 응답 값
    BUILD_PLATFORM_CONTENTS_EMPTY = "BUILD_PLATFORM_CONTENTS_EMPTY"
    BUILD_PLATFORM_CONTENTS_HAS_PARTS = "BUILD_PLATFORM_CONTENTS_HAS_PARTS"
    BUILD_PLATFORM_CONTENTS_MISSING = "BUILD_PLATFORM_CONTENTS_MISSING"
    BUILD_PLATFORM_CONTENTS_UNCONFIRMED = "BUILD_PLATFORM_CONTENTS_UNCONFIRMED"
    BUILD_PLATFORM_CONTENTS_CONFIRMED_CLEAR = "BUILD_PLATFORM_CONTENTS_CONFIRMED_CLEAR"


# ===========================================
# 프린트 작업 스키마
# ===========================================

class CurrentPrintRun(BaseModel):
    """현재 진행 중인 프린트 작업 정보"""
    guid: Optional[str] = None
    name: Optional[str] = None
    status: Optional[PrintStatus] = None
    
    # 레이어 정보
    currently_printing_layer: int = 0
    layer_count: int = 0
    
    # 시간 정보 (밀리초)
    estimated_duration_ms: int = 0
    elapsed_duration_ms: int = 0
    estimated_time_remaining_ms: int = 0
    
    # 시작/완료 시간
    print_started_at: Optional[datetime] = None
    print_finished_at: Optional[datetime] = None
    
    @property
    def progress_percent(self) -> float:
        """진행률 (0~100)"""
        if self.layer_count == 0:
            return 0.0
        return round((self.currently_printing_layer / self.layer_count) * 100, 1)
    
    @property
    def estimated_remaining_minutes(self) -> int:
        """남은 시간 (분)"""
        return self.estimated_time_remaining_ms // 60000
    
    @property
    def elapsed_minutes(self) -> int:
        """경과 시간 (분)"""
        return self.elapsed_duration_ms // 60000


# ===========================================
# 소모품 스키마
# ===========================================

class CartridgeStatus(BaseModel):
    """레진 카트리지 상태"""
    serial: Optional[str] = None
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    initial_ml: float = 0
    remaining_ml: float = 0
    
    @property
    def remaining_percent(self) -> float:
        """잔량 퍼센트"""
        if self.initial_ml == 0:
            return 0.0
        return round((self.remaining_ml / self.initial_ml) * 100, 1)
    
    @property
    def is_low(self) -> bool:
        """잔량 부족 여부 (100ml 이하)"""
        return self.remaining_ml < 100


class TankStatus(BaseModel):
    """레진 탱크 상태"""
    serial: Optional[str] = None
    material_code: Optional[str] = None
    print_count: int = 0
    days_since_first_print: int = 0


# ===========================================
# 프린터 상태 스키마
# ===========================================

class PrinterStatus(BaseModel):
    """프린터 현재 상태"""
    status: Optional[str] = None
    last_pinged_at: Optional[datetime] = None
    current_print_run: Optional[CurrentPrintRun] = None
    ready_to_print: Optional[PrinterReadyState] = None
    build_platform_contents: Optional[BuildPlatformState] = None


class Printer(BaseModel):
    """프린터 전체 정보"""
    serial: str
    alias: Optional[str] = None  # 사용자 지정 이름
    machine_type: Optional[str] = None  # "FORM-4-0"
    
    # 상태 정보
    printer_status: Optional[PrinterStatus] = None
    cartridge_status: Optional[CartridgeStatus] = None
    tank_status: Optional[TankStatus] = None
    
    # 메타데이터
    firmware_version: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @property
    def display_name(self) -> str:
        """표시용 이름 (alias 또는 serial)"""
        return self.alias or self.serial
    
    @property
    def is_printing(self) -> bool:
        """출력 중 여부"""
        if self.printer_status and self.printer_status.current_print_run:
            return self.printer_status.current_print_run.status == PrintStatus.PRINTING
        return False
    
    @property
    def is_online(self) -> bool:
        """온라인 여부 (5분 이내 통신)"""
        if self.printer_status and self.printer_status.last_pinged_at:
            now = datetime.now(timezone.utc)
            last_ping = self.printer_status.last_pinged_at
            # timezone-naive인 경우 UTC로 간주
            if last_ping.tzinfo is None:
                last_ping = last_ping.replace(tzinfo=timezone.utc)
            elapsed = now - last_ping
            return elapsed.total_seconds() < 300
        return False


# ===========================================
# 대시보드용 요약 스키마
# ===========================================

class PrinterSummary(BaseModel):
    """대시보드용 프린터 요약 정보"""
    serial: str
    name: str
    status: str  # IDLE, PRINTING, FINISHED, ERROR, OFFLINE
    
    # 출력 진행 정보 (출력 중일 때만)
    current_job_name: Optional[str] = None
    progress_percent: Optional[float] = None
    remaining_minutes: Optional[int] = None
    current_layer: Optional[int] = None
    total_layers: Optional[int] = None
    
    # 소모품 정보
    resin_remaining_ml: Optional[float] = None
    resin_remaining_percent: Optional[float] = None
    is_resin_low: bool = False
    
    # 상태 플래그
    is_online: bool = True
    is_ready: bool = True
    has_error: bool = False
    
    # 마지막 업데이트
    last_update: datetime = Field(default_factory=now_kst)


class DashboardData(BaseModel):
    """대시보드 전체 데이터"""
    printers: List[PrinterSummary]
    total_printers: int
    printers_printing: int
    printers_idle: int
    printers_error: int
    printers_offline: int
    last_update: datetime = Field(default_factory=now_kst)


# ===========================================
# 알림 스키마
# ===========================================

class NotificationType(str, Enum):
    """알림 종류"""
    PRINT_COMPLETE = "PRINT_COMPLETE"
    PRINT_ERROR = "PRINT_ERROR"
    LOW_RESIN = "LOW_RESIN"
    PRINTER_OFFLINE = "PRINTER_OFFLINE"


class Notification(BaseModel):
    """알림 정보"""
    type: NotificationType
    printer_serial: str
    printer_name: str
    title: str
    message: str
    timestamp: datetime = Field(default_factory=now_kst)
    
    # 추가 정보 (선택)
    job_name: Optional[str] = None
    error_details: Optional[str] = None


# ===========================================
# 프린트 이력 스키마
# ===========================================

class PrintHistoryPart(BaseModel):
    """프린트 이력 파트 정보"""
    display_name: str
    volume_ml: Optional[float] = None
    stl_path: Optional[str] = None  # 원본 STL 경로


class PrintHistoryItem(BaseModel):
    """프린트 이력 항목"""
    guid: str
    name: str
    printer_serial: str
    printer_name: Optional[str] = None
    status: PrintStatus

    # 시간 정보
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None

    # 레이어 정보
    layer_count: int = 0

    # 재료 정보
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    estimated_ml_used: Optional[float] = None

    # 상세 정보 (확장)
    message: Optional[str] = None  # 오류/중단 메시지
    print_run_success: Optional[str] = None  # SUCCESS / null
    thumbnail_url: Optional[str] = None
    volume_ml: Optional[float] = None  # 전체 사용 레진량
    parts: List[PrintHistoryPart] = []  # 포함된 파트 목록


class PrintHistoryResponse(BaseModel):
    """프린트 이력 응답"""
    items: List[PrintHistoryItem]
    total_count: int
    page: int = 1
    page_size: int = 20
