"""
v2 응답·요청 모델. 정본 = frontend/src/types/line.ts — 필드 이름·타입을 그대로 옮긴다(계획 §5 어긋남 8곳 주의).

여기 채우는 순서 = 라우트를 붙이는 순서(R4 → R2 R1 R3 R5 R11 → R6~R10 R12 → W3 W2 W1 W4 W5 → W6).
공통은 WriteResult 하나뿐이라 먼저 둔다.
"""
from typing import Optional

from pydantic import BaseModel


# ── R4 · GET /lines/{line_id}/control-menu ──────────────────
class ControlMenuRow(BaseModel):
    menu_label: str
    ui_kind: str                       # MONITOR | BATCH_SPLIT | PART_JUDGE | TRANSPORT(FE 가 R2 로 붙임)
    step_order: int
    node_count: int
    node_ids: list[str]


class ControlMenuResponse(BaseModel):
    menu: list[ControlMenuRow]


# ── R2 · transporters ───────────────────────────────────────
class TransporterRow(BaseModel):
    transporter_id: str
    label: str
    kind: str                          # ROBOT | OPERATOR | CONVEYOR (DB 의 ROBOT_ARM 은 API 가 ROBOT 으로)
    auto_dispatch: bool
    status: str                        # IDLE | BUSY | ERROR | OFFLINE
    queued: int
    avg_wait_s: int
    max_wait_s: int


class TransporterListResponse(BaseModel):
    transporters: list[TransporterRow]


# ── R11 · transporter commands ──────────────────────────────
class RobotCommandRow(BaseModel):
    command_id: str
    group: str
    label: str
    hint: Optional[str] = None
    send: dict
    span_mm: Optional[float] = None
    source: str
    verified: bool
    risk: Optional[str] = None


class RobotCommandListResponse(BaseModel):
    node_ids: list[str]
    manual: bool
    protocol: Optional[str] = None
    commands: list[RobotCommandRow]


# ── R1 · nodes ──────────────────────────────────────────────
class RackSlotRow(BaseModel):
    slot_no: int
    capacity: int
    used: int
    contents: list[str]


class NodeStatusRow(BaseModel):
    node_id: str
    label: str
    node_kind: str
    node_type: str
    ui_kind: Optional[str] = None      # RACK 은 null
    group_label: str
    step_order: int
    capacity: int
    occupancy: int
    status: str
    display_id: Optional[str] = None
    display_ids: list[str]
    part_label: Optional[str] = None
    part_qty: int
    elapsed_s: Optional[int] = None
    std_cycle_s: Optional[int] = None
    progress_pct: Optional[int] = None
    settle_left_s: Optional[int] = None
    transport_wait_s: Optional[int] = None
    transporter_id: Optional[str] = None
    attrs: Optional[dict] = None
    slots: Optional[list[RackSlotRow]] = None


class NodeListResponse(BaseModel):
    nodes: list[NodeStatusRow]


# ── R3 · wip ────────────────────────────────────────────────
class WipRow(BaseModel):
    ref_kind: str                      # UNIT | GROUP
    ref: str
    display_id: Optional[str] = None
    part_label: Optional[str] = None
    part_qty: int
    node_id: str
    node_label: str
    step_order: int
    display_status: str
    waiting: bool


class WipListResponse(BaseModel):
    wip: list[WipRow]


# ── R5 · inbound ────────────────────────────────────────────
class InboundRow(BaseModel):
    key: str                           # 'unit:<id>' | 'group:<id>'
    ref_kind: str
    ref: str
    label: str
    qty: int
    from_node: str
    from_label: str
    ready: bool
    waiting_s: Optional[int] = None


class InboundQueueResponse(BaseModel):
    inbound: list[InboundRow]


class WriteResult(BaseModel):
    """쓰기 API 공통 응답 (명세 §1-3). 엔진 거부는 여기가 아니라 409 다."""
    ok: bool
    event_ids: list[int] = []
    unit_ids: list[str] = []
    group_id: Optional[str] = None
    message: str = ""
    warnings: list[str] = []
