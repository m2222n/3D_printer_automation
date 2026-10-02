"""
v2 쓰기 API — W1~W5. 요청 → line_mes.contract 이벤트 → StateEngine.handle(). 엔진 ValueError = 409(없는 것은 404).

  W3 POST /nodes/{node_id}/state    State
  W2 POST /moves                    Moved
  W1 POST /units/{unit_id}/split    Split (+ part_scrap)   🚨 내용 미상 배치는 outputs+scraps 로 unit_content 먼저
  W4 POST /judgements               judgement (+ NG 면 Moved → EXIT 엣지 도착지)  한 트랜잭션
  W5 POST /commands                 command_log (+ GROUP_CLOSE 면 group_close)
  W6 POST /transporters/{tid}/commands/{cid}   → P4

product_state 를 직접 UPDATE 하는 경로는 0건이다 (명세 §5). 여기서 하는 SQL 은 judgement · part_scrap ·
command_log · group_close INSERT 와 "내용 미상 배치 unit_content 채우기" 뿐 — 전부 append 이고 위치는 엔진만 바꾼다.
actor = 요청 body(FE 가 로그인 사용자명을 싣는다). JWT 는 공통 계정 하나라 sub 로는 사람을 못 가른다.
"""
from typing import Callable, TypeVar

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.types.json import Json

from app.line import db
from app.line.schemas import (
    ActorRequest, CommandRequest, JudgementRequest, MoveRequest, SplitRequest, StateRequest, WriteResult,
)
from line_mes.contract import Moved, Split, SplitOutput, State
from line_mes.state_engine import StateEngine

router = APIRouter(tags=["LineMES v2 · write"])
T = TypeVar("T")

_NOT_FOUND = ("없는 개체", "활성 노드가 아님", "없는 라인", "라인에 없는 개체", "없음")


def _engine(fn: Callable[[], T]) -> T:
    """엔진 거부(ValueError)를 HTTP 로. 없는 것 = 404, 나머지(FIFO 위반 · 용량 · 경로 없음 · 상태) = 409."""
    try:
        return fn()
    except ValueError as ex:
        msg = str(ex)
        code = 404 if any(k in msg for k in _NOT_FOUND) else 409
        raise HTTPException(status_code=code, detail={"code": "NOT_FOUND" if code == 404 else "ENGINE_REJECTED", "message": msg})
    except RuntimeError as ex:
        raise HTTPException(status_code=503, detail={"code": "LINE_MES_OFF", "message": str(ex)})
    except psycopg.OperationalError as ex:
        raise HTTPException(status_code=503, detail={"code": "LINE_MES_UNAVAILABLE", "message": str(ex).strip()})


def _ok(eng: StateEngine, unit_ids, group_id=None, message="", warnings=None) -> WriteResult:
    return WriteResult(ok=True, event_ids=list(eng.last_event_ids), unit_ids=[str(u) for u in unit_ids],
                       group_id=group_id, message=message, warnings=warnings or [])


# W3 — 설비 상태. 노드에 있는 개체 전부에 적용(엔진 규칙). 개체가 없으면 엔진은 무시하므로 ok=false 로 알려준다.
@router.post("/nodes/{node_id}/state", response_model=WriteResult, summary="W3 설비 상태 변경")
def post_state(node_id: str, req: StateRequest) -> WriteResult:
    if req.status not in ("RUN", "DONE", "ERROR", "HOLD"):
        raise HTTPException(status_code=422, detail={"code": "BAD_STATUS", "message": req.status})

    def run():
        with db.connection() as conn:
            eng = StateEngine(conn)
            ids = eng.handle(State(node_id=node_id, status=req.status, source="MANUAL",
                                   confidence=req.confidence, duration_s=req.duration_s))
            if not ids:
                return WriteResult(ok=False, message=f"{node_id} 에 개체가 없어 상태를 적용하지 않았다")
            return _ok(eng, ids, message=f"{node_id} {req.status} · {len(ids)}개")
    return _engine(run)


# W2 — 이동. unit_id / group_id 중 하나. 후보 노드는 화면이 R1 에서 고른다 — 여기서 검증하는 것은 엔진(route · FIFO · 용량).
@router.post("/moves", response_model=WriteResult, summary="W2 이동")
def post_move(req: MoveRequest) -> WriteResult:
    if bool(req.unit_id) == bool(req.group_id):
        raise HTTPException(status_code=422, detail={"code": "BAD_REF", "message": "unit_id 와 group_id 중 정확히 하나"})

    def run():
        with db.connection() as conn:
            eng = StateEngine(conn)
            ids = eng.handle(Moved(unit_id=req.unit_id, group_id=req.group_id, join_group=req.join_group,
                                   from_node=req.from_node, to_node=req.to_node,
                                   transporter_id=req.transporter_id or "", slot_no=req.slot_no, source="MANUAL"))
            ids = ids if isinstance(ids, list) else [ids]
            return _ok(eng, ids, group_id=req.group_id or req.join_group,
                       message=f"{req.from_node} → {req.to_node} · {len(ids)}개")
    return _engine(run)


