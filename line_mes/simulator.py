#!/usr/bin/env python3
"""
P2 라인 시뮬레이터.

설비도 로봇암도 없이 라인을 돌립니다.
contract.py 의 이벤트만 발행하므로, P4에서 실물 어댑터로 교체할 때
state_engine.py 는 한 줄도 바뀌지 않습니다.

  python simulator.py --line RESIN-1 --minutes 480 --speed 240 --spawn-every 900

흉내내는 것
  - 카메라·프린터API : 설비에 개체가 들어오면 RUN, 사이클 후 DONE  (State)
  - 로봇암·작업자   : 반출 가능한 것을 담당 자원이 옮김             (Moved)
  - 서포트 제거 작업자: 배치가 DONE 이면 부품으로 분해, 바구니에 담음   (Split)
  - 주문            : 시뮬용 주문을 자동 생성해 배치를 묶음

임시로 품고 있는 것
  - dispatch() 는 M3b 의 '후보 산출 → 배정' 이다. P5 에서 sequence_service 로 이관.
"""

import argparse
import logging
import os
import random
import time

import psycopg

from line_mes.contract import Content, Moved, Spawn, Split, SplitOutput, State
from line_mes.state_engine import StateEngine

log = logging.getLogger("sim")
# 비번은 DSN 에 두지 않는다(git). LINE_DSN 환경변수 우선, 없으면 사용자만 — 비번은 PGPASSWORD/.pgpass (tools/dev_reset.sh 참고)
DSN = os.environ.get("LINE_DSN", "postgresql://mes@localhost:5432/factory")
MOVE_TIME = {"ROBOT_ARM": (25, 8), "OPERATOR": (180, 90), "CONVEYOR": (60, 10)}
PARTS = [("PN-A-2026", "치과모델 A형"), ("PN-B-1180", "치과모델 B형"), ("PN-C-770", "서지컬가이드 C")]


