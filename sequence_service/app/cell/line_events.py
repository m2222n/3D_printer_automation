"""
sequence_service → 라인 MES 관측 발행 (M2b Moved · B3 프린터 DONE).

여기가 cell/ → line_mes 의 유일한 문이다(병존 ③: 의존 한 방향 · 발행 함수만). 전부 논블로킹 put 한 줄이고
PG 접속·엔진 호출은 LinePublisher 의 데몬 스레드가 한다 — 스텝머신(robot.py 402~631)은 기다리지 않는다.
LINE_DSN 이 비어 있으면(../web-api/.env 공유) 전부 no-op.
"""
from typing import Optional

from app.core.config import get_settings
from line_mes.publish import LinePublisher

_pub: Optional[LinePublisher] = None


def publisher() -> LinePublisher:
    global _pub
    if _pub is None:
        _pub = LinePublisher(get_settings().LINE_DSN, name="sequence-line-publisher")
    return _pub


def printer_done(printer_serial: str) -> None:
    """제어가 PRINT_FINISHED(cmd_status=40)를 확정한 순간 — 프린터 DONE 의 1차 정보원(병존 ④-4)."""
    if printer_serial:
        publisher().emit_state(("printer_serial", printer_serial), "DONE", source="ADAPTER")


def robot_moved(cmd_id: str, from_unit: str, to_unit: str) -> None:
    """로봇 이동이 물리적으로 끝난 뒤(robot._complete_task). from/to 는 제어 어휘(printer-1 · wash-2 · cure-1 · output) —
    노드 매핑은 topology.yaml external_ref.legacy_task_unit 이 갖고 있어 여기서는 그대로 넘긴다."""
    publisher().emit_moved(cmd_id, ("legacy_task_unit", from_unit), ("legacy_task_unit", to_unit), source="ROBOT")
