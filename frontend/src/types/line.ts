/**
 * 라인 MES (v2) API 타입
 * =====================
 * 출처 = `docs/plan/20260921_API명세.md` R1~R4 + `schema.sql` 뷰 정의.
 *
 * 🚨 **필드명을 바꾸지 말 것** — 서버 응답을 그대로 받는 모양이다.
 *    목업을 실 API 로 교체할 때 화면 코드가 안 바뀌는 것이 이 파일의 목적이다.
 *
 * 🐛 명세 예시와 schema.sql 이 어긋난 곳은 **schema.sql 을 따랐다**(뷰가 실제로 내는 값):
 *   - `node_kind` : 명세 예시 `"MACHINE"` → schema.sql:59 `CHECK (node_kind IN ('STATION','RACK'))`
 *   - `part_label`: 명세 예시 `"브래킷 외 2종"` → v_unit_summary 는 `'혼재 N종'` 또는 파트넘버
 */

// ── 공통 ────────────────────────────────────────────────────

export type NodeKind = 'STATION' | 'RACK';

/** 어떤 제어 화면으로 조작하는가. STATION 에만 있다. */
export type UiKind = 'MONITOR' | 'BATCH_SPLIT' | 'PART_JUDGE'
  /** 🚨 반송은 STATION 이 아니라 v_control_menu 에 없다 — 화면이 R2 로 탭을 만든다 */
  | 'TRANSPORT';

/** product_state.status */
export type UnitStatus = 'IDLE' | 'WAIT' | 'RUN' | 'DONE' | 'HOLD' | 'ERROR';

/** v_product_display.display_status = status + `SETTLING`(완료했으나 ready_at 전) 파생 */
export type DisplayStatus = UnitStatus | 'SETTLING';

export type TransporterKind = 'ROBOT' | 'OPERATOR' | 'CONVEYOR';
export type TransporterStatus = 'IDLE' | 'BUSY' | 'ERROR' | 'OFFLINE';

// ── R1 · GET /lines/{line_id}/nodes ─────────────────────────

/** 랙 칸 하나. `contents` 는 앞(반출 차례)부터. */
export interface RackSlotRow {
  slot_no: number;
  capacity: number;
  used: number;
  /** 'P9-W9 (3종)' 처럼 사람이 읽는 한 줄. pos_no 오름차순 */
  contents: string[];
}

export interface NodeStatusRow {
  node_id: string;
  label: string;
  node_kind: NodeKind;
  node_type: string;
  /** STATION 만. RACK 은 조작 화면이 없다 */
  ui_kind: UiKind | null;
  /** 서브 메뉴·열 묶음 이름. 없으면 label 이 들어온다 */
  group_label: string;
  step_order: number;
  capacity: number;
  occupancy: number;
  status: DisplayStatus;
  display_id: string | null;
  display_ids: string[];
  /** 한 종이면 파트넘버, 여러 종이면 '혼재 N종' */
  part_label: string | null;
  part_qty: number;
  elapsed_s: number | null;
  std_cycle_s: number | null;
  progress_pct: number | null;
  /** 완료했으나 아직 못 꺼낸다(건조·냉각) */
  settle_left_s: number | null;
  /** 꺼낼 수 있는데 아직 안 옮겨갔다 */
  transport_wait_s: number | null;
  /** 이 노드를 담당하는 반송 자원. S8 의 '담당 구간' 은 이 키로 묶는다 */
  transporter_id: string | null;
  /** 노드 속성 jsonb (measure 등). 타입은 노드마다 다르다 */
  attrs: Record<string, unknown> | null;
  /** RACK 일 때만 */
  slots: RackSlotRow[] | null;
}

export interface NodeListResponse {
  nodes: NodeStatusRow[];
}

// ── R2 · GET /lines/{line_id}/transporters ──────────────────

export interface TransporterRow {
  transporter_id: string;
  label: string;
  kind: TransporterKind;
  auto_dispatch: boolean;
  status: TransporterStatus;
  queued: number;
  avg_wait_s: number;
  max_wait_s: number;
}

export interface TransporterListResponse {
  transporters: TransporterRow[];
}

// ── R3 · GET /lines/{line_id}/wip ───────────────────────────

/** UNIT = 개체 1건(배치 구간) · GROUP = 묶음 1건(부품 구간) */
export type WipRefKind = 'UNIT' | 'GROUP';

