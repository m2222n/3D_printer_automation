"""
프린터 어댑터 인터페이스
========================
SaaS 프린터 범용화의 이음새(seam). 현재는 Formlabs(SLA) 한 종류지만,
이 인터페이스 뒤로 벤더를 격리해 두면 나중에 FDM(OctoPrint/Cura 등)
어댑터를 추가할 때 이 계약만 구현하면 된다.

⚠️ 설계 원칙 (2026-07 리팩터링):
- 반환 타입(Printer/PrinterSummary)은 이번엔 그대로 유지 (SLA 전용 필드 포함).
  벤더 중립 데이터 모델(consumables 등)은 실제 FDM 프린터를 붙일 때
  PrinterSummary에 Optional 필드를 "추가"하는 방식으로 확장한다.
- PrinterSummary의 status/is_online/has_error/is_ready/ready_to_print 5필드는
  sequence_service 로봇 핸드셰이크 계약 → 절대 개명/삭제 금지.
"""

from typing import List, Optional, Dict, Protocol, runtime_checkable
from datetime import datetime

from app.schemas.printer import Printer, PrinterSummary, PrintStatus, PrintHistoryItem


@runtime_checkable
class PrinterAdapter(Protocol):
    """프린터 벤더 어댑터가 구현해야 하는 계약.

    현 FormlabsAPIClient의 공개 메서드를 그대로 승격한 것.
    새 벤더(FDM 등)를 추가하려면 이 Protocol을 만족하는 클래스를 만들고
    adapters/factory.py의 get_printer_adapter에 분기를 추가하면 된다.
    """

    async def get_all_printers(self) -> List[Printer]:
        """전체 프린터 목록 및 상태 조회."""
        ...

    async def get_printer(self, serial: str) -> Optional[Printer]:
        """특정 프린터 상세 조회."""
        ...

    async def get_target_printers(self) -> List[Printer]:
        """설정된 대상 프린터만 조회 (설정 없으면 전체)."""
        ...

    async def get_print_history(
        self,
        printer_serial: Optional[str] = None,
        status: Optional[PrintStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[PrintHistoryItem]:
        """프린트 이력 조회."""
        ...

    async def get_events(
        self,
        printer_serial: Optional[str] = None,
        event_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """프린터 이벤트(완료/에러 등) 조회."""
        ...

    def printer_to_summary(self, printer: Printer) -> PrinterSummary:
        """벤더 raw Printer → 대시보드/로봇용 PrinterSummary 변환.

        ⚠️ 반환 PrinterSummary의 5필드(status/is_online/has_error/
        is_ready/ready_to_print)는 로봇 핸드셰이크 계약.
        """
        ...
