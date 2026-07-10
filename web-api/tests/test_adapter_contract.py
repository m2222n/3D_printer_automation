"""PrinterAdapter 계약 준수 테스트 (Step 2).

FormlabsAPIClient가 PrinterAdapter Protocol을 만족하는지 잠근다.
runtime_checkable Protocol이라 상속 없이 덕타이핑으로 검증되며,
어댑터 메서드가 사라지거나 이름이 바뀌면 이 테스트가 깨진다.
= 나중에 새 벤더(FDM) 어댑터를 추가할 때도 이 계약을 만족해야 함.
"""

from app.adapters.base import PrinterAdapter
from app.services.formlabs_client import FormlabsAPIClient


REQUIRED_METHODS = [
    "get_all_printers",
    "get_printer",
    "get_target_printers",
    "get_print_history",
    "get_events",
    "printer_to_summary",
]


def test_formlabs_client_satisfies_adapter_protocol():
    """FormlabsAPIClient 인스턴스가 PrinterAdapter Protocol을 만족한다."""
    # 인증 매니저 없이 __new__로 빈 인스턴스 (메서드 존재만 검사)
    instance = object.__new__(FormlabsAPIClient)
    assert isinstance(instance, PrinterAdapter)


def test_adapter_has_all_required_methods():
    """계약 메서드 6개가 모두 존재한다."""
    for name in REQUIRED_METHODS:
        assert hasattr(FormlabsAPIClient, name), f"어댑터 메서드 누락: {name}"