export interface WipRow {
  ref_kind: WipRefKind;
  ref: string;
  display_id: string | null;
  part_label: string | null;
  part_qty: number;
  node_id: string;
  node_label: string;
  step_order: number;
  display_status: DisplayStatus;
  /** 랙에서 다음 공정을 기다리는 중 */
  waiting: boolean;
}

export interface WipListResponse {
  wip: WipRow[];
}

// ── R4 · GET /lines/{line_id}/control-menu ──────────────────

export interface ControlMenuRow {
  menu_label: string;
  ui_kind: UiKind;
  step_order: number;
  node_count: number;
  node_ids: string[];
}

export interface ControlMenuResponse {
  menu: ControlMenuRow[];
}

// ── 표시 보조 ───────────────────────────────────────────────

const STATUS_LABEL: Record<DisplayStatus, string> = {
  IDLE: '비어 있음',
  WAIT: '대기',
  RUN: '가동 중',
  SETTLING: '건조·냉각',
  DONE: '완료',
  HOLD: '정지',
  ERROR: '이상',
};

export function statusLabel(s: DisplayStatus): string {
  return STATUS_LABEL[s] ?? s;
}

/** 초 → '12분 30초'. `ctl_logic.js` 의 L.fmt 와 같은 규칙. */
export function formatElapsed(sec: number | null): string {
  if (sec == null) return '-';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m <= 0) return `${s}초`;
  return s ? `${m}분 ${s}초` : `${m}분`;
}

// ── R5 · GET /nodes/{node_id}/inbound ───────────────────────

export interface InboundRow {
  /** 'unit:<id>' 또는 'group:<id>' */
  key: string;
  ref_kind: WipRefKind;
  ref: string;
  label: string;
  qty: number;
  from_node: string;
  from_label: string;
  /** 출처별 맨 앞(FIFO)인가 — 뷰가 판정한다 */
  ready: boolean;
  waiting_s: number | null;
}

export interface InboundQueueResponse {
  inbound: InboundRow[];
}

// ── 쓰기 공통 (§1-3) ────────────────────────────────────────

/**
 * 🚨 `source` 는 요청 필드가 아니다 — 이 API 를 통과한 쓰기는 서버가 `MANUAL` 로 고정한다.
 *    사칭할 수 있으면 "어디가 아직 수동인가" 지표가 무너진다.
 */
export interface WriteResult {
  ok: boolean;
  event_ids: number[];
  unit_ids: string[];
  group_id: string | null;
  message: string;
  warnings: string[];
}

// ── W2 · POST /moves ────────────────────────────────────────

export interface MoveRequest {
  /** unit_id · group_id 중 정확히 하나 */
  unit_id?: string;
  group_id?: string;
  from_node: string;
  to_node: string;
  transporter_id?: string | null;
  slot_no?: number | null;
  join_group?: string | null;
  actor: string;
}

// ── W3 · POST /nodes/{node_id}/state ────────────────────────

export type StateCommand = 'RUN' | 'DONE' | 'HOLD' | 'ERROR';

export interface StateRequest {
  status: StateCommand;
  /** 작업별 가동 시간(초). 없으면 std_cycle_s */
  duration_s?: number | null;
  confidence?: number | null;
  actor: string;
}

// ── R6 · GET /nodes/{node_id}/source-racks ──────────────────

export interface RackRow {
  node_id: string;
  label: string;
  capacity: number;
  occupancy: number;
  slot_count: number;
}

export interface RackListResponse {
  racks: RackRow[];
}

// ── R7 · GET /racks/{node_id}/slots ─────────────────────────

export interface SlotRow {
  slot_no: number;
  capacity: number;
  occupancy: number;
  head_display_id: string | null;
  /** 칸 안에 든 것을 한 줄로 — 'P9-W9 (3종)' */
  contents: string[];
}

export interface SlotListResponse {
  slots: SlotRow[];
}

// ── R8 · GET /racks/{node_id}/slots/{slot_no}/queue ─────────

export interface SlotContent {
  part_no: string;
  part_name: string;
  qty: number;
  qty_scrapped: number;
}

export interface SlotQueueRow {
  unit_id: string;
  display_id: string;
  pos_no: number;
  /** v_retrievable 에 있는 행인가 — 판정 로직을 화면이 다시 쓰지 않는다 */
  retrievable: boolean;
  total_qty: number;
  kinds: number;
  contents: SlotContent[];
}

