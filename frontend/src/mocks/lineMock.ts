/**
 * 라인 MES 목업 — 서버 역할
 * =========================
 * 출처 = `docs/juhee/07_FE_병합_스냅샷/fe_merge/ctl_logic.js`(와이어프레임 원본 로직). 데이터는 손으로 옮겨 적지 않고
 * 그대로 떼어 왔고, 로직은 **지금 화면이 쓰는 것만** 옮겼다. 나머지(판정·분리·박스·명령)는
 * 그 화면이 들어올 때 같이 옮긴다.
 *
 * 🚨 화면(components/)은 이 파일을 import 하지 않는다. `services/lineApi.ts` 만 참조한다.
 *    실 API 로 바꿀 때 지우는 것은 이 파일 하나다.
 *
 * 모양은 `schema.sql` 의 테이블(node · route · unit · unit_content)과 같다.
 * 설비를 늘리려면 NODES 에 줄을 더하면 화면이 따라온다.
 */

import type { NodeKind, UiKind, UnitStatus } from '../types/line';

// ── 모양 ────────────────────────────────────────────────────

export interface MockSlotDef {
  slot_no: number;
  capacity: number;
}

export interface MockMeasureSpec {
  key: string;
  label: string;
  unit: string;
}

export interface MockNode {
  node_id: string;
  node_kind: NodeKind;
  node_type: string;
  label: string;
  ui_kind?: UiKind;
  /** 서브 메뉴 이름. 없으면 label */
  group_label?: string;
  /** 여러 공정을 한 탭으로 묶는다 (출력 · 세척) */
  menu_group?: string;
  capacity?: number;
  std_cycle_s?: number;
  /** 완료 후 꺼낼 수 있기까지 (건조·냉각) */
  post_delay_s?: number;
  /** 시작할 때 가동 시간을 받는가 */
  duration_input?: boolean;
  splits_batch?: boolean;
  id_prefix?: string;
  measure?: MockMeasureSpec;
  slot_access?: 'FIFO' | 'LIFO' | 'RANDOM';
  /** 트레이·박스 단위로 세는 랙 */
  count_by_group?: boolean;
  group_capacity?: number;
  slots?: MockSlotDef[];
}

export interface MockRoute {
  from: string;
  to: string;
  kind: 'MAIN' | 'EXIT';
}

export interface MockContent {
  part_no: string;
  qty: number;
}

export interface MockUnit {
  unit_id: string;
  unit_kind: 'BATCH' | 'PART';
  display_id: string;
  order_id?: string;
  node_id: string;
  status: UnitStatus;
  contents: MockContent[];
  slot_no?: number | null;
  pos_no?: number | null;
  elapsed_s?: number | null;
  plan_s?: number | null;
  group_id?: string;
  parent_display_id?: string;
}

export interface MockPart {
  name: string;
  cad_ref: string | null;
  attrs: { tol_mm?: number; nominal_mm?: number };
}

export interface MockBoxItem {
  unit_id: string;
  display_id: string;
  part_no: string;
  order_id?: string;
}

export interface MockBox {
  group_id: string;
  node_id: string | null;
  items: MockBoxItem[];
}

export interface MockInterlock {
  key: string;
  label: string;
  ok: boolean;
}

export interface MockLogRow {
  ts: string;
  actor: string;
  kind: string;
  text: string;
}

export interface MockJudgement {
  ts: number;
  unit_id: string;
  node_id: string;
  verdict: string;
  value: string | null;
  note: string | null;
  source: string;
}

export interface MockState {
  line_id: string;
  nodes: MockNode[];
  routes: MockRoute[];
  part: Record<string, MockPart>;
  units: MockUnit[];
  id_counter: Record<string, number>;
  group_seq: number;
  box: Record<string, { group_id: string; items: MockBoxItem[] }>;
  boxes: MockBox[];
  box_seq: number;
  interlock: Record<string, MockInterlock[]>;
  log: MockLogRow[];
  judgement: MockJudgement[];
  NG_REASONS: string[];
}

/** 투입 대기 한 줄. 출처마다 맨 앞 것만 `ready`. */
export interface InboundRow {
  key: string;
  kind: 'BOX' | 'UNIT' | 'GROUP';
  ref: string;
  label: string;
  qty: number;
  from: string;
  from_node: string;
  ready: boolean;
}

// ══ 목업 데이터 — ctl_logic.js 원본 ═══════════════════════════

