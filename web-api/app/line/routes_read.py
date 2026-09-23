"""
v2 읽기 API — R1~R12. 뷰를 감싼다. 계산은 뷰가, 이름 바꾸기(AS)는 여기가 (계획 §5).

  R1  GET /lines/{line_id}/nodes            v_node_status · v_node_order · v_rack_slot
  R2  GET /lines/{line_id}/transporters     v_transporter_load
  R3  GET /lines/{line_id}/wip              v_wip
  R4  GET /lines/{line_id}/control-menu     v_control_menu      ← 첫 번째. FE 가 v2 탭 표시를 이것의 404/503 으로 판단
  R5  GET /nodes/{node_id}/inbound          v_inbound_queue
  R6  GET /nodes/{node_id}/source-racks     v_node_prev · v_rack_load
  R7  GET /racks/{node_id}/slots            v_rack_slot
  R8  GET /racks/{node_id}/slots/{n}/queue  v_slot_map · v_retrievable · v_unit_summary · unit_content
  R9  GET /nodes/{node_id}/groups           v_group_at_node
  R10 GET /nodes/{node_id}/parts            v_node_parts
  R11 GET /transporters/{tid}/commands      transporter.attrs
  R12 GET /parts                            part
"""
import psycopg
from fastapi import APIRouter, HTTPException

from app.line import db
from app.line.schemas import (
    ControlMenuResponse, InboundQueueResponse, NodeListResponse, RobotCommandListResponse,
    TransporterListResponse, WipListResponse,
)

router = APIRouter(tags=["LineMES v2 · read"])


def _rows(sql: str, **params) -> list[dict]:
    """읽기 공통. LINE_DSN 이 비었거나 PG 에 못 붙으면 503 — FE 는 R4 의 404/503 으로 v2 탭을 끈다(명세 §3-R4)."""
    try:
        return db.rows(sql, **params)
    except RuntimeError as ex:                       # LINE_DSN 비어 있음
        raise HTTPException(status_code=503, detail={"code": "LINE_MES_OFF", "message": str(ex)})
    except psycopg.OperationalError as ex:           # PG 접속 실패
        raise HTTPException(status_code=503, detail={"code": "LINE_MES_UNAVAILABLE", "message": str(ex).strip()})


# R4 — 첫 번째 라우트. 뷰 그대로, 계산 없음. 활성 라인이 둘일 수 있어 line_id 로 건다(계획 §2-3).
@router.get("/lines/{line_id}/control-menu", response_model=ControlMenuResponse, summary="R4 제어 서브 메뉴")
def control_menu(line_id: str) -> ControlMenuResponse:
    rows = _rows(
        """SELECT menu_label, ui_kind, step_order, node_count, node_ids
             FROM v_control_menu WHERE line_id = %(line_id)s ORDER BY step_order, menu_label""",
        line_id=line_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "LINE_NOT_FOUND", "message": f"라인 {line_id} 에 설비가 없다(없는 라인 또는 비활성)"})
    return ControlMenuResponse(menu=rows)  # type: ignore[arg-type]

# R2 — 라인의 반송 자원. 자원은 라인에 안 묶여 있어 "그 라인 노드를 담당하는 자원" 으로 건다.
#      DB kind ROBOT_ARM → API ROBOT (FE TransporterKind) · 상태 행이 없으면 IDLE — 이름 바꾸기만, 계산 없음
@router.get("/lines/{line_id}/transporters", response_model=TransporterListResponse, summary="R2 반송 자원")
def transporters(line_id: str) -> TransporterListResponse:
    rows = _rows(
        """SELECT v.transporter_id, v.label,
                  CASE v.kind WHEN 'ROBOT_ARM' THEN 'ROBOT' ELSE v.kind END AS kind,
                  v.auto_dispatch, coalesce(v.status, 'IDLE') AS status, v.queued, v.avg_wait_s, v.max_wait_s
             FROM v_transporter_load v
            WHERE v.transporter_id IN (SELECT DISTINCT n.transporter_id FROM node n
                                         JOIN v_node_order o USING (node_id)
                                        WHERE o.line_id = %(line_id)s AND n.transporter_id IS NOT NULL)
            ORDER BY v.transporter_id""",
        line_id=line_id,
    )
    return TransporterListResponse(transporters=rows)  # type: ignore[arg-type]


