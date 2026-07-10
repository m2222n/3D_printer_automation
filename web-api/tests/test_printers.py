"""대시보드·프린터 조회 계약 + printer_to_summary 단위 테스트 (#3, #4, #5).

어댑터 도입 시 깨질 수 있는 정확히 그 지점을 잠근다.
"""

from datetime import datetime, timezone

import pytest

from app.schemas.printer import (
    Printer, PrinterStatus, CurrentPrintRun, CartridgeStatus,
    PrintStatus, PrinterReadyState, DashboardData, PrinterSummary,
)


# --- fixtures -------------------------------------------------------------

def _make_printer(
    serial="Form4-Test",
    run_status=None,
    ready_to_print=PrinterReadyState.READY_TO_PRINT_READY,
    online=True,
):
    """테스트용 Printer 객체. online이면 last_pinged_at을 현재로 둔다."""
    status = PrinterStatus(
        status="IDLE",
        last_pinged_at=datetime.now(timezone.utc) if online else None,
        current_print_run=(
            CurrentPrintRun(name="job.form", status=run_status)
            if run_status else None
        ),
        ready_to_print=ready_to_print,
    )
    return Printer(
        serial=serial,
        machine_type="FORM-4-0",
        printer_status=status,
        cartridge_status=CartridgeStatus(
            material_code="FLGPWH05", initial_ml=1000, remaining_ml=400
        ),
    )


@pytest.fixture
def stub_polling(monkeypatch):
    """폴링 서비스를 고정 데이터로 stub. get_current_data / get_printer_summary."""
    from app.services.formlabs_client import FormlabsAPIClient
    import app.services.polling_service as ps_mod

    # printer_to_summary는 실제 로직 사용 (계약 검증 목적)
    printer = _make_printer()
    summary = FormlabsAPIClient.printer_to_summary.__get__(
        object.__new__(FormlabsAPIClient)
    )(printer)
    dashboard = DashboardData(
        printers=[summary],
        total_printers=1,
        printers_printing=0,
        printers_idle=1,
        printers_error=0,
        printers_offline=0,
    )

    class _StubPolling:
        def get_current_data(self):
            return dashboard

        def get_printer_summary(self, serial):
            return summary if serial == summary.serial else None

    async def _get_stub():
        return _StubPolling()

    monkeypatch.setattr(ps_mod, "get_polling_service", _get_stub)
    # routes.py가 import한 참조도 교체
    import app.api.routes as routes_mod
    monkeypatch.setattr(routes_mod, "get_polling_service", _get_stub)
    return summary


# --- #3 대시보드 ----------------------------------------------------------

def test_dashboard_returns_valid_schema(client, auth_headers, stub_polling):
    resp = client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "printers" in body
    assert body["total_printers"] == 1
    # 스키마 검증 (파싱 성공)
    DashboardData(**body)


# --- #4 프린터 상세 = 로봇 핸드셰이크 계약 5필드 ⭐ --------------------------

ROBOT_CONTRACT_FIELDS = ["status", "is_online", "has_error", "is_ready", "ready_to_print"]


def test_printer_detail_has_robot_contract_fields(client, auth_headers, stub_polling):
    """⭐ 로봇이 픽업 판단에 쓰는 5필드가 응답에 반드시 존재해야 한다.

    이 필드들이 사라지거나 이름이 바뀌면 sequence_service 로봇 핸드셰이크가 깨진다.
    """
    resp = client.get(f"/api/v1/printers/{stub_polling.serial}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for field in ROBOT_CONTRACT_FIELDS:
        assert field in body, f"로봇 계약 필드 누락: {field}"


def test_printer_detail_not_found_404(client, auth_headers, stub_polling):
    resp = client.get("/api/v1/printers/NoSuchPrinter", headers=auth_headers)
    assert resp.status_code == 404


# --- #5 printer_to_summary 단위: stale FINISHED 버그 회귀 방지 --------------

def _summary_of(printer):
    from app.services.formlabs_client import FormlabsAPIClient
    return FormlabsAPIClient.printer_to_summary.__get__(
        object.__new__(FormlabsAPIClient)
    )(printer)


def test_finished_but_ready_maps_to_idle():
    """6/1 stale 버그: current_run=FINISHED인데 ready_to_print=READY면 IDLE로 봐야 함."""
    printer = _make_printer(
        run_status=PrintStatus.FINISHED,
        ready_to_print=PrinterReadyState.READY_TO_PRINT_READY,
    )
    summary = _summary_of(printer)
    assert summary.status == "IDLE"


def test_finished_and_not_ready_stays_finished():
    """FINISHED + not_ready → FINISHED 유지 (아직 배출 전)."""
    printer = _make_printer(
        run_status=PrintStatus.FINISHED,
        ready_to_print=PrinterReadyState.READY_TO_PRINT_NOT_READY,
    )
    summary = _summary_of(printer)
    assert summary.status == "FINISHED"


def test_offline_printer_maps_to_offline():
    printer = _make_printer(online=False)
    summary = _summary_of(printer)
    assert summary.status == "OFFLINE"
    assert summary.is_online is False
