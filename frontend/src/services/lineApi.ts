/**
 * 라인 MES (v2) API
 * =================
 * 화면이 서버와 만나는 **유일한 자리**. 지금은 목업이 답하고, 백엔드 `/api/v2` 가 생기면
 * 이 파일의 함수 본문만 `authFetch` 호출로 바뀐다. 화면 코드는 그대로다.
 *
 * 대응 = `docs/plan/20260921_API명세.md`
 *   R1 GET /api/v2/lines/{line_id}/nodes
 *   R2 GET /api/v2/lines/{line_id}/transporters
 *   R3 GET /api/v2/lines/{line_id}/wip
 *   R4 GET /api/v2/lines/{line_id}/control-menu
 *
 * 🚨 목업이 채우지 못하는 값은 **0 이나 null 로 정직하게 비운다.** 그럴싸한 값을 지어내면
 *    실 API 로 바꿨을 때 화면이 달라진 이유를 못 찾는다.
 */

import type {
  ControlMenuResponse, InboundQueueResponse, InboundRow, MoveRequest,
  NodeListResponse, NodeStatusRow, StateCommand, StateRequest,
  TransporterListResponse, TransporterRow, WipListResponse, WipRow, WriteResult,
  CommandRequest, GroupListResponse, GroupRow, JudgementRequest,
  PartJudgeListResponse, PartJudgeRow, RackListResponse, RackRow,
  SlotListResponse, SlotQueueResponse, SlotQueueRow, SlotRow, SplitRequest,
  RobotCommandListResponse,
} from '../types/line';
import * as mock from '../mocks/lineMock';

/** 🔴 백엔드 v2 가 생기면 false 로. 그때 아래 fetch 분기를 채운다. */
const USE_MOCK = true;

export const DEFAULT_LINE_ID = mock.MOCK.line_id;

// ── R1 · 노드 현황 ──────────────────────────────────────────

function toNodeRow(m: mock.MockState, n: mock.MockNode, order: Record<string, number>): NodeStatusRow {
  const units = mock.at(m, n.node_id);
  const head = units[0];
  const isRack = n.node_kind === 'RACK';
  const boxes = isRack ? m.boxes.filter((b) => b.node_id === n.node_id) : [];
  const load = isRack ? mock.rackLoad(m, n.node_id) : null;

  return {
    node_id: n.node_id,
    label: n.label,
    node_kind: n.node_kind,
    node_type: n.node_type,
    ui_kind: n.ui_kind ?? null,
    group_label: n.group_label ?? n.label,
    step_order: order[n.node_id] ?? 99,
    capacity: load ? load.capacity : (n.capacity ?? 1),
    // 랙은 칸에 든 것 + 올라간 박스가 모두 점유다 (박스도 그 랙에 있다)
    occupancy: load ? load.used + boxes.length : mock.occupancy(m, n),
    status: isRack ? 'IDLE' : (head?.status ?? 'IDLE'),
    display_id: isRack ? null : (head?.display_id ?? null),
    display_ids: units.map((u) => u.display_id),
    part_label: isRack || !head ? null : mock.partLabel(head),
    part_qty: isRack
      ? units.reduce((a, u) => a + mock.qtyOf(u), 0) + boxes.reduce((a, b) => a + b.items.length, 0)
      : units.reduce((a, u) => a + mock.qtyOf(u), 0),
    elapsed_s: head?.elapsed_s ?? null,
    std_cycle_s: n.std_cycle_s ?? null,
    progress_pct: isRack ? null : mock.progress(m, n),
    // 목업엔 ready_at 시계가 없다 — v_product_display 파생이라 서버만 낼 수 있다
    settle_left_s: null,
    transport_wait_s: null,
    transporter_id: mock.transporterOf(m, n),
    // 노드 속성 jsonb — 측정 스펙 · 가동 시간 입력 여부.
    // 🚨 화면은 공정 타입이 아니라 이 값으로 분기한다 (schema.sql:85 원칙)
    attrs: n.measure || n.duration_input || n.count_by_group
      ? {
          ...(n.measure ? { measure: n.measure } : {}),
          ...(n.duration_input ? { duration_input: true } : {}),
          // 트레이·박스 단위로 세는 랙인가 + 박스 정원
          ...(n.count_by_group ? { count_by_group: true, group_capacity: n.group_capacity ?? n.capacity ?? 0 } : {}),
        }
      : null,
    slots: isRack ? mock.slotsOf(m, n.node_id) : null,
  };
}

