"""
프린터 상태 폴링 서비스
========================
- 주기적 상태 조회 (10~30초)
- 상태 변경 감지
- 완료/에러 알림 트리거
"""

import asyncio
import logging
from typing import Dict, Optional, List, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.services.formlabs_client import FormlabsAPIClient, get_formlabs_client
from app.schemas.printer import (
    Printer, PrinterSummary, DashboardData,
    PrintStatus, NotificationType, Notification,
    now_kst
)

logger = logging.getLogger(__name__)


@dataclass
class PrinterState:
    """프린터 상태 추적용 내부 클래스"""
    serial: str
    last_status: Optional[PrintStatus] = None
    last_job_guid: Optional[str] = None
    last_resin_ml: float = 0
    was_online: bool = True
    last_update: datetime = field(default_factory=now_kst)


class PrinterPollingService:
    """
    프린터 상태 폴링 서비스
    
    기능:
    - 주기적으로 Formlabs Web API 폴링
    - 상태 변경 감지 (PRINTING → FINISHED, ERROR 등)
    - 알림 콜백 호출
    - 대시보드용 데이터 제공
    
    사용법:
        service = PrinterPollingService(client)
        service.on_notification(my_handler)
        await service.start()
    """
    
    def __init__(self, client: FormlabsAPIClient):
        self.settings = get_settings()
        self.client = client
        
        # 상태 추적
        self._printer_states: Dict[str, PrinterState] = {}
        self._current_data: Optional[DashboardData] = None
        
        # 폴링 제어
        self._running = False
        self._polling_task: Optional[asyncio.Task] = None
        
        # 콜백
        self._notification_handlers: List[Callable[[Notification], Awaitable[None]]] = []
        self._update_handlers: List[Callable[[DashboardData], Awaitable[None]]] = []
    
    # ===========================================
    # 콜백 등록
    # ===========================================
    
    def on_notification(self, handler: Callable[[Notification], Awaitable[None]]):
        """알림 발생 시 호출될 핸들러 등록"""
        self._notification_handlers.append(handler)
    
    def on_update(self, handler: Callable[[DashboardData], Awaitable[None]]):
        """데이터 업데이트 시 호출될 핸들러 등록"""
        self._update_handlers.append(handler)
    
    # ===========================================
    # 폴링 제어
    # ===========================================
    
    async def start(self):
        """폴링 시작"""
        if self._running:
            logger.warning("폴링이 이미 실행 중입니다")
            return
        
        self._running = True
        logger.info(
            f"🚀 프린터 폴링 서비스 시작 "
            f"(주기: {self.settings.POLLING_INTERVAL_SECONDS}초)"
        )
        
        # 초기 상태 로드
        await self._poll_once()
        
        # 폴링 루프 시작
        self._polling_task = asyncio.create_task(self._polling_loop())
    
    async def stop(self):
        """폴링 중지"""
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 프린터 폴링 서비스 중지")
    
    async def _polling_loop(self):
        """폴링 루프"""
        while self._running:
            try:
                await asyncio.sleep(self.settings.POLLING_INTERVAL_SECONDS)
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"폴링 오류: {e}")
                # 오류 발생해도 계속 폴링
                await asyncio.sleep(self.settings.POLLING_INTERVAL_SECONDS)
    
    async def _poll_once(self):
        """한 번 폴링 실행"""
        try:
            # 프린터 상태 조회
            printers = await self.client.get_target_printers()
            
            if not printers:
                logger.warning("⚠️ 조회된 프린터 없음")
                return
            
            # 상태 변경 감지 및 알림
            for printer in printers:
                await self._check_state_change(printer)
            
            # 대시보드 데이터 업데이트
            self._current_data = self._build_dashboard_data(printers)
            
            # 업데이트 핸들러 호출
            for handler in self._update_handlers:
                try:
                    await handler(self._current_data)
                except Exception as e:
                    logger.error(f"업데이트 핸들러 오류: {e}")
            
            logger.debug(f"✅ 폴링 완료: {len(printers)}대 프린터")
            
        except Exception as e:
            logger.error(f"폴링 실패: {e}")
    
    # ===========================================
    # 상태 변경 감지
    # ===========================================
    
    async def _check_state_change(self, printer: Printer):
        """프린터 상태 변경 감지 및 알림 발생"""
        serial = printer.serial
        
        # 이전 상태 가져오기 (없으면 새로 생성)
        if serial not in self._printer_states:
            self._printer_states[serial] = PrinterState(serial=serial)
        
        prev_state = self._printer_states[serial]
        
        # 현재 상태 추출
        current_status = None
        current_job_guid = None
        current_resin_ml = 0
        is_online = printer.is_online
        
        if printer.printer_status and printer.printer_status.current_print_run:
            run = printer.printer_status.current_print_run
            current_status = run.status
            current_job_guid = run.guid
        
        if printer.cartridge_status:
            current_resin_ml = printer.cartridge_status.remaining_ml
        
        # =====================
        # 1. 프린트 시작 감지
        # =====================
        if (
            current_status == PrintStatus.PRINTING and
            prev_state.last_status != PrintStatus.PRINTING and
            prev_state.last_status is not None
        ):
            await self._emit_notification(Notification(
                type=NotificationType.PRINT_STARTED,
                printer_serial=serial,
                printer_name=printer.display_name,
                title="프린트 시작",
                message=f"{printer.display_name}에서 프린트가 시작되었습니다.",
                job_name=printer.printer_status.current_print_run.name if printer.printer_status and printer.printer_status.current_print_run else None
            ))
            logger.info(f"🖨️ 프린트 시작: {printer.display_name}")

        # =====================
        # 2. 프린트 완료 감지
        # =====================
        if (
            prev_state.last_status == PrintStatus.PRINTING and
            current_status == PrintStatus.FINISHED and
            self.settings.NOTIFY_ON_PRINT_COMPLETE
        ):
            await self._emit_notification(Notification(
                type=NotificationType.PRINT_COMPLETE,
                printer_serial=serial,
                printer_name=printer.display_name,
                title="🎉 프린트 완료",
                message=f"{printer.display_name}의 프린트가 완료되었습니다.",
                job_name=printer.printer_status.current_print_run.name if printer.printer_status and printer.printer_status.current_print_run else None
            ))
            logger.info(f"🎉 프린트 완료: {printer.display_name}")
        
        # =====================
        # 2. 에러 감지
        # =====================
        if (
            current_status == PrintStatus.ERROR and
            prev_state.last_status != PrintStatus.ERROR and
            self.settings.NOTIFY_ON_PRINT_ERROR
        ):
            await self._emit_notification(Notification(
                type=NotificationType.PRINT_ERROR,
                printer_serial=serial,
                printer_name=printer.display_name,
                title="⚠️ 프린트 오류",
                message=f"{printer.display_name}에서 오류가 발생했습니다. 확인이 필요합니다.",
                job_name=printer.printer_status.current_print_run.name if printer.printer_status and printer.printer_status.current_print_run else None
            ))
            logger.warning(f"⚠️ 프린트 오류: {printer.display_name}")
        
        # =====================
        # 3. 레진 부족 감지
        # =====================
        if (
            current_resin_ml > 0 and
            current_resin_ml < self.settings.LOW_RESIN_THRESHOLD_ML and
            prev_state.last_resin_ml >= self.settings.LOW_RESIN_THRESHOLD_ML and
            self.settings.NOTIFY_ON_LOW_RESIN
        ):
            await self._emit_notification(Notification(
                type=NotificationType.LOW_RESIN,
                printer_serial=serial,
                printer_name=printer.display_name,
                title="⚠️ 레진 부족",
                message=f"{printer.display_name}의 레진이 {current_resin_ml:.0f}ml 남았습니다. 교체를 준비해주세요."
            ))
            logger.warning(f"⚠️ 레진 부족: {printer.display_name} ({current_resin_ml:.0f}ml)")
        
        # =====================
        # 4. 오프라인 감지
        # =====================
        if prev_state.was_online and not is_online:
            await self._emit_notification(Notification(
                type=NotificationType.PRINTER_OFFLINE,
                printer_serial=serial,
                printer_name=printer.display_name,
                title="🔴 프린터 오프라인",
                message=f"{printer.display_name}과의 연결이 끊어졌습니다."
            ))
            logger.warning(f"🔴 프린터 오프라인: {printer.display_name}")
        
        # 상태 업데이트
        prev_state.last_status = current_status
        prev_state.last_job_guid = current_job_guid
        prev_state.last_resin_ml = current_resin_ml
        prev_state.was_online = is_online
        prev_state.last_update = now_kst()
    
    async def _emit_notification(self, notification: Notification):
        """알림 발생 및 핸들러 호출"""
        for handler in self._notification_handlers:
            try:
                await handler(notification)
            except Exception as e:
                logger.error(f"알림 핸들러 오류: {e}")
    
    # ===========================================
    # 대시보드 데이터
    # ===========================================
    
    def _build_dashboard_data(self, printers: List[Printer]) -> DashboardData:
        """대시보드용 데이터 구성"""
        summaries = [self.client.printer_to_summary(p) for p in printers]
        
        # 통계 계산 (활성 작업 상태: PRINTING, PREHEAT, PAUSING, PAUSED, ABORTING)
        active_statuses = {"PRINTING", "PREHEAT", "PAUSING", "PAUSED", "ABORTING"}
        printing = sum(1 for s in summaries if s.status in active_statuses)
        idle = sum(1 for s in summaries if s.status == "IDLE")
        error = sum(1 for s in summaries if s.status == "ERROR")
        offline = sum(1 for s in summaries if s.status == "OFFLINE")
        
        return DashboardData(
            printers=summaries,
            total_printers=len(summaries),
            printers_printing=printing,
            printers_idle=idle,
            printers_error=error,
            printers_offline=offline,
            last_update=now_kst()
        )
    
    def get_current_data(self) -> Optional[DashboardData]:
        """현재 대시보드 데이터 반환"""
        return self._current_data
    
    def get_printer_summary(self, serial: str) -> Optional[PrinterSummary]:
        """특정 프린터 요약 정보 반환"""
        if not self._current_data:
            return None
        
        for summary in self._current_data.printers:
            if summary.serial == serial:
                return summary
        return None


# ===========================================
# 서비스 팩토리
# ===========================================

_polling_service: Optional[PrinterPollingService] = None


async def get_polling_service() -> PrinterPollingService:
    """폴링 서비스 싱글톤 반환"""
    global _polling_service
    if _polling_service is None:
        client = await get_formlabs_client()
        _polling_service = PrinterPollingService(client)
    return _polling_service


async def start_polling_service():
    """폴링 서비스 시작"""
    service = await get_polling_service()
    await service.start()


async def stop_polling_service():
    """폴링 서비스 중지"""
    global _polling_service
    if _polling_service:
        await _polling_service.stop()
        _polling_service = None
