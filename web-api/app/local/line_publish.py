"""
라인 MES(v2 · PostgreSQL) 로 Spawn 을 발행한다.

호출 지점은 하나 — routes._process_print_job 의 "프린터가 받았다" 분기.
그 시점이 배치의 탄생이다. 로봇이 옮기는지 사람이 옮기는지는 여기 없다 (Moved 가 답한다).

LINE_DSN 이 비어 있으면 아무 것도 하지 않는다 — 6000·카카오처럼 프린터에 안 닿는 인스턴스용.
실패는 raise 한다. 삼키는 것은 호출자(프린터는 이미 돌고 있어서 되돌릴 수 없다)의 몫이고,
호출자가 print_jobs.error_message 에 남긴다.
"""
import json
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def node_for_serial(conn, printer_serial: str) -> Optional[str]:
    """external_ref.printer_serial → node_id. 토폴로지에 없으면 None."""
    row = conn.execute(
        "SELECT node_id FROM node WHERE is_active AND external_ref @> %s::jsonb",
        (json.dumps({"printer_serial": printer_serial}),),
    ).fetchone()
    return row[0] if row else None


def spawn_for_print(printer_serial: str, cmd_id: Optional[str] = None,
                    part_type: Optional[str] = None, qty: int = 1) -> Optional[str]:
    """프린터가 출력을 받았다 → unit 하나. 반환 = unit_id (LINE_DSN 비면 None).

    part_type = 출력을 건 프리셋의 부품 종류. 프리셋을 만들 때 사람이 고른 값이고, 프린터가
    success 를 돌려준 순간 그 부품이 찍히기 시작한다 — 그래서 배치 내용물의 출처는 주문이 아니라 이것이다.
    프리셋 없이(직접 설정으로) 걸었으면 None → 내용 미상 배치(unit_content 0행).
    qty = 플레이트 한 장에 실린 개수. prepare_and_print 가 STL 을 한 번 import 하므로 1 이다
    (PrintJobCreate.copies 는 받기만 하고 어디서도 쓰지 않는다 — 그 값을 여기 실으면 거짓이 된다).
    """
    settings = get_settings()
    if not settings.LINE_DSN:
        return None

    import psycopg
    from line_mes.contract import Content, Spawn        # 리포 루트 패키지 (requirements `-e .`)
    from line_mes.state_engine import StateEngine

    with psycopg.connect(settings.LINE_DSN, autocommit=True) as conn:
        node_id = node_for_serial(conn, printer_serial)
        if not node_id:
            raise ValueError(f"토폴로지에 없는 프린터 시리얼: {printer_serial} (topology.yaml external_ref)")
        contents = ()
        if part_type:
            # unit_content.part_no 는 part 마스터 FK 다. 프리셋의 part_type 이 곧 작업자가 쓰는 부품 식별자이므로
            # 마스터에 없으면 그 이름으로 만든다 — 마스터가 프리셋을 따라간다.
            # ponytail: 부품 마스터 관리 화면이 생기면 이 자동 생성은 빼고 "없는 부품" 을 거부로 바꾼다.
            conn.execute("INSERT INTO part (part_no, name) VALUES (%s, %s) ON CONFLICT (part_no) DO NOTHING",
                         (part_type, part_type))
            contents = (Content(part_no=part_type, qty=qty),)
        unit_id = StateEngine(conn).handle(
            Spawn(node_id=node_id, line_id=settings.LINE_ID, cmd_id=cmd_id, contents=contents, source="ADAPTER"))
        logger.info(f"SPAWN unit={unit_id} node={node_id} cmd_id={cmd_id} part={part_type}x{qty if part_type else 0}")
        return str(unit_id)
