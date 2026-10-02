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
from fastapi import APIRouter, HTTPException, Request, Response

from app.line import db
from app.line.schemas import (
    ControlMenuResponse, GroupListResponse, InboundQueueResponse, NodeListResponse, PartJudgeListResponse,
    PartListResponse, RackListResponse, RobotCommandListResponse, SlotListResponse, SlotQueueResponse,
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


def _etag(request: Request, response: Response, where: str, **params):
    """명세 §1-4: ETag = product_state 의 max(updated_at) + 행수(삭제도 잡히게). If-None-Match 가 맞으면 304.
    product_state 로 결정되지 않는 응답(R2 transporter_state · R9 group_close · R10 judgement)엔 붙이지 않는다 — 틀린 304 가 최악이다."""
    tag = _rows(f"""SELECT '"' || md5(coalesce(max(ps.updated_at)::text, '0') || ':' || count(*)) || '"' AS tag
                      FROM product_state ps JOIN unit u USING (unit_id) WHERE {where}""", **params)[0]["tag"]
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag})
    response.headers["ETag"] = tag
    return None


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
#      DB kind ROBOT_ARM → API ROBOT · 상태 MOVING(엔진·시뮬 어휘) → BUSY(FE) · 행 없으면 IDLE — 이름 바꾸기만, 계산 없음
@router.get("/lines/{line_id}/transporters", response_model=TransporterListResponse, summary="R2 반송 자원")
def transporters(line_id: str) -> TransporterListResponse:
    rows = _rows(
        """SELECT v.transporter_id, v.label,
                  CASE v.kind WHEN 'ROBOT_ARM' THEN 'ROBOT' ELSE v.kind END AS kind,
                  v.auto_dispatch,
                  CASE coalesce(v.status, 'IDLE') WHEN 'MOVING' THEN 'BUSY' ELSE coalesce(v.status, 'IDLE') END AS status,
                  v.queued, v.avg_wait_s, v.max_wait_s
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
def nodes(line_id: str, request: Request, response: Response):
    if (r304 := _etag(request, response, "u.line_id = %(line_id)s", line_id=line_id)) is not None:
        return r304
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
def wip(line_id: str, request: Request, response: Response):
    if (r304 := _etag(request, response, "u.line_id = %(line_id)s", line_id=line_id)) is not None:
        return r304
    rows = _rows(
        """SELECT ref_kind, ref, display_id, part_label, coalesce(part_qty, 0) AS part_qty,
                  node_id, node_label, coalesce(step_order, 99) AS step_order, display_status, waiting
             FROM v_wip WHERE line_id = %(line_id)s ORDER BY step_order, node_id, display_id""",
        line_id=line_id,
    )
    return WipListResponse(wip=rows)  # type: ignore[arg-type]


# R5 — 투입 대기 큐. ready(출처별 FIFO 맨 앞)는 뷰가 판정한다. key 는 표시용 이름 조합일 뿐이다.
@router.get("/nodes/{node_id}/inbound", response_model=InboundQueueResponse, summary="R5 투입 대기 큐")
def inbound(node_id: str, request: Request, response: Response):
    # 대기 큐는 "이 노드로 올 것들" 이라 라인 전체 상태로 판정한다(출처 랙이 바뀌면 큐가 바뀐다)
    if (r304 := _etag(request, response, "u.line_id IN (SELECT line_id FROM v_node_order WHERE node_id = %(node_id)s)", node_id=node_id)) is not None:
        return r304
    rows = _rows(
        """SELECT lower(ref_kind) || ':' || ref AS key, ref_kind, ref, label, qty,
                  from_node, from_label, ready, waiting_s
             FROM v_inbound_queue WHERE node_id = %(node_id)s ORDER BY from_node, pos_no, ref""",
        node_id=node_id,
    )
    return InboundQueueResponse(inbound=rows)  # type: ignore[arg-type]

# R6 — 직전 출처 랙. "직전 MAIN · 활성 · 같은 라인" 은 v_node_prev 가, 적재량은 v_rack_load 가. 여기서는 AS 만(§5-5).
#      라인 인자가 없는 경로라 활성 라인의 route 만 본다(비활성 라인의 재배치 후 경로가 섞이지 않게).
@router.get("/nodes/{node_id}/source-racks", response_model=RackListResponse, summary="R6 직전 출처 랙")
def source_racks(node_id: str) -> RackListResponse:
    rows = _rows(
        """SELECT DISTINCT l.node_id, l.label, l.slot_capacity AS capacity, l.unit_qty AS occupancy, l.slots AS slot_count
             FROM v_node_prev p
             JOIN line ln ON ln.line_id = p.line_id AND ln.is_active
             JOIN v_rack_load l ON l.node_id = p.prev_node
            WHERE p.node_id = %(node_id)s AND p.prev_kind = 'RACK'
            ORDER BY l.node_id""",
        node_id=node_id,
    )
    return RackListResponse(racks=rows)  # type: ignore[arg-type]


# R7 — 랙 칸 목록. v_rack_slot 그대로(used → occupancy 이름만).
@router.get("/racks/{node_id}/slots", response_model=SlotListResponse, summary="R7 랙 칸 목록")
def rack_slots(node_id: str) -> SlotListResponse:
    rows = _rows(
        """SELECT slot_no, capacity, used AS occupancy, head_display_id, contents
             FROM v_rack_slot WHERE node_id = %(node_id)s ORDER BY slot_no""",
        node_id=node_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail={"code": "RACK_NOT_FOUND", "message": f"{node_id} 에 칸이 없다(랙이 아니거나 비활성)"})
    return SlotListResponse(slots=rows)  # type: ignore[arg-type]


# R8 — 칸 FIFO 대기열. 4개 조인이지만 계산은 없다 — retrievable 은 v_retrievable 에 있는 행인지(LEFT JOIN),
#      파트 구성은 unit_content 원본 행. 판정 로직을 API 가 다시 쓰지 않는다(명세 §3-R8).
@router.get("/racks/{node_id}/slots/{slot_no}/queue", response_model=SlotQueueResponse, summary="R8 칸 FIFO 대기열")
def slot_queue(node_id: str, slot_no: int) -> SlotQueueResponse:
    rows = _rows(
        """SELECT sm.unit_id::text AS unit_id, sm.display_id, sm.pos_no,
                  (rt.unit_id IS NOT NULL)            AS retrievable,
                  coalesce(vc.total_qty, 0)           AS total_qty,
                  coalesce(vc.kinds, 0)::int          AS kinds
             FROM v_slot_map sm
             LEFT JOIN v_retrievable rt ON rt.unit_id = sm.unit_id
             LEFT JOIN v_unit_content vc ON vc.unit_id = sm.unit_id
            WHERE sm.node_id = %(node_id)s AND sm.slot_no = %(slot_no)s
              AND sm.unit_id IS NOT NULL                  -- v_slot_map 은 빈 자리도 낸다(generate_series) — 대기열은 든 것만
            ORDER BY sm.pos_no""",
        node_id=node_id, slot_no=slot_no,
    )
    if rows:
        ids = [r["unit_id"] for r in rows]
        contents: dict[str, list[dict]] = {i: [] for i in ids}
        for c in _rows(
            """SELECT uc.unit_id::text AS unit_id, uc.part_no, p.name AS part_name, uc.qty, uc.qty_scrapped
                 FROM unit_content uc JOIN part p USING (part_no)
                WHERE uc.unit_id::text = ANY(%(ids)s) ORDER BY uc.part_no""",
            ids=ids,
        ):
            contents[c["unit_id"]].append({k: c[k] for k in ("part_no", "part_name", "qty", "qty_scrapped")})
        for r in rows:
            r["contents"] = contents[r["unit_id"]]
    return SlotQueueResponse(queue=rows)  # type: ignore[arg-type]


# R9 — 노드의 묶음. 작업대 묶음과 랙 박스가 같은 모양이라 뷰 하나. sources 는 뷰가 jsonb 로 낸다(§5-6).
@router.get("/nodes/{node_id}/groups", response_model=GroupListResponse, summary="R9 노드의 묶음")
def groups(node_id: str) -> GroupListResponse:
    rows = _rows(
        """SELECT group_id, node_id, unit_qty, coalesce(capacity, 0) AS capacity, closed, sources
             FROM v_group_at_node WHERE node_id = %(node_id)s ORDER BY group_id""",
        node_id=node_id,
    )
    return GroupListResponse(groups=rows)  # type: ignore[arg-type]


# R10 — 부품 판정 목록. 최신 판정 + 측정 스펙(뷰) + 공차. tol 은 두 컬럼을 이름 붙여 묶기만(§5-7).
@router.get("/nodes/{node_id}/parts", response_model=PartJudgeListResponse, summary="R10 부품 판정 목록")
def node_parts(node_id: str) -> PartJudgeListResponse:
    rows = _rows(
        """SELECT unit_id::text AS unit_id, display_id, group_id, part_no, part_name, measure_spec,
                  nominal_mm, tol_mm, verdict, judge_value AS value,
                  to_char(judged_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS judged_at
             FROM v_node_parts WHERE node_id = %(node_id)s ORDER BY group_id, display_id""",
        node_id=node_id,
    )
    for r in rows:
        tol = {k: float(r.pop(k)) for k in ("nominal_mm", "tol_mm") if r.get(k) is not None}
        for k in ("nominal_mm", "tol_mm"):
            r.pop(k, None)
        r["tol"] = tol or None
    return PartJudgeListResponse(parts=rows)  # type: ignore[arg-type]


# R12 — 부품 마스터. 내용 미상 배치의 부품 추가용(S5). all=true 면 비활성도.
@router.get("/parts", response_model=PartListResponse, summary="R12 부품 마스터")
def parts(all: bool = False) -> PartListResponse:
    rows = _rows(
        """SELECT part_no, name, revision, cad_ref, attrs, is_active
             FROM part WHERE is_active OR %(all)s ORDER BY part_no""",
        all=all,
    )
    return PartListResponse(parts=rows)  # type: ignore[arg-type]

# 읽기 12개 끝. 다음 = 쓰기 W3 W2 W1 W4 W5 (계획 하위 §6 P3) — routes_write.py