# W1 — 배치 완료 등록(분리). 한 트랜잭션: (내용 미상이면 unit_content 채움) → Split → part_scrap.
@router.post("/units/{unit_id}/split", response_model=WriteResult, summary="W1 배치 완료 등록")
def post_split(unit_id: str, req: SplitRequest) -> WriteResult:
    def run():
        with db.connection() as conn, conn.transaction():
            has = conn.execute("SELECT count(*) FROM unit_content WHERE unit_id = %s", (unit_id,)).fetchone()["count"]
            warnings = []
            if has == 0:
                # 내용 미상 배치(주문·프리셋 없이 태어남) — 작업자가 센 값이 투입 수량이다. part_scrap 트리거가 이 행을 전제한다
                qty: dict[str, int] = {}
                for o in req.outputs: qty[o.part_no] = qty.get(o.part_no, 0) + o.qty
                for s in req.scraps:  qty[s.part_no] = qty.get(s.part_no, 0) + s.qty
                for part_no, q in qty.items():
                    conn.execute("INSERT INTO part (part_no, name) VALUES (%s, %s) ON CONFLICT (part_no) DO NOTHING", (part_no, part_no))
                    conn.execute("INSERT INTO unit_content (unit_id, part_no, qty) VALUES (%s, %s, %s)", (unit_id, part_no, q))
                warnings.append("내용 미상 배치 — 작업자 입력으로 unit_content 를 채웠다")
            eng = StateEngine(conn)
            children = eng.handle(Split(unit_id=unit_id, node_id=req.node_id, group_id=req.group_id, source="MANUAL",
                                        outputs=tuple(SplitOutput(part_no=o.part_no, qty=o.qty) for o in req.outputs)))
            for s in req.scraps:
                conn.execute("""INSERT INTO part_scrap (unit_id, part_no, qty, node_id, reason, source, msg)
                                VALUES (%s, %s, %s, %s, %s, 'MANUAL', %s)""",
                             (unit_id, s.part_no, s.qty, req.node_id, s.reason, f"actor={req.actor}"))
            gid = conn.execute("SELECT group_id FROM product_state WHERE unit_id = %s", (children[0],)).fetchone()["group_id"] if children else req.group_id
            return _ok(eng, children, group_id=gid,
                       message=f"OK {sum(o.qty for o in req.outputs)}개 등록 · NG {sum(s.qty for s in req.scraps)}개", warnings=warnings)
    return _engine(run)


# W4 — 부품 판정. append only · NG 면 같은 트랜잭션에서 EXIT 엣지 도착지로 Moved (도착지는 route 에서 — 하드코딩 없음).
@router.post("/judgements", response_model=WriteResult, summary="W4 부품 판정")
def post_judgement(req: JudgementRequest) -> WriteResult:
    if req.verdict not in ("OK", "NG", "RETEST"):
        raise HTTPException(status_code=422, detail={"code": "BAD_VERDICT", "message": req.verdict})

    def run():
        with db.connection() as conn, conn.transaction():
            here = conn.execute("SELECT node_id FROM product_state WHERE unit_id = %s", (req.unit_id,)).fetchone()
            if not here:
                raise ValueError(f"라인에 없는 개체: {req.unit_id}")
            if here["node_id"] != req.node_id:
                raise ValueError(f"{req.unit_id} 는 {here['node_id']} 에 있다")
            conn.execute("""INSERT INTO judgement (unit_id, node_id, verdict, value, note, source)
                            VALUES (%s, %s, %s, %s, %s, 'MANUAL')""",
                         (req.unit_id, req.node_id, req.verdict, Json(req.value) if req.value is not None else None,
                          (req.note or "") + f" (actor={req.actor})"))
            eng = StateEngine(conn)
            if req.verdict == "NG":
                exit_node = conn.execute("""SELECT r.to_node FROM route r JOIN unit u ON u.line_id = r.line_id
                                             WHERE u.unit_id = %s AND r.from_node = %s AND r.edge_kind = 'EXIT' LIMIT 1""",
                                         (req.unit_id, req.node_id)).fetchone()
                if not exit_node:
                    raise ValueError(f"{req.node_id} 에서 나가는 폐기(EXIT) 경로가 없다")
                eng.handle(Moved(unit_id=req.unit_id, from_node=req.node_id, to_node=exit_node["to_node"], source="MANUAL"))
                return _ok(eng, [req.unit_id], message=f"NG · {exit_node['to_node']} 로")
            return _ok(eng, [req.unit_id], message=f"{req.verdict} 판정")
    return _engine(run)


