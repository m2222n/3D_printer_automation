"""
web-api 의 LinePublisher 인스턴스 + 프린터 상태 매핑 (M2c).

프린터 API 가 주는 것은 RUN/HOLD 까지다. DONE 은 여기서 내지 않는다 — FINISHED 는 플레이트를 빼면 15초 폴링이
놓치는 전이 상태라(6/1 stale 버그 계열) 제어(sequence_service · cmd_status=40)가 1차 정보원이다(병존 ④-4 · 계획 B3).
ERROR 도 아직 내지 않는다 — 프린터 API 의 어느 필드가 "고장" 인지 확정된 매핑이 없다. 지어 넣지 않는다.
"""
from typing import Optional

from app.core.config import get_settings
from app.schemas.printer import PrintStatus
from line_mes.publish import LinePublisher

_pub: Optional[LinePublisher] = None


def publisher() -> LinePublisher:
    global _pub
    if _pub is None:
        _pub = LinePublisher(get_settings().LINE_DSN, name="web-api-line-publisher")
    return _pub


_RUN = {PrintStatus.PREPRINT, PrintStatus.PREHEAT, PrintStatus.PRECOAT, PrintStatus.PRINTING, PrintStatus.POSTCOAT}
_HOLD = {PrintStatus.PAUSING, PrintStatus.PAUSED, PrintStatus.ABORTING}


def printer_line_state(status) -> Optional[str]:
    """Formlabs current_print_run.status → 라인 State. 매핑 없는 값(FINISHED · IDLE · ABORTED · None)은 None = 발행 안 함."""
    if status in _RUN:
        return "RUN"
    if status in _HOLD:
        return "HOLD"
    return None
