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
from app.line.schemas import ControlMenuResponse

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

# 다음 = R2 R1 R3 R5 R11 (뷰 컬럼이 그대로 맞는 것부터 · 계획 하위 §6 P1)