export async function getNodes(lineId: string = DEFAULT_LINE_ID): Promise<NodeListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const order = mock.stepOrder(m);
  const nodes = m.nodes
    .map((n) => toNodeRow(m, n, order))
    .sort((a, b) => a.step_order - b.step_order || a.node_id.localeCompare(b.node_id));
  void lineId;
  return { nodes };
}

// ── R2 · 반송 자원 ──────────────────────────────────────────

export async function getTransporters(lineId: string = DEFAULT_LINE_ID): Promise<TransporterListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  // 담당 노드의 투입 대기 건수를 합쳐 큐로 본다
  const queued: Record<string, number> = {};
  m.nodes.filter((n) => n.node_kind === 'STATION').forEach((n) => {
    const t = mock.transporterOf(m, n);
    if (!t) return;
    queued[t] = (queued[t] ?? 0) + mock.inbound(m, n.node_id).length;
  });
  const transporters: TransporterRow[] = mock.TRANSPORTERS.map((t) => ({
    transporter_id: t.id,
    label: t.label,
    kind: t.kind === 'ROBOT_ARM' ? 'ROBOT' : t.kind,
    // endpoint 가 없으면 사람이 옮긴다 — 자동 배정이 아니다
    auto_dispatch: t.endpoint != null,
    status: t.endpoint == null ? 'IDLE' : (queued[t.id] ?? 0) > 0 ? 'BUSY' : 'IDLE',
    queued: queued[t.id] ?? 0,
    // 목업엔 대기 시계가 없다 — v_transporter_load 가 낸다
    avg_wait_s: 0,
    max_wait_s: 0,
  }));
  void lineId;
  return { transporters };
}

// ── R3 · 재공 파이프라인 ────────────────────────────────────

export async function getWip(lineId: string = DEFAULT_LINE_ID): Promise<WipListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const order = mock.stepOrder(m);
  const rowOf = (nodeId: string) => {
    const n = mock.node(m, nodeId);
    return {
      node_id: nodeId,
      node_label: n?.label ?? nodeId,
      step_order: order[nodeId] ?? 99,
      waiting: n?.node_kind === 'RACK',
    };
  };

  const wip: WipRow[] = [];

  // 배치 구간 = 개체 1건
  m.units.filter((u) => u.unit_kind === 'BATCH').forEach((u) => {
    wip.push({
      ref_kind: 'UNIT', ref: u.unit_id, display_id: u.display_id,
      part_label: mock.partLabel(u), part_qty: mock.qtyOf(u),
      display_status: u.status, ...rowOf(u.node_id),
    });
  });

  // 부품 구간 = 묶음 1건
  const byGroup = new Map<string, { node_id: string; status: WipRow['display_status']; n: number }>();
  m.units.filter((u) => u.unit_kind === 'PART' && u.group_id).forEach((u) => {
    const id = u.group_id as string;
    const e = byGroup.get(id);
    if (e) { e.n += 1; return; }
    byGroup.set(id, { node_id: u.node_id, status: u.status, n: 1 });
  });
  byGroup.forEach((g, id) => {
    wip.push({
      ref_kind: 'GROUP', ref: id, display_id: null,
      part_label: null, part_qty: g.n,
      display_status: g.status, ...rowOf(g.node_id),
    });
  });

  // 랙에 올라간 박스도 묶음이다
  m.boxes.forEach((b) => {
    wip.push({
      ref_kind: 'GROUP', ref: b.group_id, display_id: null,
      part_label: null, part_qty: b.items.length,
      display_status: 'DONE', ...rowOf(b.node_id ?? ''),
    });
  });

  wip.sort((a, b) => a.step_order - b.step_order || a.ref.localeCompare(b.ref));
  void lineId;
  return { wip };
}

// ── R4 · 제어 서브 메뉴 ─────────────────────────────────────

export async function getControlMenu(lineId: string = DEFAULT_LINE_ID): Promise<ControlMenuResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  void lineId;
  return { menu: mock.menu(mock.MOCK) };
}

// ── R5 · 투입 대기 큐 ───────────────────────────────────────

export async function getInbound(nodeId: string): Promise<InboundQueueResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const inbound: InboundRow[] = mock.inbound(m, nodeId).map((r) => ({
    // 박스도 묶음이다 — R5 는 UNIT / GROUP 둘로만 가른다
    key: r.kind === 'UNIT' ? `unit:${r.ref}` : `group:${r.ref}`,
    ref_kind: r.kind === 'UNIT' ? 'UNIT' : 'GROUP',
    ref: r.ref,
    label: r.label,
    qty: r.qty,
    from_node: r.from_node,
    from_label: r.from,
    ready: r.ready,
    // 목업엔 대기 시계가 없다 — v_inbound_queue 가 낸다
    waiting_s: null,
  }));
  return { inbound };
}