class Sim:
    def __init__(self, conn, line_id, speed, seed=42):
        self.conn, self.line_id, self.speed = conn, line_id, speed
        self.engine = StateEngine(conn)
        self.rnd = random.Random(seed)
        self.clock, self.timers, self.order_seq = 0.0, [], 0
        self.entry = conn.execute("""SELECT node_id FROM v_node_order
                                      WHERE line_id=%s ORDER BY step_order LIMIT 1""",
                                  (line_id,)).fetchone()[0]
        self._seed_parts()
        self._compress_time()
        conn.execute("UPDATE transporter_state SET status='IDLE'")

    def _seed_parts(self):
        for pn, name in PARTS:
            self.conn.execute("""INSERT INTO part (part_no, name, attrs) VALUES (%s,%s,'{"tol_mm":0.15}')
                                 ON CONFLICT DO NOTHING""", (pn, name))
        self.conn.execute("INSERT INTO id_counter (prefix) VALUES ('BOX') ON CONFLICT DO NOTHING")

    def _compress_time(self):
        """
        상태 엔진과 뷰는 DB의 now() 를 쓴다. 가상 시계를 따로 굴리면 ready_at 이
        영원히 오지 않는다(겪은 버그). 토폴로지의 시간 값을 줄여 압축된 실시간으로.
        원복 = topo_sync.py --apply.
        """
        self.conn.execute("UPDATE node SET std_cycle_s = greatest(1, round(std_cycle_s/%s)) "
                          "WHERE std_cycle_s IS NOT NULL", (self.speed,))
        self.conn.execute("UPDATE node SET post_delay_s = greatest(0, round(post_delay_s/%s)) "
                          "WHERE post_delay_s > 0", (self.speed,))

    def at(self, delay_s, fn):
        self.timers.append((self.clock + delay_s, fn))

    # ------------------------------------------------------------ 주문 · 투입
    def new_order(self):
        """시뮬용 주문. 70% 단일 파트, 30% 혼재 2~3종."""
        self.order_seq += 1
        oid = f"SIM-{self.order_seq:04d}"
        k = 1 if self.rnd.random() < 0.7 else self.rnd.choice((2, 3))
        picks = self.rnd.sample(PARTS, k)
        self.conn.execute("INSERT INTO customer_order (order_id, customer, due_at) "
                          "VALUES (%s, %s, now() + interval '2 day')",
                          (oid, self.rnd.choice(("서울덴탈랩", "부산치과", "대전랩"))))
        for pn, _ in picks:
            self.conn.execute("INSERT INTO order_line VALUES (%s,%s,%s)",
                              (oid, pn, self.rnd.randint(2, 6)))
        return oid

    def spawn(self):
        oid = self.new_order()
        return self.engine.handle(Spawn(node_id=self.entry, line_id=self.line_id,
                                        order_id=oid, source="SIM"))

    # ------------------------------------------------------------ 카메라 역할
    def start_processing(self, node_id):
        cycle, kind, prefix = self.conn.execute(
            "SELECT std_cycle_s, node_kind, id_prefix FROM node WHERE node_id=%s",
            (node_id,)).fetchone()
        if kind == "RACK" or not cycle:
            return
        self.engine.handle(State(node_id=node_id, status="RUN", source="SIM", confidence=0.97))
        jitter = max(0.6, self.rnd.gauss(1.0, 0.08))
        self.at(max(0.2, cycle * jitter), lambda: self._done(node_id))

    def _done(self, node_id):
        self.engine.handle(State(node_id=node_id, status="DONE", source="SIM", confidence=0.95))
        # 분해 노드에서 배치가 끝나면 작업자가 부품으로 나눈다
        if self.conn.execute("SELECT splits_batch FROM node WHERE node_id=%s", (node_id,)).fetchone()[0]:
            self.at(1.0 / self.speed * 60, lambda: self.split_batches(node_id))

    def split_batches(self, node_id):
        rows = self.conn.execute("""
            SELECT u.unit_id, u.display_id FROM product_state ps JOIN unit u USING (unit_id)
             WHERE ps.node_id=%s AND u.unit_kind='BATCH' AND ps.status='DONE'""",
            (node_id,)).fetchall()
        for uid, disp in rows:
            contents = self.conn.execute(
                "SELECT part_no, qty - qty_scrapped FROM unit_content WHERE unit_id=%s", (uid,)).fetchall()
            outs = []
            for pn, q in contents:
                ng = sum(1 for _ in range(q) if self.rnd.random() < 0.05)   # 5% 서포트 제거 불량
                if ng:
                    self.conn.execute("""INSERT INTO part_scrap (unit_id, part_no, qty, node_id, reason, source)
                                         VALUES (%s,%s,%s,%s,'서포트 자국','SIM')""", (uid, pn, ng, node_id))
                if q - ng > 0:
                    outs.append(SplitOutput(pn, q - ng))
            if outs:
                self.engine.handle(Split(unit_id=str(uid), node_id=node_id, source="SIM",
                                         outputs=tuple(outs)))

    # ------------------------------------------------------------ 반송 (M3b 대역)
    def dispatch(self):
        """
        반출 가능한 것을 담당 자원에 배정한다.
        - v_waiting_for: ready_at 지났고 FIFO 앞이며 MAIN 으로 갈 곳이 있는 것
        - 자원 1대는 한 번에 하나, 목적지 하나에 동시 하나
        - 같은 group_id 는 한 번에 (바구니째)
        """
        rows = self.conn.execute("""
            SELECT w.unit_id, w.at_node, w.next_node, n.transporter_id, t.kind,
                   ps.group_id, u.unit_kind
              FROM v_waiting_for w
              JOIN product_state ps USING (unit_id)
              JOIN unit u USING (unit_id)
              JOIN node n ON n.node_id = w.at_node
              JOIN transporter t ON t.transporter_id = n.transporter_id AND t.is_active
              JOIN transporter_state ts ON ts.transporter_id = t.transporter_id AND ts.status <> 'MOVING'
              JOIN node dst ON dst.node_id = w.next_node AND dst.is_active AND NOT dst.draining
              JOIN node src ON src.node_id = w.at_node
             WHERE u.line_id = %s
               AND NOT (u.unit_kind = 'BATCH' AND src.splits_batch)   -- 분해 대상은 반송 안 함
               AND (SELECT count(*) FROM product_state x WHERE x.node_id = dst.node_id) < dst.capacity
             ORDER BY w.waiting_s DESC""", (self.line_id,)).fetchall()

        busy, filling, seen_groups = set(), set(), set()
        for uid, src, dst, tr_id, kind, gid, ukind in rows:
            if tr_id in busy or dst in filling:
                continue
            if gid and gid in seen_groups:
                continue
            busy.add(tr_id); filling.add(dst)
            # 묶음째 옮길지 하나씩 옮길지는 목적지 용량이 정한다.
            # 바구니는 경화기(용량 12)로는 통째로, 치수검사(용량 1)로는 하나씩.
            if gid and ukind == "PART":
                gsize = self.conn.execute("SELECT count(*) FROM product_state WHERE group_id=%s AND node_id=%s",
                                          (gid, src)).fetchone()[0]
                dcap = self.conn.execute("SELECT capacity FROM node WHERE node_id=%s", (dst,)).fetchone()[0]
                if dcap >= gsize:
                    seen_groups.add(gid)
                    self.begin_move(tr_id, kind, src, dst, group_id=gid)
                    continue
            self.begin_move(tr_id, kind, src, dst, unit_id=str(uid))

    def begin_move(self, tr_id, kind, src, dst, unit_id=None, group_id=None):
        self.conn.execute("""UPDATE transporter_state SET status='MOVING', from_node=%s, to_node=%s,
                             started_at=now(), updated_at=now() WHERE transporter_id=%s""",
                          (src, dst, tr_id))
        mu, sigma = MOVE_TIME.get(kind, (60, 10))
        dur = max(1, self.rnd.gauss(mu, sigma)) / self.speed

        def finish():
            try:
                # 부품이 랙으로 들어가면 박스 단위로 묶는다 (OK 적재 박스)
                dst_kind, by_group = self.conn.execute(
                    "SELECT node_kind, count_by_group FROM node WHERE node_id=%s", (dst,)).fetchone()
                join = None
                if unit_id and dst_kind == "RACK" and by_group:
                    join = self._current_box(dst)
                self.engine.handle(Moved(unit_id=unit_id, group_id=group_id, from_node=src, to_node=dst,
                                         transporter_id=tr_id, join_group=join, source="SIM"))
                self.start_processing(dst)
            except ValueError as ex:
                log.debug("이동 취소: %s", ex)
            finally:
                self.conn.execute("""UPDATE transporter_state SET status='IDLE', from_node=NULL,
                                     to_node=NULL, updated_at=now() WHERE transporter_id=%s""", (tr_id,))
        self.at(dur, finish)

    def _current_box(self, node_id, size=12):
        """열린 박스(12개 미만)가 있으면 그것, 없으면 새 번호."""
        row = self.conn.execute("""SELECT group_id FROM product_state WHERE node_id=%s AND group_id LIKE 'BOX-%%'
                                    GROUP BY group_id HAVING count(*) < %s ORDER BY max(entered_at) DESC LIMIT 1""",
                                (node_id, size)).fetchone()
        if row:
            return row[0]
        return self.conn.execute("UPDATE id_counter SET next_val=next_val+1 WHERE prefix='BOX' "
                                 "RETURNING 'BOX-'||lpad((next_val-1)::text,4,'0')").fetchone()[0]

    # ------------------------------------------------------------ 루프
    def run(self, minutes, spawn_every):
        end, spawn_iv = minutes * 60 / self.speed, spawn_every / self.speed
        next_spawn, t0 = 0.0, time.monotonic()
        while True:
            self.clock = time.monotonic() - t0
            if self.clock >= end:
                break
            due = [t for t in self.timers if t[0] <= self.clock]
            self.timers = [t for t in self.timers if t[0] > self.clock]
            for _, fn in sorted(due, key=lambda x: x[0]):
                try:
                    fn()
                except Exception as ex:  # noqa: BLE001
                    log.warning("타이머 실패: %s", ex)
            if self.clock >= next_spawn:
                try:
                    self.spawn(); next_spawn = self.clock + spawn_iv
                except ValueError as ex:  # 플레이트·랙 만재 = 정상적인 백프레셔
                    log.debug("투입 보류: %s", ex); next_spawn = self.clock + spawn_iv / 4
            self.dispatch()
            time.sleep(0.25)
        self.report(minutes)

    def report(self, minutes):
        q = lambda sql, *a: self.conn.execute(sql, a).fetchall()
        print(f"\n시뮬 경과 {minutes/60:.1f}h (실제 {self.clock:.0f}s · {self.speed:.0f}x · 라인 {self.line_id})\n")
        print("── 노드 현황 " + "─" * 50)
        for r in q("""SELECT node_id, label, occupancy, capacity, coalesce(display_id, display_ids, '-'),
                             coalesce(status,'IDLE') FROM v_node_status WHERE line_id=%s
                      ORDER BY step_order, node_id""", self.line_id):
            ids = r[4] if len(r[4]) < 34 else r[4][:31] + "…"
            print(f"  {r[0]:<15} {r[1]:<14} {r[2]:>2}/{r[3]:<3} {r[5]:<8} {ids}")
        print("\n── 반송 자원 " + "─" * 50)
        for r in q("SELECT transporter_id, kind, status, queued, avg_wait_s, max_wait_s FROM v_transporter_load ORDER BY 1"):
            print(f"  {r[0]:<9} {r[1]:<10} {r[2]:<8} 대기 {r[3]:>2}  평균 {r[4]:>4}s  최대 {r[5]:>5}s")
        print("\n── 플레이트 / 주문 " + "─" * 44)
        u, c = q("SELECT plates_in_use, plate_count FROM v_plate_usage WHERE line_id=%s", self.line_id)[0]
        print(f"  플레이트 {u}/{c} 사용 중")
        for r in q("""SELECT order_id, customer, ordered_qty, produced_qty, scrapped_qty, done_qty
                      FROM v_order_progress ORDER BY order_id LIMIT 6"""):
            print(f"  {r[0]}  {r[1]:<8} 주문 {r[2]:>2} / 생산 {r[3]:>2} / 폐기 {r[4]} / 완료 {r[5]}")
        done = q("""SELECT u.display_id FROM product_state ps JOIN unit u USING (unit_id)
                    JOIN node n USING (node_id) WHERE u.line_id=%s AND u.unit_kind='PART' AND n.node_kind='RACK'
                      AND NOT EXISTS (SELECT 1 FROM route r WHERE r.from_node=n.node_id AND r.edge_kind='MAIN')
                      AND EXISTS (SELECT 1 FROM route r WHERE r.to_node=n.node_id AND r.edge_kind='MAIN')
                    ORDER BY u.born_at""", self.line_id)
        print(f"\n── 완주 부품 {len(done)}개: " + ", ".join(r[0] for r in done[:5]) + (" …" if len(done) > 5 else ""))
        sc = q("SELECT node_label, sum(qty) FROM v_scrap_summary GROUP BY 1")
        if sc:
            print("── 폐기: " + ", ".join(f"{a} {b}" for a, b in sc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DSN)
    ap.add_argument("--line", default="RESIN-1")
    ap.add_argument("--minutes", type=int, default=480)
    ap.add_argument("--speed", type=float, default=240)
    ap.add_argument("--spawn-every", type=int, default=900)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(name)s %(message)s")
    with psycopg.connect(a.dsn, autocommit=True) as conn:
        Sim(conn, a.line, a.speed).run(a.minutes, a.spawn_every)


if __name__ == "__main__":
    main()
