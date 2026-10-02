"""
관측 이벤트 발행기 — 제어·폴링 코드가 라인 MES 에 State/Moved 를 "던지고 잊는" 통로.

원칙 (병존 ②-2 · 계획 §2)
  1. 논블로킹 — 호출자는 put_nowait 한 줄. PG 접속·엔진 호출은 데몬 스레드가 한다. 로봇 루프·폴링 루프는 기다리지 않는다
  2. 큐가 차면 버린다 — 관측이다. 제어는 관측 때문에 멈추지 않는다
  3. 엔진이 거부(ValueError)하면 로그만 — 관측이 제어를 판정하지 않는다. 라인은 이미 그렇게 움직였다
  4. dsn 이 비어 있으면 아무 것도 하지 않는다 — LINE_DSN 없는 인스턴스(카카오·6000)에서 무해

참조 해석은 스레드가 한다 — 호출자는 자기 어휘로 말한다:
  ("printer_serial", "Form4-…") · ("mqtt", "wash_1") · ("legacy_task_unit", "printer-1")  → node.external_ref 역조회
  cmd_id → unit (unit.cmd_id · 미소비)                                                  → Moved 의 unit_id
"""
import logging
import queue
import threading
import time
from typing import Optional

import psycopg

from line_mes.contract import Moved, State
from line_mes.state_engine import StateEngine

log = logging.getLogger("line_mes.publish")


class LinePublisher:
    def __init__(self, dsn: str, maxsize: int = 1000, name: str = "line-publisher"):
        self.dsn = dsn or ""
        self.q: "queue.Queue[dict]" = queue.Queue(maxsize=maxsize)
        self.name = name
        self.sent = self.rejected = self.dropped = 0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._node_cache: dict[tuple[str, str], Optional[str]] = {}

    # ── 호출자 쪽 (논블로킹) ─────────────────────────────────
    def enabled(self) -> bool:
        return bool(self.dsn)

    def emit_state(self, ref: tuple[str, str], status: str, source: str, confidence=None, duration_s=None) -> bool:
        return self._put({"kind": "STATE", "ref": ref, "status": status, "source": source,
                          "confidence": confidence, "duration_s": duration_s})

    def emit_moved(self, cmd_id: str, from_ref: tuple[str, str], to_ref: tuple[str, str], source: str) -> bool:
        return self._put({"kind": "MOVED", "cmd_id": cmd_id, "from_ref": from_ref, "to_ref": to_ref, "source": source})

    def _put(self, item: dict) -> bool:
        if not self.dsn:
            return False
        self._ensure_thread()
        try:
            self.q.put_nowait(item)
            return True
        except queue.Full:
            self.dropped += 1
            if self.dropped in (1, 10, 100, 1000):
                log.error("%s: 큐 만석 — 이벤트 버림 누계 %d (관측이라 버린다)", self.name, self.dropped)
            return False

    def flush(self, timeout: float = 5.0) -> bool:
        """테스트·종료용 — 큐가 빌 때까지 기다린다. 운영 코드는 부르지 않는다."""
        end = time.monotonic() + timeout
        while not self.q.empty() or self._busy:
            if time.monotonic() > end:
                return False
            time.sleep(0.02)
        return True

    # ── 스레드 쪽 ───────────────────────────────────────────
    _busy = False

    def _ensure_thread(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
                self._thread.start()

    def _run(self):
        conn = None
        while True:
            item = self.q.get()
            self._busy = True
            try:
                if conn is None or conn.closed:
                    conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)
                self._apply(conn, item)
                self.sent += 1
            except psycopg.OperationalError as ex:
                # PG 가 죽었다 — 이 이벤트는 버리고 잠깐 뒤 다시 붙는다. 제어는 모른다
                log.error("%s: PG 접속 실패 — 이벤트 버림: %s", self.name, str(ex).strip()[:120])
                conn = None
                time.sleep(2)
            except ValueError as ex:
                self.rejected += 1
                log.warning("%s: 엔진 거부(관측 불일치 · 무해): %s | %s", self.name, ex, item)
            except Exception:  # noqa: BLE001 — 스레드가 죽으면 이후 전부 사라진다
                log.exception("%s: 발행 실패 | %s", self.name, item)
            finally:
                self._busy = False
                self.q.task_done()

    def _node(self, conn, ref: tuple[str, str]) -> Optional[str]:
        if ref not in self._node_cache:
            row = conn.execute("SELECT node_id FROM node WHERE is_active AND external_ref @> %s::jsonb",
                               (psycopg.types.json.Json({ref[0]: ref[1]}),)).fetchone()
            self._node_cache[ref] = row[0] if row else None
            if not row:
                log.warning("%s: 토폴로지에 없는 참조 %s=%s — 이 참조의 이벤트는 버린다 (topology.yaml external_ref)", self.name, *ref)
        return self._node_cache[ref]

    def _apply(self, conn, item: dict):
        if item["kind"] == "STATE":
            node = self._node(conn, tuple(item["ref"]))
            if not node:
                return
            StateEngine(conn).handle(State(node_id=node, status=item["status"], source=item["source"],
                                           confidence=item["confidence"], duration_s=item["duration_s"]))
        elif item["kind"] == "MOVED":
            src, dst = self._node(conn, tuple(item["from_ref"])), self._node(conn, tuple(item["to_ref"]))
            if not (src and dst):
                return
            row = conn.execute("SELECT unit_id::text FROM unit WHERE cmd_id = %s AND consumed_at IS NULL", (item["cmd_id"],)).fetchone()
            if not row:
                # Spawn 이 안 됐던 CMD(LINE_UNTRACKED) — 이동도 기록할 개체가 없다
                log.warning("%s: cmd_id=%s 의 unit 없음 — Moved 버림 (%s → %s)", self.name, item["cmd_id"], src, dst)
                return
            tr = conn.execute("SELECT transporter_id FROM node WHERE node_id = %s", (src,)).fetchone()
            StateEngine(conn).handle(Moved(unit_id=row[0], from_node=src, to_node=dst,
                                           transporter_id=(tr[0] if tr and tr[0] else ""), source=item["source"]))
