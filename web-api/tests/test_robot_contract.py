"""로봇 핸드셰이크 계약 테스트 (#8) — 가장 중요한 회귀 방지.

sequence_service/app/cell/sequences/inprocess.py 의 프린터 픽업 판정 로직
(_printer_can_accept, :148~166)이 PrinterSummary 5필드로 판단한다.
그 판정 규칙을 여기 명세로 고정해, web-api가 만드는 PrinterSummary가
로봇이 기대하는 계약을 계속 만족하는지 검증한다.

⚠️ 이 판정 규칙이 바뀌면 여기 명세도 sequence_service와 함께 갱신해야 한다.
   (규칙 출처: inprocess.py 실제 코드)
"""

from app.services.formlabs_client import FormlabsAPIClient
from app.schemas.printer import (
    Printer, PrinterStatus, CurrentPrintRun,
    PrintStatus, PrinterReadyState,
)
from datetime import datetime, timezone


def robot_can_accept(summary_dict: dict) -> bool:
    """inprocess.py:148~166 판정 로직의 명세 복제.

    로봇이 이 프린터에 새 작업을 줄 수 있는가?
    """
    status = str(summary_dict.get("status") or "").upper()
    is_online = bool(summary_dict.get("is_online", False))
    has_error = bool(summary_dict.get("has_error", False))
    is_ready = bool(summary_dict.get("is_ready", False))
    ready_to_print = str(summary_dict.get("ready_to_print") or "").upper()

    if not is_online or has_error:
        return False
    if ready_to_print in {"NOT_READY", "READY_TO_PRINT_NOT_READY"}:
        return False
    return status in {"IDLE", "READY", "FINISHED"} and (
        is_ready or ready_to_print in {"READY", "READY_TO_PRINT_READY"}
    )


def _summary_dict(run_status=None, ready=PrinterReadyState.READY_TO_PRINT_READY, online=True):
    printer = Printer(
        serial="Form4-Test",
        printer_status=PrinterStatus(
            last_pinged_at=datetime.now(timezone.utc) if online else None,
            current_print_run=(
                CurrentPrintRun(name="j.form", status=run_status) if run_status else None
            ),
            ready_to_print=ready,
        ),
    )
    summary = FormlabsAPIClient.printer_to_summary.__get__(
        object.__new__(FormlabsAPIClient)
    )(printer)
    # 로봇은 JSON(dict)으로 받으므로 dict로 변환해 계약 검증
    return summary.model_dump(mode="json")


def test_idle_ready_printer_accepts():
    """IDLE + ready → 로봇 픽업 가능."""
    assert robot_can_accept(_summary_dict()) is True


def test_finished_but_ready_accepts():
    """FINISHED이지만 ready=READY(=IDLE로 매핑됨) → 픽업 가능."""
    d = _summary_dict(run_status=PrintStatus.FINISHED)
    # printer_to_summary가 IDLE로 매핑하므로 로봇도 수락
    assert robot_can_accept(d) is True


def test_printing_printer_rejected():
    """출력 중 → 픽업 불가."""
    d = _summary_dict(run_status=PrintStatus.PRINTING)
    assert robot_can_accept(d) is False


def test_offline_printer_rejected():
    d = _summary_dict(online=False)
    assert robot_can_accept(d) is False


def test_not_ready_printer_rejected():
    """ready_to_print=NOT_READY → 픽업 불가 (탱크 없음 등)."""
    d = _summary_dict(ready=PrinterReadyState.READY_TO_PRINT_NOT_READY)
    assert robot_can_accept(d) is False


def test_summary_has_all_contract_fields():
    """PrinterSummary가 로봇 계약 5필드를 모두 직렬화하는지."""
    d = _summary_dict()
    for f in ["status", "is_online", "has_error", "is_ready", "ready_to_print"]:
        assert f in d