// ── W2 · 이동 (투입) ────────────────────────────────────────

export async function postMove(req: MoveRequest): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;

  // 박스 합류 — OK 판정한 부품 하나가 다음 랙의 담는 중인 박스에 붙는다
  if (req.join_group && req.unit_id) {
    const gid = mock.joinBox(m, req.unit_id, req.to_node);
    if (!gid) {
      return { ok: false, event_ids: [], unit_ids: [], group_id: null, message: '부품을 찾을 수 없습니다', warnings: [] };
    }
    const warnings: string[] = [];
    const rack = mock.node(m, req.to_node);
    if (mock.openBox(m, req.to_node).items.length >= mock.groupCapacity(rack)) {
      const closed = mock.closeBox(m, req.to_node);
      if (closed) {
        mock.pushLog(m, 'BOX_CLOSE', `${closed.group_id} 자동 마감 (${closed.items.length}개)`, req.actor);
        warnings.push(`${closed.group_id} 정원이 차 자동 마감됨`);
      }
    }
    return { ok: true, event_ids: [], unit_ids: [req.unit_id], group_id: gid, message: '박스 합류', warnings };
  }

  const key = req.unit_id ? `UNIT:${req.unit_id}`
    : m.boxes.some((b) => b.group_id === req.group_id) ? `BOX:${req.group_id}`
    : `GROUP:${req.group_id}`;
  const done = mock.loadInto(m, req.to_node, key);
  if (!done) {
    // 실 API 의 409 (FIFO 위반 · 용량 초과 · 경로 없음) 자리
    return { ok: false, event_ids: [], unit_ids: [], group_id: null,
             message: '투입할 수 없습니다 (FIFO 위반 · 정원 초과)', warnings: [] };
  }
  const node = mock.node(m, req.to_node);
  mock.pushLog(m, 'MOVED', `${done.label} → ${node?.label ?? req.to_node} 투입 (${done.count}개)`, req.actor);
  return { ok: true, event_ids: [], unit_ids: [], group_id: req.group_id ?? null,
           message: `${done.label} 투입 (${done.count}개)`, warnings: [] };
}

// ── W3 · 설비 상태 변경 ─────────────────────────────────────

const CMD_OF_STATUS: Record<StateCommand, string> = {
  RUN: 'start', HOLD: 'stop', DONE: 'done', ERROR: 'done',
};

export async function postState(nodeId: string, req: StateRequest): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const n = mock.node(m, nodeId);
  const cmd = CMD_OF_STATUS[req.status];
  const minutes = req.duration_s == null ? null : req.duration_s / 60;
  const ev = mock.runCmd(m, nodeId, cmd, minutes);
  if (!ev) {
    return { ok: false, event_ids: [], unit_ids: [], group_id: null,
             message: '명령을 보낼 수 없습니다 (가동 시간 미지정 · 상태 불가)', warnings: [] };
  }
  const label = mock.cmdOf(cmd)?.label ?? req.status;
  mock.pushLog(m, 'CMD', `${n?.label ?? nodeId} ${label} (${ev.from} → ${ev.to})`, req.actor);
  return { ok: true, event_ids: [], unit_ids: [], group_id: null,
           message: `${n?.label ?? nodeId} ${label}`, warnings: [] };
}

// ── 아직 엔드포인트가 없는 것 ───────────────────────────────
// 🔴 인터록 · 명령 로그는 명세에 **읽는 엔드포인트가 없다**(인터록은 §5 에서 "데이터원 없음"으로 유보).
//    실 API 가 생길 때까지 목업을 직접 읽는다 — 그때 이 두 함수만 바뀐다.

export interface InterlockRow { key: string; label: string; ok: boolean }

export function readInterlocks(nodeId: string): InterlockRow[] {
  return mock.interlockOf(mock.MOCK, nodeId).map((i) => ({ ...i }));
}

export function toggleInterlock(nodeId: string, key: string, ok: boolean): void {
  const row = mock.interlockOf(mock.MOCK, nodeId).find((i) => i.key === key);
  if (row) row.ok = ok;
}

export function readCommandLog(): { ts: string; actor: string; kind: string; text: string }[] {
  return mock.MOCK.log.map((r) => ({ ...r }));
}

// ── R6 · 직전 출처 랙 ───────────────────────────────────────

export async function getSourceRacks(nodeId: string): Promise<RackListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const racks: RackRow[] = mock.prevRacks(m, nodeId).map((r) => {
    const load = mock.rackLoad(m, r.node_id);
    return { node_id: r.node_id, label: r.label, capacity: load.capacity, occupancy: load.used, slot_count: load.slots };
  });
  return { racks };
}

