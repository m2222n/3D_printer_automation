"""라인 MES 발행기 — 논블로킹 · 참조 해석 · 거부는 로그만. 매핑은 PG 없이, 발행은 LINE_DSN 있을 때."""
import os

import pytest


def test_printer_state_mapping():
    from app.line.publisher import printer_line_state
    from app.schemas.printer import PrintStatus
    assert printer_line_state(PrintStatus.PRINTING) == "RUN"
    assert printer_line_state(PrintStatus.PREHEAT) == "RUN"
    assert printer_line_state(PrintStatus.PAUSED) == "HOLD"
    assert printer_line_state(PrintStatus.FINISHED) is None, "DONE 은 제어(cmd_status=40)가 낸다"
    assert printer_line_state(None) is None and printer_line_state(PrintStatus.ABORTED) is None


def test_publisher_is_noop_without_dsn():
    from line_mes.publish import LinePublisher
    p = LinePublisher("")
    assert p.emit_state(("printer_serial", "x"), "RUN", "ADAPTER") is False
    assert p.q.empty() and p._thread is None


def test_vision_status_suffix_mapping():
    m = lambda s: {"running": "RUN", "complete": "DONE", "error": "ERROR"}.get(s.rsplit("_", 1)[-1])
    assert m("wash_running") == "RUN" and m("cure_complete") == "DONE" and m("error") == "ERROR"
    assert m("wash_idle") is None and m("offline") is None


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_publisher_resolves_refs_and_drops_unknown(settings):
    import psycopg
    from line_mes.publish import LinePublisher
    dsn = os.environ["LINE_DSN"]
    with psycopg.connect(dsn) as c:
        serial = c.execute("SELECT external_ref->>'printer_serial' FROM node WHERE node_id='PRT-01'").fetchone()[0]
        has_unit = c.execute("SELECT count(*) FROM product_state WHERE node_id='PRT-01'").fetchone()[0]
        before = c.execute("SELECT count(*) FROM product_event WHERE node_id='PRT-01' AND source='ADAPTER'").fetchone()[0]
    p = LinePublisher(dsn, name="test")
    assert p.emit_state(("printer_serial", serial), "RUN", "ADAPTER")
    assert p.emit_state(("printer_serial", "Form4-NOPE"), "RUN", "ADAPTER")          # 모르는 참조 → 스레드가 버린다
    assert p.emit_moved("cmd-없음", ("legacy_task_unit", "printer-1"), ("legacy_task_unit", "wash-1"), "ROBOT")  # unit 없음 → 버림
    assert p.flush(10)
    with psycopg.connect(dsn) as c:
        after = c.execute("SELECT count(*) FROM product_event WHERE node_id='PRT-01' AND source='ADAPTER'").fetchone()[0]
    assert after == before + (1 if has_unit else 0), "개체가 있으면 RUN 이벤트 1건, 없으면 엔진이 무시(0건)"
    assert p.sent == 3 and p.rejected == 0, "버림(참조 없음·unit 없음)은 거부가 아니라 조용한 처리 — 스레드는 계속 산다"


@pytest.mark.skipif(not os.environ.get("LINE_DSN"), reason="개발 PG 없음")
def test_publisher_moved_by_cmd_id(settings):
    """B5 경로: 제어 어휘(printer-1 → cure-1)와 cmd_id 만으로 unit 이 실제로 옮겨진다. ASIS 에 PRT→CUR 엣지가 있다."""
    import uuid
    import psycopg
    from line_mes.contract import Spawn
    from line_mes.publish import LinePublisher
    from line_mes.state_engine import StateEngine
    dsn = os.environ["LINE_DSN"]
    cmd = f"pub-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(dsn, autocommit=True) as c:
        line = c.execute("SELECT line_id FROM line WHERE is_active LIMIT 1").fetchone()[0]
        uid = StateEngine(c).handle(Spawn(node_id="PRT-01", line_id=line, cmd_id=cmd, source="ADAPTER"))
    p = LinePublisher(dsn, name="test-moved")
    assert p.emit_moved(cmd, ("legacy_task_unit", "printer-1"), ("legacy_task_unit", "cure-1"), "ROBOT")
    assert p.flush(10)
    with psycopg.connect(dsn) as c:
        node, = c.execute("SELECT node_id FROM product_state WHERE unit_id = %s", (uid,)).fetchone()
        tr, src = c.execute("SELECT transporter_id, source FROM product_event WHERE unit_id = %s ORDER BY event_id DESC LIMIT 1", (uid,)).fetchone()
    assert node == "CUR-01", node
    assert src == "ROBOT" and tr, "출발 노드 담당 반송자원이 이벤트에 실린다(하드코딩 없음)"