export const MOCK: MockState = {
  line_id: 'RESIN-1',

  // node. ui_kind 가 어떤 화면으로 조작할지 정한다.
  nodes: [
    // 랙
    { node_id: 'RK-WSH-DONE-01', node_kind: 'RACK', node_type: 'BUFFER', label: '세척기 완료 랙 1',
      slot_access: 'FIFO', slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },
    { node_id: 'RK-PRT-DONE-01', node_kind: 'RACK', node_type: 'BUFFER', label: '프린터 완료 랙 1',
      slot_access: 'FIFO', slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },
    { node_id: 'RK-PRE-PRT-01', node_kind: 'RACK', node_type: 'BUFFER', label: '프린터 대기 랙 1',
      slot_access: 'FIFO', slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },
    { node_id: 'RK-CUR-WAIT-01', node_kind: 'RACK', node_type: 'BUFFER', label: '경화 대기 랙 1',
      slot_access: 'FIFO', count_by_group: true, group_capacity: 12,   // 박스 1개에 부품 12
      slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },
    { node_id: 'RK-BPD-WAIT-01', node_kind: 'RACK', node_type: 'BUFFER', label: '빈피킹 대기 랙 1',
      slot_access: 'FIFO', count_by_group: true, group_capacity: 12,   // 트레이 1개에 부품 12
      slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },

    // 설비 — group_label 이 서브 메뉴 이름, ui_kind 가 화면 종류
    { node_id: 'PRT-01', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
      group_label: '프린터', menu_group: '출력 · 세척', label: 'ShrewdStork', capacity: 1, std_cycle_s: 5400 },
    { node_id: 'PRT-02', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
      group_label: '프린터', menu_group: '출력 · 세척', label: 'CorrectPelican', capacity: 1, std_cycle_s: 5400 },
    { node_id: 'PRT-03', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
      group_label: '프린터', menu_group: '출력 · 세척', label: 'HeavenlyTuna', capacity: 1, std_cycle_s: 5400 },
    { node_id: 'PRT-04', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
      group_label: '프린터', menu_group: '출력 · 세척', label: 'CapableGecko', capacity: 1, std_cycle_s: 5400 },

    { node_id: 'WSH-01', node_kind: 'STATION', node_type: 'WASHER', ui_kind: 'MONITOR',
      group_label: '세척기', menu_group: '출력 · 세척', label: '세척기 1호기', capacity: 1, std_cycle_s: 600, post_delay_s: 300,
      duration_input: true },
    { node_id: 'WSH-02', node_kind: 'STATION', node_type: 'WASHER', ui_kind: 'MONITOR',
      group_label: '세척기', menu_group: '출력 · 세척', label: '세척기 2호기', capacity: 1, std_cycle_s: 600, post_delay_s: 300,
      duration_input: true },

    { node_id: 'SEP-01', node_kind: 'STATION', node_type: 'SEPARATION', ui_kind: 'BATCH_SPLIT',
      group_label: '부품 분리', label: '부품 분리대 1', capacity: 16, std_cycle_s: 300,
      splits_batch: true, id_prefix: 'S' },

    { node_id: 'SUP-01', node_kind: 'STATION', node_type: 'SUPPORT_REMOVAL', ui_kind: 'PART_JUDGE',
      group_label: '서포트 제거', label: '서포트 제거대 1', capacity: 16, std_cycle_s: 480 },

    { node_id: 'CUR-01', node_kind: 'STATION', node_type: 'CURER', ui_kind: 'MONITOR',
      group_label: '경화기', label: '경화기 1호기', capacity: 12, std_cycle_s: 1800,
      duration_input: true },
    { node_id: 'CUR-02', node_kind: 'STATION', node_type: 'CURER', ui_kind: 'MONITOR',
      group_label: '경화기', label: '경화기 2호기', capacity: 12, std_cycle_s: 1800,
      duration_input: true },

    { node_id: 'INS-01', node_kind: 'STATION', node_type: 'INSPECT', ui_kind: 'PART_JUDGE',
      group_label: '치수검사', label: '치수검사', capacity: 1, std_cycle_s: 300, id_prefix: 'D',
      measure: { key: 'height_mm', label: '높이', unit: 'mm' } },   // 측정 스펙이 있으면 입력란이 뜬다

    { node_id: 'BPD-01', node_kind: 'STATION', node_type: 'BEAMPICK', ui_kind: 'MONITOR',
      group_label: '빈피킹·드릴링·트림', label: '빈피킹/드릴링/트림', capacity: 1, std_cycle_s: 900 }
  ],

  // route. MAIN 만 순서 계산과 "다음/직전 공정" 파생의 대상.
  routes: [
    { from: 'RK-PRE-PRT-01', to: 'PRT-01', kind: 'MAIN' }, { from: 'RK-PRE-PRT-01', to: 'PRT-02', kind: 'MAIN' },
    { from: 'RK-PRE-PRT-01', to: 'PRT-03', kind: 'MAIN' }, { from: 'RK-PRE-PRT-01', to: 'PRT-04', kind: 'MAIN' },
    { from: 'PRT-01', to: 'RK-PRT-DONE-01', kind: 'MAIN' }, { from: 'PRT-02', to: 'RK-PRT-DONE-01', kind: 'MAIN' },
    { from: 'PRT-03', to: 'RK-PRT-DONE-01', kind: 'MAIN' }, { from: 'PRT-04', to: 'RK-PRT-DONE-01', kind: 'MAIN' },
    { from: 'RK-PRT-DONE-01', to: 'WSH-01', kind: 'MAIN' }, { from: 'RK-PRT-DONE-01', to: 'WSH-02', kind: 'MAIN' },
    { from: 'WSH-01', to: 'RK-WSH-DONE-01', kind: 'MAIN' }, { from: 'WSH-02', to: 'RK-WSH-DONE-01', kind: 'MAIN' },
    { from: 'RK-WSH-DONE-01', to: 'SEP-01', kind: 'MAIN' },
    { from: 'SEP-01', to: 'SUP-01', kind: 'MAIN' },              // 같은 작업대. 논리적 단계 전환
    { from: 'SUP-01', to: 'RK-CUR-WAIT-01', kind: 'MAIN' },
    { from: 'RK-CUR-WAIT-01', to: 'CUR-01', kind: 'MAIN' },
    { from: 'RK-CUR-WAIT-01', to: 'CUR-02', kind: 'MAIN' },
    { from: 'CUR-01', to: 'INS-01', kind: 'MAIN' }, { from: 'CUR-02', to: 'INS-01', kind: 'MAIN' },
    { from: 'INS-01', to: 'RK-BPD-WAIT-01', kind: 'MAIN' },
    { from: 'RK-BPD-WAIT-01', to: 'BPD-01', kind: 'MAIN' },
    { from: 'SEP-01', to: 'EXIT-SCRAP', kind: 'EXIT' }, { from: 'SUP-01', to: 'EXIT-SCRAP', kind: 'EXIT' },
    { from: 'INS-01', to: 'EXIT-SCRAP', kind: 'EXIT' }
  ],

  part: {
    'PN-A-2026': { name: '치과모델 A형', cad_ref: 'A-2026.stl', attrs: { tol_mm: 0.15, nominal_mm: 12.0 } },
    'PN-B-1180': { name: '치과모델 B형', cad_ref: 'B-1180.stl', attrs: { tol_mm: 0.15, nominal_mm: 9.0 } },
    'PN-C-770':  { name: '서지컬가이드 C', cad_ref: null,       attrs: { tol_mm: 0.20, nominal_mm: 15.0 } }
  },

  // unit + product_state + unit_content 을 한 줄로.
  //   unit_kind BATCH = 배치(플레이트 분량) / PART = 분리된 개별 부품
  units: [
    // 세척기 완료 랙에서 분리를 기다리는 배치들.
    // 🔴 혼재가 기본이다 — 한 배치에 파트넘버가 다른 부품이 섞인다 (보통 2~3종).
    //    단일 파트는 예외 케이스로 하나만 둔다.
    { unit_id: 'u-9',  unit_kind: 'BATCH', display_id: 'P9-W9',   order_id: 'SIM-0043',
      node_id: 'RK-WSH-DONE-01', slot_no: 1, pos_no: 1, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 6 }, { part_no: 'PN-B-1180', qty: 3 },
                 { part_no: 'PN-C-770', qty: 3 }] },                       // 3종
    { unit_id: 'u-10', unit_kind: 'BATCH', display_id: 'P10-W10', order_id: 'SIM-0043',
      node_id: 'RK-WSH-DONE-01', slot_no: 1, pos_no: 2, status: 'DONE',
      contents: [{ part_no: 'PN-C-770', qty: 6 }] },                       // 1종 (예외)
    { unit_id: 'u-8',  unit_kind: 'BATCH', display_id: 'P8-W8',   order_id: 'SIM-0042',
      node_id: 'RK-WSH-DONE-01', slot_no: 1, pos_no: 3, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 8 }, { part_no: 'PN-B-1180', qty: 4 }] },  // 2종

    // 칸 2 — 6개짜리 두 장. 경화기 정원 12를 채우려면 두 배치를 한 묶음에 모아야 한다.
    { unit_id: 'u-11', unit_kind: 'BATCH', display_id: 'P11-W11', order_id: 'SIM-0044',
      node_id: 'RK-WSH-DONE-01', slot_no: 2, pos_no: 1, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 4 }, { part_no: 'PN-B-1180', qty: 2 }] },
    { unit_id: 'u-12', unit_kind: 'BATCH', display_id: 'P12-W12', order_id: 'SIM-0044',
      node_id: 'RK-WSH-DONE-01', slot_no: 2, pos_no: 2, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 3 }, { part_no: 'PN-C-770', qty: 3 }] },
    { unit_id: 'u-13b', unit_kind: 'BATCH', display_id: 'P13-W13', order_id: 'SIM-0045',
      node_id: 'RK-WSH-DONE-01', slot_no: 2, pos_no: 3, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 5 }, { part_no: 'PN-B-1180', qty: 2 },
                 { part_no: 'PN-C-770', qty: 1 }] },                   // 3종
    // 🆕 내용 미상 배치 — 주문도 프리셋도 없이 /local/print 로 태어난 형태 (order_id 없음 · contents 0행).
    //    S5 ④ 에서 작업자가 R12 목록으로 부품을 직접 추가해야 완료할 수 있다. FIFO 라 앞 3장 뒤에 차례가 온다.
    { unit_id: 'u-22', unit_kind: 'BATCH', display_id: 'U-9c41d0e2',
      node_id: 'RK-WSH-DONE-01', slot_no: 1, pos_no: 4, status: 'DONE', contents: [] },
    { unit_id: 'u-14b', unit_kind: 'BATCH', display_id: 'P14-W14', order_id: 'SIM-0045',
      node_id: 'RK-WSH-DONE-01', slot_no: 2, pos_no: 4, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 6 }] },                  // 1종

    // 프린터 대기 랙 — MONITOR 화면의 투입 대기열
    { unit_id: 'u-20', unit_kind: 'BATCH', display_id: 'U-3f2a91c4', order_id: 'SIM-0045',
      node_id: 'RK-PRE-PRT-01', slot_no: 1, pos_no: 1, status: 'DONE',
      contents: [{ part_no: 'PN-A-2026', qty: 8 }] },
    { unit_id: 'u-21', unit_kind: 'BATCH', display_id: 'U-77b0e2da', order_id: 'SIM-0045',
      node_id: 'RK-PRE-PRT-01', slot_no: 1, pos_no: 2, status: 'DONE',
      contents: [{ part_no: 'PN-C-770', qty: 6 }] },

    // 설비 점유
    { unit_id: 'u-13', unit_kind: 'BATCH', display_id: 'P13', order_id: 'SIM-0044',
      node_id: 'PRT-01', status: 'RUN', elapsed_s: 2100,
      contents: [{ part_no: 'PN-A-2026', qty: 8 }] },
    { unit_id: 'u-14', unit_kind: 'BATCH', display_id: 'P14', order_id: 'SIM-0044',
      node_id: 'PRT-02', status: 'RUN', elapsed_s: 3600,
      contents: [{ part_no: 'PN-B-1180', qty: 6 }] },
    { unit_id: 'u-15', unit_kind: 'BATCH', display_id: 'P15-W15', order_id: 'SIM-0041',
      node_id: 'WSH-01', status: 'RUN', elapsed_s: 330,
      contents: [{ part_no: 'PN-A-2026', qty: 10 }] },
    { unit_id: 'u-16', unit_kind: 'BATCH', display_id: 'P16', order_id: 'SIM-0045',
      node_id: 'PRT-03', status: 'WAIT', elapsed_s: 0,
      contents: [{ part_no: 'PN-C-770', qty: 6 }] },
    { unit_id: 'u-17', unit_kind: 'BATCH', display_id: 'P17-W17', order_id: 'SIM-0045',
      node_id: 'WSH-02', status: 'WAIT', elapsed_s: 0,
      contents: [{ part_no: 'PN-B-1180', qty: 8 }] },

    // 서포트 제거대에서 판정을 기다리는 부품 (앞 배치 P6-W6 분리분)
    { unit_id: 'p-1', unit_kind: 'PART', display_id: 'P6-W6-S31', parent_display_id: 'P6-W6',
      order_id: 'SIM-0041', node_id: 'SUP-01', group_id: 'G-P6-W6', status: 'WAIT',
      contents: [{ part_no: 'PN-A-2026', qty: 1 }] },
    { unit_id: 'p-2', unit_kind: 'PART', display_id: 'P6-W6-S32', parent_display_id: 'P6-W6',
      order_id: 'SIM-0041', node_id: 'SUP-01', group_id: 'G-P6-W6', status: 'WAIT',
      contents: [{ part_no: 'PN-A-2026', qty: 1 }] },
    { unit_id: 'p-3', unit_kind: 'PART', display_id: 'P6-W6-S33', parent_display_id: 'P6-W6',
      order_id: 'SIM-0041', node_id: 'SUP-01', group_id: 'G-P6-W6', status: 'WAIT',
      contents: [{ part_no: 'PN-B-1180', qty: 1 }] },

    // 치수검사 대기 부품 (경화 끝난 것)
    { unit_id: 'p-11', unit_kind: 'PART', display_id: 'P5-W5-S21-C88', parent_display_id: 'P5-W5',
      order_id: 'SIM-0040', node_id: 'INS-01', group_id: 'G-P5-W5', status: 'WAIT',
      contents: [{ part_no: 'PN-A-2026', qty: 1 }] },
    { unit_id: 'p-12', unit_kind: 'PART', display_id: 'P5-W5-S22-C89', parent_display_id: 'P5-W5',
      order_id: 'SIM-0040', node_id: 'INS-01', group_id: 'G-P5-W5', status: 'WAIT',
      contents: [{ part_no: 'PN-A-2026', qty: 1 }] },
    { unit_id: 'p-13', unit_kind: 'PART', display_id: 'P5-W5-S23-C90', parent_display_id: 'P5-W5',
      order_id: 'SIM-0040', node_id: 'INS-01', group_id: 'G-P5-W5', status: 'WAIT',
      contents: [{ part_no: 'PN-C-770', qty: 1 }] }
  ],

  id_counter: { S: 41, D: 88 },
  group_seq: 41,        // 묶음 채번. 배치 이름이 아니라 일련번호 — 여러 배치가 한 묶음에 섞이므로
  box: {},        // 랙마다 담는 중인 박스 — { 랙 id: { group_id, items } }
  boxes: [],      // 마감돼 랙에 올라간 박스
  box_seq: 41,

  interlock: {
    'SEP-01': [{ key: 'dust', label: '집진 가동 중', ok: true },
               { key: 'login', label: '작업자 로그인 확인', ok: true }],
    'SUP-01': [{ key: 'dust', label: '집진 가동 중', ok: true },
               { key: 'login', label: '작업자 로그인 확인', ok: true }],
    'INS-01': [{ key: 'origin', label: '스캐너 원점 정상', ok: true },
               { key: 'calib', label: '기준물 캘리브레이션 24h 이내', ok: true }]
  },

  log: [
    { ts: '10:22', actor: '담당자', kind: 'JUDGE', text: 'P6-W6 분리 완료 (OK 3)' },
    { ts: '10:05', actor: '시스템', kind: 'MOVED', text: 'P7-W7 세척기 완료 랙 1 · 칸 1 도착' }
  ],

  NG_REASONS: ['서포트 자국', '표면 결손', '파손', '기타'],
  judgement: [],
};

