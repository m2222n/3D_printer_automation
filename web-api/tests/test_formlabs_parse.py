"""Formlabs raw JSON → Printer 파싱 계약 테스트 (#6).

_parse_printer는 순수 함수(HTTP 무관)라 실제 Formlabs 응답 샘플을 직접 넣어
파싱 계약을 잠근다. 어댑터로 옮겨도 이 변환 규칙이 유지돼야 한다.
(중첩 구조 cartridge_status.cartridge.initial_volume_ml 등)
"""

from app.services.formlabs_client import FormlabsAPIClient
from app.schemas.printer import Printer


def _parse(data: dict) -> Printer:
    return FormlabsAPIClient._parse_printer.__get__(
        object.__new__(FormlabsAPIClient)
    )(data)


# 실제 Formlabs API 응답 구조를 본뜬 샘플
SAMPLE = {
    "serial": "Form4-CapableGecko",
    "alias": "테스트기",
    "machine_type": "FORM-4-0",
    "firmware_version": "1.16.1-2955",
    "is_remote_print_enabled": True,
    "printer_status": {
        "status": "IDLE",
        "last_pinged_at": "2026-07-10T02:00:00Z",
        "ready_to_print": "READY_TO_PRINT_READY",
        "build_platform_contents": "BUILD_PLATFORM_CONTENTS_MISSING",
        "temperature": 28.5,
        "current_print_run": None,
    },
    "cartridge_status": {
        "cartridge": {
            "serial": "CART-123",
            "material": "FLGPWH05",
            "display_name": "White V5",
            "initial_volume_ml": 1000,
            "volume_dispensed_ml": 600,
        }
    },
    "tank_status": {
        "tank": {
            "serial": "TANK-9",
            "material": "FLGPWH05",
            "print_count": 42,
        }
    },
}


def test_parse_basic_fields():
    p = _parse(SAMPLE)
    assert p.serial == "Form4-CapableGecko"
    assert p.machine_type == "FORM-4-0"
    assert p.firmware_version == "1.16.1-2955"


def test_parse_cartridge_remaining_computed():
    """레진 잔량 = initial - dispensed = 1000 - 600 = 400."""
    p = _parse(SAMPLE)
    assert p.cartridge_status is not None
    assert p.cartridge_status.remaining_ml == 400
    assert p.cartridge_status.material_code == "FLGPWH05"


def test_parse_tank_status():
    p = _parse(SAMPLE)
    assert p.tank_status is not None
    assert p.tank_status.print_count == 42


def test_parse_printer_status_enums():
    p = _parse(SAMPLE)
    assert p.printer_status.ready_to_print == "READY_TO_PRINT_READY"
    assert p.printer_status.temperature == 28.5


def test_parse_unknown_enum_becomes_none():
    """Formlabs가 새 enum 값을 추가해도 파싱이 죽지 않고 None 처리."""
    data = dict(SAMPLE)
    data["printer_status"] = dict(SAMPLE["printer_status"])
    data["printer_status"]["ready_to_print"] = "SOME_FUTURE_VALUE"
    p = _parse(data)
    assert p.printer_status.ready_to_print is None


def test_parse_missing_optional_sections():
    """cartridge/tank 없는 최소 응답도 파싱 가능."""
    minimal = {"serial": "Form4-Bare", "printer_status": None}
    p = _parse(minimal)
    assert p.serial == "Form4-Bare"
    assert p.cartridge_status is None
    assert p.tank_status is None