// ── R7 · 랙 칸 목록 ─────────────────────────────────────────

export async function getRackSlots(rackId: string): Promise<SlotListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const slots: SlotRow[] = mock.slotsOf(mock.MOCK, rackId).map((s) => ({
    slot_no: s.slot_no,
    capacity: s.capacity,
    occupancy: s.used,
    head_display_id: s.contents[0]?.split(' ')[0] ?? null,
    contents: s.contents,
  }));
  return { slots };
}

// ── R8 · 칸 FIFO 대기열 ─────────────────────────────────────

export async function getSlotQueue(rackId: string, slotNo: number): Promise<SlotQueueResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const queue: SlotQueueRow[] = mock.queueOf(m, rackId, slotNo).map((u) => ({
    unit_id: u.unit_id,
    display_id: u.display_id,
    pos_no: u.pos_no ?? 0,
    retrievable: u.retrievable,
    total_qty: mock.qtyOf(u),
    kinds: u.contents.length,
    contents: u.contents.map((c) => ({
      part_no: c.part_no,
      part_name: m.part[c.part_no]?.name ?? c.part_no,
      qty: c.qty,
      qty_scrapped: 0,
    })),
  }));
  return { queue };
}

// ── R9 · 노드의 묶음 ────────────────────────────────────────

export async function getGroups(nodeId: string): Promise<GroupListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const capacity = mock.groupTarget(m, nodeId);
  const groups: GroupRow[] = mock.groups(m, nodeId).map((g) => ({
    group_id: g.group_id,
    node_id: nodeId,
    unit_qty: g.units.length,
    capacity,
    closed: false,
    sources: mock.groupSources(m, nodeId, g.group_id).map((s) => ({
      parent_display_id: s.parent_display_id, parts: s.parts,
    })),
  }));
  return { groups };
}

// ── R10 · 부품 판정 목록 ────────────────────────────────────

export async function getNodeParts(nodeId: string): Promise<PartJudgeListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const spec = mock.measureSpec(m, nodeId);
  const parts: PartJudgeRow[] = mock.waitingParts(m, nodeId).map((p) => {
    const v = mock.latestVerdict(m, p.unit_id);
    return {
      unit_id: p.unit_id,
      display_id: p.display_id,
      group_id: p.group_id,
      part_no: p.part_no,
      part_name: p.part_name,
      measure_spec: spec,
      tol: p.attrs,
      verdict: (v?.verdict as PartJudgeRow['verdict']) ?? null,
      value: v?.value ? (JSON.parse(v.value) as Record<string, number>) : null,
      judged_at: v ? new Date(v.ts).toISOString() : null,
    };
  });
  return { parts };
}

// ── W1 · 배치 완료 등록 (분리) ──────────────────────────────

export async function postSplit(unitId: string, req: SplitRequest): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const batch = m.units.find((u) => u.unit_id === unitId);
  if (!batch) {
    return { ok: false, event_ids: [], unit_ids: [], group_id: null, message: '배치를 찾을 수 없습니다', warnings: [] };
  }
  // outputs/scraps 를 판정 행으로 되돌린다 — 목업 엔진이 쓰는 모양
  const rows = batch.contents.map((c) => ({
    part_no: c.part_no,
    name: m.part[c.part_no]?.name ?? c.part_no,
    qty: c.qty,
    ok: req.outputs.find((o) => o.part_no === c.part_no)?.qty ?? 0,
    ng: req.scraps.find((o) => o.part_no === c.part_no)?.qty ?? 0,
    reason: req.scraps.find((o) => o.part_no === c.part_no)?.reason ?? '',
  }));
  const r = mock.splitBatch(m, batch, rows, req.node_id, req.group_id);
  mock.pushLog(m, 'JUDGE',
    `${batch.display_id} 분리 완료 (OK ${r.ok}${r.ng ? ` / NG ${r.ng}` : ''}) → ${r.group_id}`, req.actor);
  return { ok: true, event_ids: [], unit_ids: [], group_id: r.group_id,
           message: `OK ${r.ok}개 등록`, warnings: r.ng ? [`NG ${r.ng}개 폐기`] : [] };
}

// ── W4 · 부품 판정 ──────────────────────────────────────────
// 🚨 NG 는 판정 + EXIT-SCRAP 이동이 **한 트랜잭션**이다. 나눠 부르면 판정만 남고 부품이 라인에 남는다.