# R11 — 명령 카탈로그. 정본 = topology.yaml transporters[].attrs.commands (topo_sync 가 jsonb 로 적재). API 는 내용을 모른다.
#       yaml 의 id 를 command_id 로 이름만 바꾼다. protocol 은 topo_sync 가 endpoint 를 저장하지 않아 지금은 null.
@router.get("/transporters/{transporter_id}/commands", response_model=RobotCommandListResponse, summary="R11 로봇 명령 카탈로그")
def transporter_commands(transporter_id: str) -> RobotCommandListResponse:
    t = _rows("SELECT auto_dispatch, attrs FROM transporter WHERE transporter_id = %(tid)s AND is_active", tid=transporter_id)
    if not t:
        raise HTTPException(status_code=404, detail={"code": "TRANSPORTER_NOT_FOUND", "message": transporter_id})
    nodes = _rows("SELECT node_id FROM node WHERE transporter_id = %(tid)s AND is_active ORDER BY node_id", tid=transporter_id)
    attrs = t[0]["attrs"] or {}
    commands = [{**{k: v for k, v in c.items() if k != "id"}, "command_id": c["id"]} for c in attrs.get("commands", [])]
    return RobotCommandListResponse(
        node_ids=[r["node_id"] for r in nodes],
        manual=not t[0]["auto_dispatch"],
        protocol=(attrs.get("endpoint") or {}).get("protocol"),
        commands=commands,  # type: ignore[arg-type]
    )


# R1 — 노드 현황. v_node_status 그대로 + 랙은 v_rack_slot 을 slots 로 붙인다. RACK 의 ui_kind 는 null(FE 계약).
@router.get("/lines/{line_id}/nodes", response_model=NodeListResponse, summary="R1 노드 현황")
def nodes(line_id: str) -> NodeListResponse:
    rows = _rows(
        """SELECT node_id, label, node_kind, node_type,
                  CASE WHEN node_kind = 'RACK' THEN NULL ELSE ui_kind END AS ui_kind,
                  group_label, step_order, capacity, occupancy, coalesce(status, 'IDLE') AS status,
                  display_id, display_ids, part_label, coalesce(part_qty, 0) AS part_qty,
                  elapsed_s, std_cycle_s, progress_pct, settle_left_s, transport_wait_s, transporter_id, attrs
             FROM v_node_status WHERE line_id = %(line_id)s ORDER BY step_order, node_id""",
        line_id=line_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "LINE_NOT_FOUND", "message": line_id})
    racks = [r["node_id"] for r in rows if r["node_kind"] == "RACK"]
    slots: dict[str, list[dict]] = {r: [] for r in racks}
    if racks:
        for sl in _rows("SELECT node_id, slot_no, capacity, used, contents FROM v_rack_slot WHERE node_id = ANY(%(racks)s) ORDER BY node_id, slot_no", racks=racks):
            slots[sl["node_id"]].append({k: sl[k] for k in ("slot_no", "capacity", "used", "contents")})
    for r in rows:
        r["slots"] = slots.get(r["node_id"]) if r["node_kind"] == "RACK" else None
    return NodeListResponse(nodes=rows)  # type: ignore[arg-type]


# R3 — 재공 파이프라인. 배치는 개체, 부품은 묶음 단위로 접힌 것이 뷰(v_wip)의 몫이다.
@router.get("/lines/{line_id}/wip", response_model=WipListResponse, summary="R3 재공 파이프라인")
def wip(line_id: str) -> WipListResponse:
    rows = _rows(
        """SELECT ref_kind, ref, display_id, part_label, coalesce(part_qty, 0) AS part_qty,
                  node_id, node_label, coalesce(step_order, 99) AS step_order, display_status, waiting
             FROM v_wip WHERE line_id = %(line_id)s ORDER BY step_order, node_id, display_id""",
        line_id=line_id,
    )
    return WipListResponse(wip=rows)  # type: ignore[arg-type]


# R5 — 투입 대기 큐. ready(출처별 FIFO 맨 앞)는 뷰가 판정한다. key 는 표시용 이름 조합일 뿐이다.
@router.get("/nodes/{node_id}/inbound", response_model=InboundQueueResponse, summary="R5 투입 대기 큐")
def inbound(node_id: str) -> InboundQueueResponse:
    rows = _rows(
        """SELECT lower(ref_kind) || ':' || ref AS key, ref_kind, ref, label, qty,
                  from_node, from_label, ready, waiting_s
             FROM v_inbound_queue WHERE node_id = %(node_id)s ORDER BY from_node, pos_no, ref""",
        node_id=node_id,
    )
    return InboundQueueResponse(inbound=rows)  # type: ignore[arg-type]

# 다음 = R6 R7 R8 R9 R10 R12 (계획 하위 §6 P2)