export interface SlotQueueResponse {
  queue: SlotQueueRow[];
}

// ── R9 · GET /nodes/{node_id}/groups ────────────────────────

export interface GroupSourceRow {
  parent_display_id: string;
  parts: Record<string, number>;
}

export interface GroupRow {
  group_id: string;
  node_id: string;
  unit_qty: number;
  /** 박스 정원 — node.capacity 에서 온다(하드코딩 아님) */
  capacity: number;
  closed: boolean;
  sources: GroupSourceRow[];
}

export interface GroupListResponse {
  groups: GroupRow[];
}

// ── R10 · GET /nodes/{node_id}/parts ────────────────────────

export interface MeasureSpec {
  key: string;
  label: string;
  unit: string;
}

export interface PartJudgeRow {
  unit_id: string;
  display_id: string;
  group_id: string | null;
  part_no: string;
  part_name: string;
  measure_spec: MeasureSpec | null;
  tol: { nominal_mm?: number; tol_mm?: number } | null;
  verdict: 'OK' | 'NG' | 'RETEST' | null;
  value: Record<string, number> | null;
  judged_at: string | null;
}

export interface PartJudgeListResponse {
  parts: PartJudgeRow[];
}

// ── W1 · POST /units/{unit_id}/split ────────────────────────

export interface SplitRequest {
  node_id: string;
  /** 🚨 NG 는 여기 넣지 않는다 — 부품 unit 이 생기면 안 된다 */
  outputs: { part_no: string; qty: number }[];
  /** part_scrap 으로 수량 차감. unit 이 생기지 않는다 */
  scraps: { part_no: string; qty: number; reason: string }[];
  /** null 이면 새 묶음, 값이 있으면 이어 담기. 🔴 서버 기본값을 정하지 않는다 */
  group_id: string | null;
  actor: string;
}

// ── W4 · POST /judgements ───────────────────────────────────

export interface JudgementRequest {
  unit_id: string;
  node_id: string;
  verdict: 'OK' | 'NG' | 'RETEST';
  value: Record<string, number> | null;
  note: string | null;
  actor: string;
}

// ── W5 · POST /commands ─────────────────────────────────────

export interface CommandRequest {
  kind: string;
  target: string;
  payload: Record<string, unknown>;
  actor: string;
}

// ── R11 · GET /transporters/{transporter_id}/commands ───────

/** 화면은 이 값을 **그대로 찍어 보여준다** — 해석하지 않는다. */
export interface CommandSend {
  kind: 'DO' | 'MODBUS' | 'SOCKET';
  ch?: string;
  bits?: number[];
  pulse_s?: number;
  reg?: number;
  value?: number;
  then?: { reg: number; value: number };
  port?: number;
  msg?: string;
}

export interface RobotCommandRow {
  command_id: string;
  group: string;
  label: string;
  hint?: string;
  send: CommandSend;
  /** 그리퍼 상태의 벌림 폭. 이산값이라 임의 폭 입력이 없다 */
  span_mm?: number;
  /** 🥇 이 값이 어디서 왔나. 작업자가 타이핑하지 않았으므로 추적 근거가 대신 있어야 한다 */
  source: string;
  /** false 면 화면이 실행을 잠그고 값만 보여준다. W6 도 409 로 거부한다 */
  verified: boolean;
  risk: string;
}

export interface RobotCommandListResponse {
  /** 담당 구간 — R1 을 transporter_id 로 묶은 결과와 같다 */
  node_ids: string[];
  /** endpoint 가 없으면 수동 반송이라 보낼 명령이 없다 */
  manual: boolean;
  protocol: string | null;
  commands: RobotCommandRow[];
}

// ── R12 · GET /parts ────────────────────────────────────────
// 내용 미상 배치(unit_content 0행)의 파트별 판정에서 작업자가 부품을 고를 목록.
// unit_content.part_no 가 part FK 라 자유 입력이 아니라 여기서 고른다.

export interface PartRow {
  part_no: string;
  name: string;
  revision: string | null;
  cad_ref: string | null;
  attrs: Record<string, unknown> | null;
  is_active: boolean;
}

export interface PartListResponse {
  parts: PartRow[];
}
