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
from fastapi import APIRouter

router = APIRouter(tags=["LineMES v2 · read"])

# 라우트는 계획 §6 순서로 여기 붙인다. 지금은 비어 있다 — /api/v2/* 가 404 라 FE 는 목업으로 동작한다.