export async function postJudgement(req: JudgementRequest): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  const part = mock.waitingParts(m, req.node_id).find((p) => p.unit_id === req.unit_id);
  mock.judge(m, req.unit_id, req.node_id, req.verdict, req.value ? JSON.stringify(req.value) : null);
  if (req.verdict === 'NG') {
    mock.scrapPart(m, req.unit_id);
    mock.pushLog(m, 'JUDGE', `${part?.display_id ?? req.unit_id} NG · 폐기`, req.actor);
  } else {
    mock.pushLog(m, 'JUDGE', `${part?.display_id ?? req.unit_id} ${req.verdict}`, req.actor);
  }
  return { ok: true, event_ids: [], unit_ids: [req.unit_id], group_id: null, message: `${req.verdict} 판정`, warnings: [] };
}

// ── W5 · 조작 기록 (박스 수동 마감) ─────────────────────────

export async function postCommand(req: CommandRequest): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const m = mock.MOCK;
  if (req.kind === 'GROUP_CLOSE') {
    const done = mock.closeBox(m, req.target);
    if (!done) {
      return { ok: false, event_ids: [], unit_ids: [], group_id: null, message: '마감할 박스가 비어 있습니다', warnings: [] };
    }
    mock.pushLog(m, 'BOX_CLOSE', `${done.group_id} 수동 마감 (${done.items.length}개)`, req.actor);
    return { ok: true, event_ids: [], unit_ids: [], group_id: done.group_id,
             message: `${done.group_id} 마감 (${done.items.length}개)`, warnings: [] };
  }
  mock.pushLog(m, req.kind, `${req.kind} ${req.target}`, req.actor);
  return { ok: true, event_ids: [], unit_ids: [], group_id: null, message: '기록됨', warnings: [] };
}

// ── 담는 중인 박스 (읽는 엔드포인트 없음) ───────────────────
// 🔴 R9 는 **마감돼 랙에 올라간** 묶음을 본다. "지금 담는 중인 박스" 는 명세에 조회가 없다.

export function readOpenBox(rackId: string): { group_id: string; count: number; capacity: number } {
  const m = mock.MOCK;
  const box = mock.openBox(m, rackId);
  return { group_id: box.group_id, count: box.items.length, capacity: mock.groupCapacity(mock.node(m, rackId)) };
}

// ── R11 · 로봇 명령 카탈로그 ────────────────────────────────
// 🥇 카탈로그의 정본은 `topology.yaml` 이다 — API 는 명령의 내용을 알지 못하고 그대로 돌려준다.

export async function getRobotCommands(transporterId: string): Promise<RobotCommandListResponse> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const t = mock.transporterById(transporterId);
  if (!t) return { node_ids: [], manual: true, protocol: null, commands: [] };
  return {
    node_ids: t.nodes,
    manual: t.endpoint == null,
    protocol: t.endpoint?.protocol ?? null,
    commands: t.commands.map((c) => ({
      command_id: c.id, group: c.group, label: c.label, hint: c.hint,
      send: c.send, span_mm: c.span_mm, source: c.source, verified: c.verified, risk: c.risk,
    })),
  };
}

// ── W6 · 로봇 명령 실행 ─────────────────────────────────────
// 🚨 보낼 값을 요청에 싣지 않는다. command_id 만 보내고 무엇을 쓸지는 서버가 안다 —
//    클라이언트가 레지스터·비트를 실어 보낼 수 있으면 기존 「자동화 수동제어」와 같아진다.
// 🥇 이벤트가 아니다 — 위치를 바꾸지 않는다. 로봇이 실제로 옮기면 그 사실은 Moved 로 따로 온다.

export async function runRobotCommand(transporterId: string, commandId: string, actor: string): Promise<WriteResult> {
  if (!USE_MOCK) throw new Error('v2 미구현');
  const t = mock.transporterById(transporterId);
  const c = t?.commands.find((x) => x.id === commandId);
  if (!t || !c) {
    return { ok: false, event_ids: [], unit_ids: [], group_id: null, message: '없는 명령입니다', warnings: [] };
  }
  if (t.endpoint == null) {
    return { ok: false, event_ids: [], unit_ids: [], group_id: null, message: '수동 반송 자원입니다', warnings: [] };
  }
  if (!c.verified) {
    // 실 API 의 409 UNVERIFIED_COMMAND 자리 — 실물로 확인되지 않은 것은 내보내지 않는다
    return { ok: false, event_ids: [], unit_ids: [], group_id: null,
             message: '미검증 명령이라 내보내지 않았습니다 (UNVERIFIED_COMMAND)', warnings: [] };
  }
  mock.pushLog(mock.MOCK, 'DEVICE', `${t.label} · ${c.label}`, actor);
  return { ok: true, event_ids: [], unit_ids: [], group_id: null, message: `${c.label} 실행`, warnings: [] };
}