// ══ 대기 큐 예시 — 앞 공정에서 마감돼 랙에 올라가 있는 박스들 ══════
//   한 박스에 파트넘버가 섞여 있는 것이 기본이다 (앞 배치들이 함께 담긴다).
const BOX_SEED: [string, string, string, [string, number][]][] = [
  ['BOX-0038', 'RK-CUR-WAIT-01', 'P5-W5', [['PN-A-2026', 7], ['PN-B-1180', 5]]],
  ['BOX-0039', 'RK-CUR-WAIT-01', 'P6-W6', [['PN-C-770', 6], ['PN-A-2026', 3]]],
  ['BOX-0040', 'RK-BPD-WAIT-01', 'P3-W3', [['PN-A-2026', 8], ['PN-C-770', 4]]],
  ['BOX-0041', 'RK-BPD-WAIT-01', 'P4-W4', [['PN-B-1180', 7]]],
];

BOX_SEED.forEach(([id, rack, src, mix]) => {
  const items: MockBoxItem[] = [];
  let no = 0;
  mix.forEach(([pn, qty]) => {
    for (let i = 0; i < qty; i++) {
      no += 1;
      items.push({ unit_id: `${id.toLowerCase()}-${no}`, display_id: `${src}-S${no}`, part_no: pn });
    }
  });
  MOCK.boxes.push({ group_id: id, node_id: rack, items });
});