# W5 — 조작 기록. GROUP_CLOSE 면 group_close 도(정원 미달 수동 마감 — 자동 마감은 행이 안 생긴다).
@router.post("/commands", response_model=WriteResult, summary="W5 조작 기록")
def post_command(req: CommandRequest) -> WriteResult:
    def run():
        with db.connection() as conn, conn.transaction():
            result, message, warnings = "OK", "기록됨", []
            if req.kind == "GROUP_CLOSE":
                at = conn.execute("SELECT node_id, count(*) AS n FROM product_state WHERE group_id = %s GROUP BY node_id ORDER BY n DESC LIMIT 1",
                                  (req.target,)).fetchone()
                if not at:
                    raise ValueError(f"마감할 묶음이 비어 있다: {req.target}")
                done = conn.execute("""INSERT INTO group_close (group_id, node_id, actor) VALUES (%s, %s, %s)
                                       ON CONFLICT (group_id) DO NOTHING RETURNING group_id""",
                                    (req.target, at["node_id"], req.actor)).fetchone()
                if not done:
                    warnings.append(f"{req.target} 는 이미 마감돼 있었다")
                message = f"{req.target} 마감 ({at['n']}개)"
            conn.execute("""INSERT INTO command_log (actor, kind, target, payload, result)
                            VALUES (%s, %s, %s, %s, %s)""", (req.actor, req.kind, req.target, Json(req.payload or {}), result))
            return WriteResult(ok=True, group_id=req.target if req.kind == "GROUP_CLOSE" else None, message=message, warnings=warnings)
    return _engine(run)

# W6 — 로봇 명령 실행. 여기서 하는 것은 ①verified 검사 ②command_log(DEVICE) 기록 ③결과 반환 셋뿐(명세 §4-W6).
#      🚨 v2 는 Modbus·DO 를 직접 치지 않는다 — 실제 송신 경로(sequence_service Modbus · 펜던트 소켓)는 web-api 안에 없고,
#      제어권은 한 프로세스만 가져야 한다(한화). 그래서 지금은 "기록했고 보내지 않았다" 를 ok=false 로 정직하게 돌려준다.
#      실행됨(ok=true)으로 답하면 작업자가 로봇이 받은 줄 안다. 어댑터가 붙는 날 이 한 곳만 바뀐다.
@router.post("/transporters/{transporter_id}/commands/{command_id}", response_model=WriteResult, summary="W6 로봇 명령 실행")
def run_transporter_command(transporter_id: str, command_id: str, req: ActorRequest) -> WriteResult:
    def run():
        with db.connection() as conn, conn.transaction():
            t = conn.execute("SELECT label, auto_dispatch, attrs FROM transporter WHERE transporter_id = %s AND is_active", (transporter_id,)).fetchone()
            if not t:
                raise HTTPException(status_code=404, detail={"code": "TRANSPORTER_NOT_FOUND", "message": transporter_id})
            if not t["auto_dispatch"]:
                raise HTTPException(status_code=404, detail={"code": "MANUAL_TRANSPORTER", "message": f"{transporter_id} 는 수동 반송 자원 — 보낼 명령이 없다"})
            cmd = next((c for c in (t["attrs"] or {}).get("commands", []) if c.get("id") == command_id), None)
            if not cmd:
                raise HTTPException(status_code=404, detail={"code": "COMMAND_NOT_FOUND", "message": command_id})
            if not cmd.get("verified"):
                raise HTTPException(status_code=409, detail={"code": "UNVERIFIED_COMMAND", "message": f"{cmd.get('label')} — 실물로 확인되지 않은 명령은 내보내지 않는다"})
            reason = "송신 어댑터 미연결 — 기록만 남김"
            conn.execute("""INSERT INTO command_log (actor, kind, target, payload, result)
                            VALUES (%s, 'DEVICE', %s, %s, 'REJECTED')""",
                         (req.actor, transporter_id, Json({"command_id": command_id, "label": cmd.get("label"), "send": cmd.get("send"), "reason": reason})))
            return WriteResult(ok=False, message=f"{t['label']} · {cmd.get('label')} — 기록됨, 미송신", warnings=[reason])
    return _engine(run)
