"""
M3a 상태 엔진.

책임
  - contract 의 이벤트를 받아 product_state 를 갱신한다
  - display_id 를 채번한다 (유일한 채번 지점)
  - product_event 에 이력을 남긴다

하지 않는 것
  - 로봇에 명령하지 않는다 (M3b)
  - 타이머를 돌리지 않는다 (ready_at)
  - 공정 이름을 모른다 — 동작 차이는 node 컬럼에서 읽는다
"""

import logging

import psycopg
from psycopg.rows import tuple_row

from line_mes.contract import Event, Moved, Spawn, Split, State

log = logging.getLogger("m3a")


class _TupleConn:
    """엔진은 컬럼 순서로 읽는다(row[0] · 언패킹). 호출자 커넥션의 row_factory 가 dict_row(web-api 풀)여도
    깨지지 않게 실행마다 튜플 커서를 쓴다. transaction() 은 그대로 위임 — 호출자 트랜잭션 안이면 세이브포인트."""
    def __init__(self, conn):
        self._c = conn
    def execute(self, sql, params=None):
        return self._c.cursor(row_factory=tuple_row).execute(sql, params)
    def transaction(self):
        return self._c.transaction()


class StateEngine:

    def __init__(self, conn):
        self.conn = conn if isinstance(conn, _TupleConn) else _TupleConn(conn)
        self.last_event_ids: list[int] = []   # 직전 handle() 이 남긴 product_event.event_id — 쓰기 API 응답용

    def handle(self, e: Event):
        self.last_event_ids = []
        with self.conn.transaction():
            if isinstance(e, Spawn): return self._spawn(e)
            if isinstance(e, State): return self._state(e)
            if isinstance(e, Moved): return self._moved(e)
            if isinstance(e, Split): return self._split(e)
        raise ValueError(f"알 수 없는 이벤트: {e}")

    # ------------------------------------------------------------ 헬퍼
    def _node(self, node_id):
        row = self.conn.execute("""
            SELECT node_kind, capacity, std_cycle_s, id_prefix, post_delay_s, slot_access, splits_batch
              FROM node WHERE node_id=%s AND is_active""", (node_id,)).fetchone()
        if not row:
            raise ValueError(f"활성 노드가 아님: {node_id}")
        return dict(zip(("kind", "capacity", "cycle", "prefix", "delay", "access", "splits"), row))

    def _place(self, node_id, slot_no=None, group_id=None):
        """
        놓을 (칸, 순번). 지시된 칸이 있으면 그 칸, 없으면 next_place().
        묶음이 이미 그 노드에 있으면 같은 자리 — 박스 하나가 자리 하나다.
        """
        if group_id:
            row = self.conn.execute("""SELECT slot_no, pos_no FROM product_state
                                        WHERE node_id=%s AND group_id=%s AND slot_no IS NOT NULL LIMIT 1""",
                                    (node_id, group_id)).fetchone()
            if row:
                return row
        if slot_no is not None:
            row = self.conn.execute("""
                SELECT sl.slot_no, count(ps.unit_id)+1 FROM node_slot sl
                  LEFT JOIN product_state ps ON ps.node_id=sl.node_id AND ps.slot_no=sl.slot_no
                 WHERE sl.node_id=%s AND sl.slot_no=%s GROUP BY sl.slot_no, sl.capacity
                HAVING count(ps.unit_id) < sl.capacity""", (node_id, slot_no)).fetchone()
            if not row:
                raise ValueError(f"{node_id} 칸 {slot_no} 이 이미 참")
            return row
        return self.conn.execute("SELECT * FROM next_place(%s)", (node_id,)).fetchone()

    def _serial(self, prefix):
        row = self.conn.execute("""
            UPDATE id_counter SET next_val = next_val + 1 WHERE prefix=%s
            RETURNING prefix || (next_val - 1)""", (prefix,)).fetchone()
        return row[0] if row else None

    def _log(self, unit_id, node_id, status, source, confidence=None, ready_at=None,
             transporter_id=None, msg=None):
        row = self.conn.execute("""
            INSERT INTO product_event (unit_id, node_id, status, ready_at, source,
                                       confidence, transporter_id, msg, duration_s)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
              (SELECT extract(epoch FROM (now() - updated_at))::int
                 FROM product_state WHERE unit_id=%s))
            RETURNING event_id
        """, (unit_id, node_id, status, ready_at, source, confidence, transporter_id, msg, unit_id)).fetchone()
        self.last_event_ids.append(row[0])

    # ------------------------------------------------------------ SPAWN
    def _spawn(self, e: Spawn):
        n = self._node(e.node_id)
        if e.order_id:
            row = self.conn.execute(
                "SELECT status FROM customer_order WHERE order_id=%s", (e.order_id,)).fetchone()
            if not row:
                raise ValueError(f"없는 주문: {e.order_id}")
            if row[0] in ("SHIPPED", "CANCELLED"):
                raise ValueError(f"{e.order_id} 는 {row[0]} 상태")

        # 투입 게이트 3개. 시뮬레이터(SIM)는 제어 역할까지 하므로 거부가 맞다 — 그게 백프레셔다.
        # 실물(ADAPTER 등)은 제어가 이미 물건을 넣은 뒤에 관측이 도착한다. 여기서 raise 하면
        # 프린터는 돌고 unit 만 안 생겨 대시보드에서 조용히 사라진다 ⇒ 경고하고 만든다.
        # 관측이 제어를 판정하지 않는다. (P5 에서 제어가 route 를 보게 되면 진짜 게이트로 승격)
        def gate(msg):
            if e.source == "SIM":
                raise ValueError(msg)
            log.warning("투입 게이트 경고(생성은 진행): %s", msg)

        # 플레이트 제약. 라인에 있는 배치 수가 보유 플레이트 수를 넘을 수 없다.
        row = self.conn.execute(
            "SELECT plates_in_use, plate_count FROM v_plate_usage WHERE line_id=%s",
            (e.line_id,)).fetchone()
        if not row:
            # v_plate_usage 는 활성 라인만 낸다 — 비활성/없는 라인으로는 어떤 source 도 투입할 수 없다(게이트가 아니라 정합성)
            raise ValueError(f"없는 라인 또는 비활성 라인: {e.line_id}")
        used, cap = row
        if used >= cap:
            gate(f"{e.line_id} 빌드플레이트 {cap}장 전부 사용 중 — 투입 거부")

        is_rack = n["kind"] == "RACK"
        place = self._place(e.node_id) if is_rack else None
        if is_rack and not place:
            gate(f"{e.node_id} 빈 자리 없음 — 투입 거부")
        if not is_rack:
            cnt = self.conn.execute("SELECT count(*) FROM product_state WHERE node_id=%s",
                                    (e.node_id,)).fetchone()[0]
            if cnt >= n["capacity"]:
                gate(f"{e.node_id} 용량 초과 — 투입 거부")

        unit_id, display_id = self.conn.execute("""
            INSERT INTO unit (line_id, order_id, cmd_id, display_id)
            VALUES (%s, %s, %s, 'U-' || left(gen_random_uuid()::text, 8))
            RETURNING unit_id, display_id""", (e.line_id, e.order_id, e.cmd_id)).fetchone()

        if e.contents:
            for ct in e.contents:
                self.conn.execute("INSERT INTO unit_content (unit_id, part_no, qty) VALUES (%s,%s,%s)",
                                  (unit_id, ct.part_no, ct.qty))
        elif e.order_id:
            k = self.conn.execute("""INSERT INTO unit_content (unit_id, part_no, qty)
                                     SELECT %s, part_no, qty FROM order_line WHERE order_id=%s""",
                                  (unit_id, e.order_id)).rowcount
            if not k:
                raise ValueError(f"{e.order_id} 에 품목이 없습니다")
        # else: 내용 미상 배치 — unit_content 0행. 지어 넣지 않는다.
        if e.order_id:
            self.conn.execute("UPDATE customer_order SET status='IN_PROGRESS' WHERE order_id=%s AND status='OPEN'",
                              (e.order_id,))

        slot_no, pos_no = place if place else (None, None)
        self.conn.execute("""
            INSERT INTO product_state (unit_id, node_id, slot_no, pos_no, status, entered_at, ready_at)
            VALUES (%s,%s,%s,%s,%s, now(), CASE WHEN %s THEN now() END)
        """, (unit_id, e.node_id, slot_no, pos_no, "DONE" if is_rack else "WAIT", is_rack))
        self._log(unit_id, e.node_id, "DONE" if is_rack else "WAIT", e.source)
        return unit_id

    # ------------------------------------------------------------ STATE
    def _state(self, e: State):
        """관측. 위치를 바꾸지 않는다. 노드에 있는 개체 전부에 적용한다."""
        n = self._node(e.node_id)
        ids = [r[0] for r in self.conn.execute(
            "SELECT unit_id FROM product_state WHERE node_id=%s", (e.node_id,)).fetchall()]
        if not ids:
            log.warning("STATE %s %s — 개체 없음, 무시", e.node_id, e.status)
            return None
        # 이번 가동을 얼마나 돌리나. 지시값이 오면 그것, 없으면 노드 표준 주기.
        # (기존 print_command.washing_time 과 같은 성격 — 배치마다 다르게 준다)
        run_s = e.duration_s if e.duration_s else n["cycle"]
        for uid in ids:
            if e.status == "RUN":
                self.conn.execute("""UPDATE product_state SET status='RUN', entered_at=now(),
                    updated_at=now(), ready_at=NULL, eta=now()+(%s*interval '1 second')
                    WHERE unit_id=%s""", (run_s, uid))
                self._log(uid, e.node_id, "RUN", e.source, e.confidence)
            elif e.status == "DONE":
                ready = self.conn.execute("""UPDATE product_state SET status='DONE', updated_at=now(),
                    ready_at=now()+(%s*interval '1 second') WHERE unit_id=%s RETURNING ready_at""",
                    (n["delay"], uid)).fetchone()[0]
                self._log(uid, e.node_id, "DONE", e.source, e.confidence, ready_at=ready)
            elif e.status == "HOLD":
                # 멈춘 것은 꺼낼 수 없다 — ready_at 을 지운다. 위치는 그대로다.
                # eta 도 지운다. 언제 끝날지는 다시 RUN 이 올 때 정해진다.
                # 🔴 ERROR 와 묶지 않는다 — "고장" 과 "세워둠" 은 다른 사실이고
                #    v_node_status 의 우선순위 정렬도 둘을 다르게 센다.
                self.conn.execute("""UPDATE product_state SET status='HOLD', updated_at=now(),
                    ready_at=NULL, eta=NULL WHERE unit_id=%s""", (uid,))
                self._log(uid, e.node_id, "HOLD", e.source, e.confidence)
            else:
                self.conn.execute("UPDATE product_state SET status='ERROR', updated_at=now(), "
                                  "ready_at=NULL WHERE unit_id=%s", (uid,))
                self._log(uid, e.node_id, "ERROR", e.source, e.confidence)
        return ids

    # ------------------------------------------------------------ SPLIT
    def _split(self, e: Split):
        """
        배치 → 부품 N개. splits_batch 노드(부품 분리대)에서만 일어난다.
        서포트 제거는 그 다음 별개 노드이고 거기서는 부품을 하나씩 판정할 뿐이다.
        부품은 group_id 로 묶여 함께 움직인다. 플레이트는 숫자라 복귀 처리가 없다.
        """
        row = self.conn.execute("""
            SELECT u.line_id, u.order_id, u.display_id, u.unit_kind, ps.node_id
              FROM unit u JOIN product_state ps USING (unit_id) WHERE u.unit_id=%s""",
            (e.unit_id,)).fetchone()
        if not row:
            raise ValueError(f"라인에 없는 개체: {e.unit_id}")
        line_id, order_id, parent_display, kind, node_id = row
        if kind != "BATCH":
            raise ValueError(f"BATCH 만 분해할 수 있습니다: {parent_display}")
        if node_id != e.node_id:
            raise ValueError(f"{parent_display} 는 {node_id} 에 있습니다")
        if not e.outputs:
            raise ValueError("분해 결과가 비어 있습니다")

        n = self._node(e.node_id)
        group = e.group_id or f"G-{parent_display}"
        children = []
        for out in e.outputs:
            for _ in range(out.qty):
                serial = self._serial(n["prefix"]) if n["prefix"] else None
                child_display = f"{parent_display}-{serial}" if serial \
                                else f"{parent_display}-{len(children)+1:02d}"
                child = self.conn.execute("""
                    INSERT INTO unit (line_id, order_id, unit_kind, display_id, parent_unit_id, named_at)
                    VALUES (%s,%s,'PART',%s,%s,%s) RETURNING unit_id""",
                    (line_id, order_id, child_display, e.unit_id, e.node_id)).fetchone()[0]
                self.conn.execute("INSERT INTO unit_content (unit_id, part_no, qty) VALUES (%s,%s,1)",
                                  (child, out.part_no))
                self.conn.execute("""INSERT INTO product_state (unit_id, node_id, group_id, status, entered_at, ready_at)
                                     VALUES (%s,%s,%s,'DONE', now(), now())""", (child, e.node_id, group))
                self._log(child, e.node_id, "DONE", e.source, msg=f"split from {parent_display}")
                children.append(child)

        self.conn.execute("DELETE FROM product_state WHERE unit_id=%s", (e.unit_id,))
        self.conn.execute("UPDATE unit SET consumed_at=now() WHERE unit_id=%s", (e.unit_id,))
        log.info("SPLIT %s -> %d개 (%s)", parent_display, len(children), group)
        return children

    # ------------------------------------------------------------ MOVED
    def _moved(self, e: Moved):
        if bool(e.unit_id) == bool(e.group_id):
            raise ValueError("unit_id 와 group_id 중 정확히 하나만")
        if e.group_id:
            ids = [r[0] for r in self.conn.execute(
                "SELECT unit_id FROM product_state WHERE group_id=%s AND node_id=%s ORDER BY entered_at",
                (e.group_id, e.from_node)).fetchall()]
            if not ids:
                raise ValueError(f"{e.from_node} 에 묶음 {e.group_id} 없음")
            dst = self._node(e.to_node)
            occ = self.conn.execute("SELECT count(*) FROM product_state WHERE node_id=%s",
                                    (e.to_node,)).fetchone()[0]
            if occ + len(ids) > dst["capacity"] and dst["kind"] != "RACK":
                raise ValueError(f"{e.to_node} 용량 {dst['capacity']} < 묶음 {len(ids)}개 — 하나씩 옮겨야 합니다")
            is_rack = dst["kind"] == "RACK"
            place = self._place(e.to_node, e.slot_no, group_id=e.group_id) if is_rack else None
            if is_rack and not place:
                raise ValueError(f"{e.to_node} 빈 자리 없음")
            slot_no, pos_no = place if place else (None, None)
            for uid in ids:
                self._relocate(uid, e.from_node, e.to_node, slot_no, pos_no, is_rack,
                               e.transporter_id, e.source, keep_group=True)
            return ids
        return self._moved_unit(e)

    def _moved_unit(self, e: Moved):
        """개체 하나. 묶음에서 꺼내는 것이므로 group_id 가 끊긴다."""
        ok = self.conn.execute("""SELECT 1 FROM route r JOIN unit u ON u.line_id=r.line_id
                                   WHERE u.unit_id=%s AND r.from_node=%s AND r.to_node=%s""",
                               (e.unit_id, e.from_node, e.to_node)).fetchone()
        if not ok:
            raise ValueError(f"토폴로지에 없는 이동: {e.from_node} -> {e.to_node}")
        if not self.conn.execute("SELECT 1 FROM v_retrievable WHERE unit_id=%s", (e.unit_id,)).fetchone():
            raise ValueError(f"{e.from_node} 에서 반출 불가한 위치 — 앞의 것부터")
        # 배치는 분해 노드를 통과할 수 없다. 거기서 Split 되어야 한다.
        kind = self.conn.execute("SELECT unit_kind FROM unit WHERE unit_id=%s", (e.unit_id,)).fetchone()[0]
        if kind == "BATCH" and self._node(e.from_node)["splits"]:
            raise ValueError(f"{e.from_node} 의 배치는 이동이 아니라 분해(Split) 대상입니다")

        dst = self._node(e.to_node)
        is_rack = dst["kind"] == "RACK"
        place = self._place(e.to_node, e.slot_no, group_id=e.join_group) if is_rack else None
        if is_rack and not place:
            raise ValueError(f"{e.to_node} 빈 자리 없음")
        slot_no, pos_no = place if place else (None, None)

        src_slot, src_pos, src_access = self.conn.execute("""
            SELECT ps.slot_no, ps.pos_no, n.slot_access FROM product_state ps
              JOIN node n USING (node_id) WHERE ps.unit_id=%s""", (e.unit_id,)).fetchone()

        self._relocate(e.unit_id, e.from_node, e.to_node, slot_no, pos_no, is_rack,
                       e.transporter_id, e.source, keep_group=False, join_group=e.join_group)

        # FIFO 랙: 앞의 것이 빠지면 뒤가 밀려 내려온다.
        # 두 단계로 당긴다 — 한 문장으로 pos-1 하면 UPDATE 가 3→2 를 2→1 보다 먼저 처리할 때
        # 유니크 인덱스에 걸린다 (실제로 겪음). 음수를 경유하면 충돌이 없다.
        if src_slot is not None and src_access in ("FIFO", "RANDOM"):
            self.conn.execute("""UPDATE product_state SET pos_no = -(pos_no - 1)
                                  WHERE node_id=%s AND slot_no=%s AND pos_no > %s""",
                              (e.from_node, src_slot, src_pos))
            self.conn.execute("""UPDATE product_state SET pos_no = -pos_no
                                  WHERE node_id=%s AND slot_no=%s AND pos_no < 0""",
                              (e.from_node, src_slot))
        return e.unit_id

    def _relocate(self, uid, from_node, to_node, slot_no, pos_no, is_rack, transporter_id, source,
                  keep_group, join_group=None):
        """
        위치를 옮기고 필요하면 채번한다. 개별·묶음 이동이 공유한다.
        채번 조건: from_node 에서 DONE 이었고, 그 노드에서 아직 이름을 받지 않았을 것.
        """
        status, named_at = self.conn.execute("""
            SELECT ps.status, u.named_at FROM product_state ps JOIN unit u USING (unit_id)
             WHERE ps.unit_id=%s""", (uid,)).fetchone()
        prefix = self._node(from_node)["prefix"]
        if status == "DONE" and named_at != from_node and prefix:
            serial = self._serial(prefix)
            self.conn.execute("""
                UPDATE unit SET named_at=%s,
                  display_id = CASE WHEN display_id LIKE 'U-%%' THEN %s
                                    ELSE display_id || '-' || %s END
                 WHERE unit_id=%s""", (from_node, serial, serial, uid))

        self.conn.execute("""
            UPDATE product_state SET node_id=%s, slot_no=%s, pos_no=%s,
                   group_id = COALESCE(%s, CASE WHEN %s THEN group_id END),
                   status=%s, entered_at=now(), updated_at=now(), eta=NULL,
                   ready_at = CASE WHEN %s THEN now() END
             WHERE unit_id=%s
        """, (to_node, slot_no, pos_no, join_group, keep_group,
              "DONE" if is_rack else "WAIT", is_rack, uid))
        self._log(uid, to_node, "DONE" if is_rack else "WAIT", source, transporter_id=transporter_id)