// ══ 로직 — 서버(뷰)가 할 계산 ═══════════════════════════════
//   이름은 대응하는 뷰를 주석에 적어 둔다. 실 API 로 가면 전부 서버가 한다.

export function node(m: MockState, id: string): MockNode | null {
  return m.nodes.find((n) => n.node_id === id) ?? null;
}

/** v_node_order — MAIN 엣지만 따라간 공정 순서. */
export function stepOrder(m: MockState): Record<string, number> {
  const main = m.routes.filter((r) => r.kind === 'MAIN');
  const order: Record<string, number> = {};
  m.nodes.filter((n) => !main.some((r) => r.to === n.node_id))
    .forEach((n) => { order[n.node_id] = 0; });
  for (let i = 0; i < 50; i++) {            // 깊이 상한 = 스키마와 같다
    let moved = false;
    main.forEach((r) => {
      if (order[r.from] == null) return;
      const d = order[r.from] + 1;
      if (order[r.to] == null || order[r.to] < d) { order[r.to] = d; moved = true; }
    });
    if (!moved) break;
  }
  return order;
}

export interface MenuRow {
  menu_label: string;
  ui_kind: UiKind;
  step_order: number;
  node_count: number;
  node_ids: string[];
}

/** v_control_menu — group_label 로 묶고 step_order 순. 서브 메뉴의 유일한 출처. */
export function menu(m: MockState): MenuRow[] {
  const ord = stepOrder(m);
  const by = new Map<string, MenuRow>();
  m.nodes.filter((n) => n.node_kind === 'STATION').forEach((n) => {
    // menu_group 이 있으면 여러 공정이 한 탭으로 묶인다 (출력 · 세척)
    const label = n.menu_group ?? n.group_label ?? n.label;
    const ui = n.ui_kind ?? 'MONITOR';
    const key = `${label} ${ui}`;
    const step = ord[n.node_id] ?? 99;
    let e = by.get(key);
    if (!e) { e = { menu_label: label, ui_kind: ui, step_order: step, node_count: 0, node_ids: [] }; by.set(key, e); }
    e.node_count += 1;
    e.node_ids.push(n.node_id);
    e.step_order = Math.min(e.step_order, step);
  });
  const rows = Array.from(by.values());
  rows.forEach((r) => r.node_ids.sort());
  rows.sort((a, b) => a.step_order - b.step_order || a.menu_label.localeCompare(b.menu_label));
  return rows;
}

export function prevMain(m: MockState, nodeId: string): string[] {
  return m.routes.filter((r) => r.kind === 'MAIN' && r.to === nodeId).map((r) => r.from);
}

export function nextMain(m: MockState, nodeId: string): string[] {
  return m.routes.filter((r) => r.kind === 'MAIN' && r.from === nodeId).map((r) => r.to);
}

export function at(m: MockState, nodeId: string): MockUnit[] {
  return m.units.filter((u) => u.node_id === nodeId);
}

export function qtyOf(u: MockUnit): number {
  return u.contents.reduce((a, c) => a + c.qty, 0);
}

/** v_unit_summary.part_label — 한 종이면 파트넘버, 여러 종이면 '혼재 N종'. */
export function partLabel(u: MockUnit): string | null {
  if (u.contents.length === 0) return null;
  return u.contents.length === 1 ? u.contents[0].part_no : `혼재 ${u.contents.length}종`;
}

export interface SlotView {
  slot_no: number;
  capacity: number;
  used: number;
  contents: string[];
}

/** v_rack_slot — 빈 칸도 돌려준다. */
export function slotsOf(m: MockState, rackId: string): SlotView[] {
  const rack = node(m, rackId);
  if (!rack?.slots) return [];
  return rack.slots.map((s) => {
    const inSlot = at(m, rackId).filter((u) => u.slot_no === s.slot_no);
    return {
      slot_no: s.slot_no,
      capacity: s.capacity,
      used: inSlot.length,
      // 배치명만으로는 안에 뭐가 들었는지 모른다 — 종수를 함께 준다
      contents: inSlot.slice().sort((a, b) => (a.pos_no ?? 0) - (b.pos_no ?? 0))
        .map((u) => `${u.display_id} (${u.contents.length}종)`),
    };
  });
}

/** v_rack_load */
export function rackLoad(m: MockState, rackId: string): { used: number; capacity: number; slots: number } {
  const s = slotsOf(m, rackId);
  return {
    used: s.reduce((a, x) => a + x.used, 0),
    capacity: s.reduce((a, x) => a + x.capacity, 0),
    slots: s.length,
  };
}

/** 더 받을 수 있는가. 🚨 "비어 있는가" 가 아니다 — 작업대는 정원 16이라 이미 뭔가 있어도 받는다. */
export function isFree(m: MockState, n: MockNode): boolean {
  return occupancy(m, n) < (n.capacity ?? 1);
}

export function occupancy(m: MockState, n: MockNode): number {
  return at(m, n.node_id).reduce((a, u) => a + (u.unit_kind === 'PART' ? 1 : qtyOf(u)), 0);
}

export interface GroupView {
  group_id: string;
  units: MockUnit[];
}

/** 묶음 — 부품 구간의 재공 단위. */
export function groups(m: MockState, nodeId: string): GroupView[] {
  const g = new Map<string, GroupView>();
  at(m, nodeId).filter((u) => u.unit_kind === 'PART' && u.group_id).forEach((u) => {
    const id = u.group_id as string;
    let e = g.get(id);
    if (!e) { e = { group_id: id, units: [] }; g.set(id, e); }
    e.units.push(u);
  });
  return Array.from(g.values());
}

/**
 * v_inbound_queue — 이 설비에 들어올 차례를 기다리는 것들.
 *   직전이 랙    = 적재분 + 그 랙에 올라간 박스
 *   직전이 작업대 = 아직 안 넘긴 묶음
 */
export function inbound(m: MockState, nodeId: string): InboundRow[] {
  const rows: InboundRow[] = [];
  prevMain(m, nodeId).forEach((id) => {
    const n = node(m, id);
    if (!n) return;
    const push = (kind: InboundRow['kind'], ref: string, label: string, qty: number) =>
      rows.push({ key: `${kind}:${ref}`, kind, ref, label, qty, from: n.label, from_node: id, ready: false });
    if (n.node_kind === 'RACK') {
      m.boxes.filter((b) => b.node_id === id).forEach((b) => push('BOX', b.group_id, b.group_id, b.items.length));
      at(m, id).slice()
        .sort((a, b) => ((a.slot_no ?? 0) - (b.slot_no ?? 0)) || ((a.pos_no ?? 0) - (b.pos_no ?? 0)))
        .forEach((u) => push('UNIT', u.unit_id, u.display_id, qtyOf(u)));
    } else {
      groups(m, id).forEach((g) => push('GROUP', g.group_id, g.group_id, g.units.length));
    }
  });
  // FIFO — 출처마다 맨 앞 것만 지금 넣을 수 있다
  const seen: Record<string, true> = {};
  rows.forEach((r) => { if (!seen[r.from_node]) { seen[r.from_node] = true; r.ready = true; } });
  return rows;
}

/** 이 설비가 얼마나 돌기로 되어 있나 — 시작할 때 정한 값이 있으면 그것, 없으면 표준. */
export function runTotal(m: MockState, n: MockNode): number {
  const u = at(m, n.node_id)[0];
  return u?.plan_s || n.std_cycle_s || 0;
}

export function progress(m: MockState, n: MockNode): number | null {
  const u = at(m, n.node_id)[0];
  const total = runTotal(m, n);
  if (!u || !total || u.elapsed_s == null) return null;
  return Math.min(100, Math.round((100 * u.elapsed_s) / total));
}

// ══ 반송 자원 — topology.yaml transporters 를 그대로 옮긴 것 ══════
// 🚨 담당 구간·명령 카탈로그는 화면이 지어내지 않는다. 늘리려면 여기(=topology.yaml)만 고친다.

export interface MockSend {
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

export interface MockCommand {
  id: string;
  group: string;
  label: string;
  hint?: string;
  span_mm?: number;
  send: MockSend;
  source: string;
  /** false 면 화면이 실행을 잠그고 값만 보여준다. W6 도 거부한다 */
  verified: boolean;
  risk: string;
}

export interface MockTransporter {
  id: string;
  kind: 'ROBOT_ARM' | 'OPERATOR' | 'CONVEYOR';
  label: string;
  nodes: string[];
  /** 없으면 수동 반송 — 보낼 명령이 없다 */
  endpoint: { protocol: string; ref: string } | null;
  commands: MockCommand[];
}

const DO = (ch: string, bits: number[], pulse_s?: number): MockSend => ({ kind: 'DO', ch, bits, pulse_s });
const MB = (reg: number, value: number, then?: { reg: number; value: number }): MockSend =>
  ({ kind: 'MODBUS', reg, value, then });
const SOCK = (port: number, msg: string): MockSend => ({ kind: 'SOCKET', port, msg });

export const TRANSPORTERS: MockTransporter[] = [
  {
    id: 'ARM-A', kind: 'ROBOT_ARM', label: '로봇암 A',
    nodes: ['RK-PRE-PRT-01', 'PRT-01', 'PRT-02', 'PRT-03', 'PRT-04', 'RK-PRT-DONE-01', 'WSH-01', 'WSH-02'],
    endpoint: { protocol: 'modbus', ref: 'arm-a' },
    commands: [
      { id: 'mv-prt', group: '이송 핸드셰이크', label: '프린터 이송', hint: '명령값 1',
        send: MB(130, 1, { reg: 150, value: 1 }), source: 'config.py ROBOT_MODBUS_CMD_FW_VALUE',
        verified: true, risk: '로봇이 프린터로 이동' },
      { id: 'mv-wash', group: '이송 핸드셰이크', label: '세척기 이송', hint: '명령값 2',
        send: MB(130, 2, { reg: 150, value: 1 }), source: 'config.py ROBOT_MODBUS_CMD_FW_VALUE',
        verified: true, risk: '로봇이 세척기로 이동' },
      { id: 'mv-back', group: '이송 핸드셰이크', label: '복귀', hint: '명령값 0',
        send: MB(130, 0, { reg: 150, value: 1 }), source: 'config.py ROBOT_MODBUS_CMD_FW_VALUE',
        verified: true, risk: '로봇이 대기 자세로' },
      { id: 'pc-ready', group: '이송 핸드셰이크', label: 'PC Ready 세우기', hint: '레지스터 151',
        send: MB(151, 1), source: 'config.py ROBOT_MODBUS_PC_READY',
        verified: true, risk: '로봇이 다음 단계로 넘어간다' },
    ],
  },
  {
    id: 'OP-CURE', kind: 'OPERATOR', label: '경화 구간 수동 반송',
    nodes: ['RK-WSH-DONE-01', 'SEP-01', 'SUP-01', 'RK-CUR-WAIT-01', 'CUR-01', 'CUR-02', 'INS-01', 'RK-BPD-WAIT-01'],
    endpoint: null,
    commands: [],
  },
  {
    id: 'ARM-B', kind: 'ROBOT_ARM', label: '로봇암 B',
    nodes: ['BPD-01'],
    endpoint: { protocol: 'modbus', ref: 'arm-b' },
    commands: [
      // 🚨 그리퍼는 상태 하나에 신호 하나다. "열어라/닫아라" 가 아니라 갈 상태를 고른다.
      { id: 'grip-open-1', group: '그리퍼 상태', label: '열기 1단계', span_mm: 40,
        send: DO('D_GEN_OUT_0~3', [1, 0, 0, 0], 0.5),
        source: 'rodi_pick_sequence.js GRIP_COMBO[0] · 폭은 임의값(9/9 에 45mm 부품을 못 물었다)',
        verified: false, risk: '그리퍼가 이 상태로 간다' },
      { id: 'grip-open-2', group: '그리퍼 상태', label: '열기 2단계', span_mm: 84,
        send: DO('D_GEN_OUT_0~3', [0, 1, 0, 0], 0.5),
        source: 'rodi_pick_sequence.js GRIP_COMBO[1] · 9/9 실물 확인',
        verified: true, risk: '그리퍼가 이 상태로 간다' },
      { id: 'grip-open-3', group: '그리퍼 상태', label: '열기 3단계', span_mm: 60,
        send: DO('D_GEN_OUT_0~3', [1, 1, 0, 0], 0.5),
        source: 'rodi_pick_sequence.js GRIP_COMBO[2] · 폭은 임의값',
        verified: false, risk: '그리퍼가 이 상태로 간다' },
      { id: 'grip-open-4', group: '그리퍼 상태', label: '열기 4단계', span_mm: 20,
        send: DO('D_GEN_OUT_0~3', [1, 1, 1, 0], 0.5),
        source: 'rodi_pick_sequence.js GRIP_COMBO[3] · 폭은 임의값',
        verified: false, risk: '그리퍼가 이 상태로 간다' },
      { id: 'bp-capture', group: '빈피킹', label: '촬영 자세로', hint: 'PICK_CAPTURE_POSE',
        send: SOCK(5000, 'CAPTURE'),
        source: 'pick_socket_server.py · 자세값은 10월 재배치 후 재티칭',
        verified: false, risk: '팔이 촬영 자세로 이동' },
      { id: 'bp-pick', group: '빈피킹', label: '인식 좌표로 집기', hint: '6요소 좌표 송신',
        send: SOCK(5000, 'PICK'),
        source: 'pick_socket_server.py · hand-eye 값 미확정',
        verified: false, risk: '팔이 빈으로 내려가 집는다' },
      // 🔴 스핀들은 rodi_pick_sequence.js 가 SPINDLE_API='none' 으로 두고 있다.
      { id: 'spindle-on', group: '스핀들', label: '스핀들 ON', hint: 'D_CONF_OUT_2',
        send: DO('D_CONF_OUT_2', [1]),
        source: "rodi_pick_sequence.js SPINDLE_API='none' — 함수명 미확인",
        verified: false, risk: '드릴이 돈다' },
    ],
  },
];

/** 이 노드를 담당하는 반송 자원. topology 의 nodes 목록이 정본이다. */
export function transporterOf(m: MockState, n: MockNode): string | null {
  void m;
  return TRANSPORTERS.find((t) => t.nodes.includes(n.node_id))?.id ?? null;
}

export function transporterById(id: string): MockTransporter | null {
  return TRANSPORTERS.find((t) => t.id === id) ?? null;
}

// ══ 조작 — 서버(상태 엔진)가 할 일 ═══════════════════════════
//   실 API 에서는 이벤트 Moved · State 가 하는 일이다.

/** 랙에서 하나를 빼면 뒤엣것이 한 칸 당겨진다 (FIFO 라 번호가 밀린다). */
function pullFromRack(m: MockState, u: MockUnit): void {
  if (u.slot_no == null) return;
  const from = { node_id: u.node_id, slot_no: u.slot_no, pos_no: u.pos_no ?? 0 };
  m.units.forEach((x) => {
    if (x !== u && x.node_id === from.node_id && x.slot_no === from.slot_no && (x.pos_no ?? 0) > from.pos_no) {
      x.pos_no = (x.pos_no ?? 0) - 1;
    }
  });
  u.slot_no = null;
  u.pos_no = null;
}

/** 묶음째 이동 — 부품 N건이 아니라 Moved 1건. */
export function moveGroup(m: MockState, groupId: string, fromNode: string, toNode: string): number {
  const moved = m.units.filter((u) => u.group_id === groupId && u.node_id === fromNode);
  moved.forEach((u) => { u.node_id = toNode; u.status = 'WAIT'; });
  return moved.length;
}

/** 대기 큐에서 골라 설비에 넣는다. 차 있으면 못 넣는다(409). */
export function loadInto(m: MockState, nodeId: string, key: string): { count: number; label: string } | null {
  const dest = node(m, nodeId);
  if (!dest || !isFree(m, dest)) return null;
  const row = inbound(m, nodeId).find((r) => r.key === key);
  if (!row?.ready) return null;

  let count = 0;
  if (row.kind === 'GROUP') {
    count = moveGroup(m, row.ref, row.from_node, nodeId);
  } else if (row.kind === 'UNIT') {
    const u = m.units.find((x) => x.unit_id === row.ref);
    if (!u) return null;
    pullFromRack(m, u);
    u.node_id = nodeId;
    u.status = 'WAIT';
    u.elapsed_s = 0;
    u.plan_s = null;
    count = qtyOf(u);
  } else {
    // BOX — 담겨 있던 부품이 설비로 들어간다
    const bi = m.boxes.findIndex((b) => b.group_id === row.ref);
    if (bi < 0) return null;
    const box = m.boxes[bi];
    box.items.forEach((it) => m.units.push({
      unit_id: it.unit_id, unit_kind: 'PART', display_id: it.display_id,
      order_id: it.order_id, node_id: nodeId, group_id: box.group_id,
      status: 'WAIT', elapsed_s: 0, contents: [{ part_no: it.part_no, qty: 1 }],
    }));
    count = box.items.length;
    m.boxes.splice(bi, 1);
  }
  return { count, label: row.label };
}

/**
 * 설비 명령 — 시작 · 중지 · 완료.
 * 실린 것이 없으면 아무 명령도 못 준다 (빈 설비를 돌릴 수는 없다).
 */
export const CMD: { key: string; label: string; to: UnitStatus }[] = [
  { key: 'start', label: '시작', to: 'RUN' },
  { key: 'stop', label: '중지', to: 'HOLD' },
  { key: 'done', label: '완료', to: 'DONE' },
];

export function cmdOf(key: string) {
  return CMD.find((c) => c.key === key) ?? null;
}

/** 시작할 때 가동 시간을 받는 설비인가. 노드가 정한다 — 공정 타입으로 분기하지 않는다. */
export function durationSpec(m: MockState, nodeId: string): { label: string; unit: string; default: number } | null {
  const n = node(m, nodeId);
  if (!n?.duration_input) return null;
  return { label: '가동 시간', unit: '분', default: Math.max(1, Math.round((n.std_cycle_s ?? 0) / 60)) };
}

export function canCmd(m: MockState, nodeId: string, key: string): boolean {
  const u = at(m, nodeId)[0];
  if (!u) return false;
  if (key === 'start') return u.status !== 'RUN';
  if (key === 'stop') return u.status === 'RUN';
  if (key === 'done') return u.status === 'RUN' || u.status === 'HOLD';
  return false;
}

export function runCmd(m: MockState, nodeId: string, key: string, minutes: number | null):
  { from: UnitStatus; to: UnitStatus; plan_s: number | null } | null {
  if (!canCmd(m, nodeId, key)) return null;
  const here = at(m, nodeId);
  const c = cmdOf(key);
  if (!c) return null;
  const from = here[0].status;
  let plan_s: number | null = null;
  if (key === 'start' && durationSpec(m, nodeId)) {
    const min = Math.round(Number(minutes));
    if (!(min > 0)) return null;             // 시간을 안 정하면 돌리지 않는다
    plan_s = min * 60;
  }
  here.forEach((x) => {
    x.status = c.to;
    if (key === 'start') {
      if (plan_s) x.plan_s = plan_s;
      if (x.elapsed_s == null) x.elapsed_s = 0;
    }
  });
  return { from, to: c.to, plan_s };
}

/** 혼재 내역 — 'PN-A-2026 x8, PN-B-1180 x4' */
export function mixOf(u: MockUnit): string {
  return u.contents.map((c) => `${c.part_no} x${c.qty}`).join(', ');
}

export function interlockOf(m: MockState, nodeId: string): MockInterlock[] {
  return m.interlock[nodeId] ?? [];
}

export function interlockOk(m: MockState, nodeId: string): boolean {
  return interlockOf(m, nodeId).every((i) => i.ok);
}

/** 명령 로그 — 🔴 읽는 엔드포인트가 명세에 없다(R12 부재). 지금은 세션 로그다. */
export function pushLog(m: MockState, kind: string, text: string, actor: string): void {
  const d = new Date();
  m.log.unshift({
    ts: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
    actor, kind, text,
  });
  m.log = m.log.slice(0, 8);
}

// ══ 분리(BATCH_SPLIT) · 판정(PART_JUDGE) ════════════════════

export function prevRacks(m: MockState, nodeId: string): MockNode[] {
  return prevMain(m, nodeId).map((id) => node(m, id)).filter((n): n is MockNode => n?.node_kind === 'RACK');
}

export function nextNodes(m: MockState, nodeId: string): MockNode[] {
  return nextMain(m, nodeId).map((id) => node(m, id)).filter((n): n is MockNode => n != null);
}

/** 묶음 정원 — 경화기면 설비 용량, 트레이 랙이면 트레이 정원. */
export function groupCapacity(dest: MockNode | null): number {
  if (!dest) return 0;
  return dest.group_capacity ?? dest.capacity ?? 0;
}

/** v_retrievable — 랙의 slot_access 규칙으로 지금 꺼낼 수 있는 것만 표시. */
export function queueOf(m: MockState, rackId: string, slotNo: number): (MockUnit & { retrievable: boolean })[] {
  const rack = node(m, rackId);
  const access = rack?.slot_access ?? 'FIFO';
  const rows = at(m, rackId).filter((u) => u.slot_no === slotNo)
    .slice().sort((a, b) => (a.pos_no ?? 0) - (b.pos_no ?? 0));
  if (!rows.length) return [];
  const pos = rows.map((r) => r.pos_no ?? 0);
  const pick = access === 'FIFO' ? Math.min(...pos) : access === 'LIFO' ? Math.max(...pos) : null;
  return rows.map((u) => ({ ...u, retrievable: access === 'RANDOM' ? true : u.pos_no === pick }));
}

export interface JudgeRow {
  part_no: string;
  name: string;
  qty: number;
  ok: number;
  ng: number;
  reason: string;
}

export type JudgeInput = Record<string, { ok?: number; ng?: number; reason?: string }>;

/** 파트넘버별 판정 행. 부품 ID 를 만들지 않는다 — 아직 존재하지 않는다. */
export function judgeRows(m: MockState, batch: MockUnit, saved: JudgeInput = {}): JudgeRow[] {
  return batch.contents.map((c) => {
    const s = saved[c.part_no] ?? {};
    const p = m.part[c.part_no];
    const ng = s.ng ?? 0;
    return {
      part_no: c.part_no,
      name: p?.name ?? c.part_no,
      qty: c.qty,
      ok: s.ok ?? c.qty - ng,
      ng,
      reason: s.reason ?? '',
    };
  });
}

export function totals(rows: JudgeRow[]): { qty: number; ok: number; ng: number } {
  return rows.reduce((a, r) => ({ qty: a.qty + r.qty, ok: a.ok + r.ok, ng: a.ng + r.ng }), { qty: 0, ok: 0, ng: 0 });
}

/** 🔴 검증은 파트별로 각각. 합계가 맞아도 파트별이 어긋나면 안 된다. */
export function rowValid(r: JudgeRow): boolean {
  return r.ok + r.ng === r.qty && (r.ng ? !!r.reason : true);
}

export function badRows(rows: JudgeRow[]): JudgeRow[] {
  return rows.filter((r) => !rowValid(r));
}

/** 일괄 OK 대상 = 아직 손대지 않은 파트. 이미 입력한 줄은 건드리지 않는다. */
export function untouched(rows: JudgeRow[], saved: JudgeInput = {}): { kinds: number; qty: number; parts: JudgeRow[] } {
  const list = rows.filter((r) => saved[r.part_no] == null);
  return { kinds: list.length, qty: list.reduce((a, r) => a + r.qty, 0), parts: list };
}

export function canComplete(rows: JudgeRow[], interlock: boolean): boolean {
  return rows.length > 0 && interlock && rows.every(rowValid);
}

function nextGroupId(m: MockState): string {
  m.group_seq += 1;
  return `G-${String(m.group_seq).padStart(4, '0')}`;
}

/**
 * Split — 배치가 개별 부품으로 분해된다. outputs 에는 OK 수량만.
 * NG 는 part_scrap 으로 기록되고 unit 이 생기지 않는다.
 */
export function splitBatch(m: MockState, batch: MockUnit, rows: JudgeRow[], nodeId: string, groupId: string | null):
  { ok: number; ng: number; group_id: string } {
  const n = node(m, nodeId);
  const prefix = n?.id_prefix ?? 'S';
  const group_id = groupId ?? nextGroupId(m);
  const born: MockUnit[] = [];
  rows.forEach((r) => {
    for (let i = 0; i < r.ok; i++) {
      m.id_counter[prefix] = (m.id_counter[prefix] ?? 1) + 1;
      born.push({
        unit_id: `${batch.unit_id}-${prefix}${m.id_counter[prefix]}`,
        unit_kind: 'PART',
        display_id: `${batch.display_id}-${prefix}${m.id_counter[prefix]}`,
        parent_display_id: batch.display_id,
        order_id: batch.order_id,
        node_id: nodeId,
        group_id,
        status: 'WAIT',
        contents: [{ part_no: r.part_no, qty: 1 }],
      });
    }
  });

  // 배치는 소비된다. 랙의 뒤 배치를 한 칸 당긴다 (FIFO 라 2번이 1번이 된다).
  const from = { node_id: batch.node_id, slot_no: batch.slot_no, pos_no: batch.pos_no ?? 0 };
  m.units = m.units.filter((u) => u.unit_id !== batch.unit_id);
  m.units.forEach((u) => {
    if (u.node_id === from.node_id && u.slot_no === from.slot_no && (u.pos_no ?? 0) > from.pos_no) {
      u.pos_no = (u.pos_no ?? 0) - 1;
    }
  });
  born.forEach((b) => m.units.push(b));
  const t = totals(rows);
  return { ok: t.ok, ng: t.ng, group_id };
}

export interface GroupSource {
  parent_display_id: string;
  parts: Record<string, number>;
  qty: number;
}

/** 묶음 안을 출처 배치별로 쪼갠다 — 여러 배치가 섞이므로 어디서 왔는지 보여야 한다. */
export function groupSources(m: MockState, nodeId: string, groupId: string): GroupSource[] {
  const by = new Map<string, GroupSource>();
  at(m, nodeId).filter((u) => u.group_id === groupId).forEach((u) => {
    const src = u.parent_display_id ?? '?';
    let e = by.get(src);
    if (!e) { e = { parent_display_id: src, parts: {}, qty: 0 }; by.set(src, e); }
    const pn = u.contents[0].part_no;
    e.parts[pn] = (e.parts[pn] ?? 0) + 1;
    e.qty += 1;
  });
  return Array.from(by.values());
}

export function groupCount(m: MockState, nodeId: string, groupId: string): number {
  return at(m, nodeId).filter((u) => u.group_id === groupId).length;
}

/**
 * 묶음 정원 — 이 묶음이 통째로 들어갈 설비의 정원.
 * 분리대에서 만든 묶음은 서포트제거를 거쳐 경화기로 가므로 두 홉을 본다.
 * ponytail: "묶음이 어디서 깨지는가" 가 스키마에 없어 capacity>1 로 근사한다
 *           (치수검사는 부품 하나씩이라 capacity=1 로 걸러진다).
 *           node 에 group_breaks 플래그가 생기면 그것으로 바꾼다.
 */
export function groupTarget(m: MockState, nodeId: string): number {
  const seen: Record<string, true> = {};
  let front = [nodeId];
  let best: number | null = null;
  for (let hop = 0; hop < 2; hop++) {
    const nxt: string[] = [];
    front.forEach((id) => nextMain(m, id).forEach((t) => { if (!seen[t]) { seen[t] = true; nxt.push(t); } }));
    nxt.forEach((id) => {
      const nd = node(m, id);
      if (nd && (nd.node_kind === 'STATION' || nd.count_by_group)) {
        const c = groupCapacity(nd);
        if (c > 1) best = best == null ? c : Math.min(best, c);
      }
    });
    front = nxt;
  }
  return best ?? 0;
}

export interface PartRow {
  unit_id: string;
  display_id: string;
  group_id: string | null;
  part_no: string;
  part_name: string;
  attrs: MockPart['attrs'];
}

/** 대기 부품. 파트넘버로 정렬 — 같은 모양끼리 붙어 있어야 손이 덜 간다. */
export function waitingParts(m: MockState, nodeId: string): PartRow[] {
  return at(m, nodeId).filter((u) => u.unit_kind === 'PART')
    .map((u) => {
      const pn = u.contents[0]?.part_no ?? '';
      return {
        unit_id: u.unit_id,
        display_id: u.display_id,
        group_id: u.group_id ?? null,
        part_no: pn,
        part_name: m.part[pn]?.name ?? pn,
        attrs: m.part[pn]?.attrs ?? {},
      };
    })
    .sort((a, b) => a.part_no.localeCompare(b.part_no) || a.display_id.localeCompare(b.display_id));
}

/** 측정 스펙이 노드에 있으면 입력란을 띄운다. ui_kind 는 그대로 PART_JUDGE. */
export function measureSpec(m: MockState, nodeId: string): MockMeasureSpec | null {
  return node(m, nodeId)?.measure ?? null;
}

export function inTolerance(v: number | null, attrs: MockPart['attrs']): boolean | null {
  if (v == null || attrs?.nominal_mm == null) return null;
  return Math.abs(v - attrs.nominal_mm) <= (attrs.tol_mm ?? Infinity);
}

export function latestVerdict(m: MockState, unitId: string): MockJudgement | null {
  for (let i = m.judgement.length - 1; i >= 0; i--) if (m.judgement[i].unit_id === unitId) return m.judgement[i];
  return null;
}

/** 판정 기록 — append only. 사람이 뒤집으면 새 행이 쌓인다. */
export function judge(m: MockState, unitId: string, nodeId: string, verdict: string, value: string | null): MockJudgement {
  const rec: MockJudgement = { ts: Date.now(), unit_id: unitId, node_id: nodeId, verdict, value, note: null, source: 'MANUAL' };
  m.judgement.push(rec);
  return rec;
}

/** NG 부품은 라인을 떠난다. */
export function scrapPart(m: MockState, unitId: string): boolean {
  const before = m.units.length;
  m.units = m.units.filter((x) => x.unit_id !== unitId);
  return m.units.length < before;
}

/** 이 랙에 담는 중인 박스. 없으면 새로 딴다 — 랙마다 따로다. */
export function openBox(m: MockState, rackId: string): { group_id: string; items: MockBoxItem[] } {
  if (!m.box[rackId]) {
    m.box_seq += 1;
    m.box[rackId] = { group_id: `BOX-${String(m.box_seq).padStart(4, '0')}`, items: [] };
  }
  return m.box[rackId];
}

/** 박스 합류 — 부품 하나씩 join_group 으로 붙는다. */
export function joinBox(m: MockState, unitId: string, rackId: string): string | null {
  const u = m.units.find((x) => x.unit_id === unitId);
  if (!u) return null;
  const box = openBox(m, rackId);
  m.units = m.units.filter((x) => x.unit_id !== unitId);
  box.items.push({ unit_id: unitId, display_id: u.display_id, part_no: u.contents[0].part_no });
  return box.group_id;
}

export function closeBox(m: MockState, rackId: string): { group_id: string; items: MockBoxItem[] } | null {
  const done = m.box[rackId];
  if (!done?.items.length) return null;
  // 마감한 박스는 랙에 올라간다 — 안 그러면 어디에도 안 남고 다음 공정이 못 본다
  m.boxes.push({ group_id: done.group_id, items: done.items, node_id: rackId });
  delete m.box[rackId];               // 다음 것은 담을 때 새로 열린다
  return done;
}

/** 이 노드의 OK 부품이 담길 박스 랙. 없으면 null. */
export function boxRackOf(m: MockState, nodeId: string): MockNode | null {
  return nextNodes(m, nodeId).find((n) => n.node_kind === 'RACK' && n.count_by_group) ?? null;
}

/** NG 사유 목록 — 🔴 조회 엔드포인트가 명세에 없다(노드 속성으로 와야 할 값). */
export function NG_REASONS_OF(m: MockState): string[] {
  return m.NG_REASONS;
}
