/* ══════════════════════════════════════════════════════════════
   제어 화면 — 목업 + 순수 로직 (DOM 을 만지지 않는다)
   다음 단계에서 MOCK 만 API 응답으로 갈아끼우면 화면 코드는 그대로다.
   ══════════════════════════════════════════════════════════════ */
(function (root) {

  // ══ 목업 — topology.yaml 과 같은 모양. 설비를 늘리려면 여기에만 줄을 더한다 ══
  const MOCK = {
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
      { node_id: 'RK-BPD-WAIT-01', node_kind: 'RACK', node_type: 'BUFFER', label: '빔피킹 대기 랙 1',
        slot_access: 'FIFO', count_by_group: true, group_capacity: 12,   // 트레이 1개에 부품 12
        slots: [{ slot_no: 1, capacity: 4 }, { slot_no: 2, capacity: 4 }] },

      // 설비 — group_label 이 서브 메뉴 이름, ui_kind 가 화면 종류
      { node_id: 'PRT-01', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
        group_label: '프린터', menu_group: '출력 · 세척', label: '프린터 1호기', capacity: 1, std_cycle_s: 5400 },
      { node_id: 'PRT-02', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
        group_label: '프린터', menu_group: '출력 · 세척', label: '프린터 2호기', capacity: 1, std_cycle_s: 5400 },
      { node_id: 'PRT-03', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
        group_label: '프린터', menu_group: '출력 · 세척', label: '프린터 3호기', capacity: 1, std_cycle_s: 5400 },
      { node_id: 'PRT-04', node_kind: 'STATION', node_type: 'PRINTER', ui_kind: 'MONITOR',
        group_label: '프린터', menu_group: '출력 · 세척', label: '프린터 4호기', capacity: 1, std_cycle_s: 5400 },

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
        group_label: '빔피킹·드릴링·트림', label: '빔피킹/드릴링/트림', capacity: 1, std_cycle_s: 900 }
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

    NG_REASONS: ['서포트 자국', '표면 결손', '파손', '기타']
  };

  // ══ 로직 ══════════════════════════════════════════════════
  const L = {
    node(m, id) { return m.nodes.find(n => n.node_id === id) || null; },

    /** v_node_order — MAIN 엣지만 따라간 공정 순서. */
    stepOrder(m) {
      const main = m.routes.filter(r => r.kind === 'MAIN');
      const order = {};
      const roots = m.nodes.filter(n => !main.some(r => r.to === n.node_id)).map(n => n.node_id);
      roots.forEach(id => { order[id] = 0; });
      for (let i = 0; i < 50; i++) {           // 깊이 상한 = 스키마와 같다
        let moved = false;
        main.forEach(r => {
          if (order[r.from] == null) return;
          const d = order[r.from] + 1;
          if (order[r.to] == null || order[r.to] < d) { order[r.to] = d; moved = true; }
        });
        if (!moved) break;
      }
      return order;
    },

    /** v_control_menu — group_label 로 묶고 step_order 순. 서브 메뉴의 유일한 출처. */
    menu(m) {
      const ord = L.stepOrder(m);
      const by = new Map();
      m.nodes.filter(n => n.node_kind === 'STATION').forEach(n => {
        // menu_group 이 있으면 여러 공정이 한 탭으로 묶인다 (출력 · 세척)
        const label = n.menu_group || n.group_label || n.label;
        const key = label + ' ' + n.ui_kind;
        if (!by.has(key)) by.set(key, {
          menu_label: label, ui_kind: n.ui_kind,
          step_order: ord[n.node_id] == null ? 99 : ord[n.node_id],
          node_count: 0, node_ids: []
        });
        const e = by.get(key);
        e.node_count += 1; e.node_ids.push(n.node_id);
        e.step_order = Math.min(e.step_order, ord[n.node_id] == null ? 99 : ord[n.node_id]);
      });
      const rows = Array.from(by.values());
      rows.forEach(r => r.node_ids.sort());
      rows.sort((a, b) => a.step_order - b.step_order || a.menu_label.localeCompare(b.menu_label));
      return rows;
    },


    prevMain(m, nodeId) { return m.routes.filter(r => r.kind === 'MAIN' && r.to === nodeId).map(r => r.from); },
    nextMain(m, nodeId) { return m.routes.filter(r => r.kind === 'MAIN' && r.from === nodeId).map(r => r.to); },
    prevRacks(m, nodeId) {
      return L.prevMain(m, nodeId).map(id => L.node(m, id)).filter(n => n && n.node_kind === 'RACK');
    },
    nextNodes(m, nodeId) { return L.nextMain(m, nodeId).map(id => L.node(m, id)).filter(Boolean); },

    at(m, nodeId) { return m.units.filter(u => u.node_id === nodeId); },
    qtyOf(u) { return u.contents.reduce((a, c) => a + c.qty, 0); },
    mixOf(u) { return u.contents.map(c => c.part_no + ' x' + c.qty).join(', '); },

    /** v_rack_slot — 빈 칸도 돌려준다. */
    slotsOf(m, rackId) {
      const rack = L.node(m, rackId);
      if (!rack || !rack.slots) return [];
      return rack.slots.map(s => {
        const inSlot = L.at(m, rackId).filter(u => u.slot_no === s.slot_no);
        return { slot_no: s.slot_no, capacity: s.capacity, used: inSlot.length,
                 // 배치명만으로는 안에 뭐가 들었는지 모른다 — 종수를 함께 준다
                 contents: inSlot.slice().sort((a, b) => a.pos_no - b.pos_no)
                   .map(u => u.display_id + ' (' + u.contents.length + '종)') };
      });
    },
    rackLoad(m, rackId) {
      const s = L.slotsOf(m, rackId);
      return { used: s.reduce((a, x) => a + x.used, 0),
               capacity: s.reduce((a, x) => a + x.capacity, 0), slots: s.length };
    },

    /** v_retrievable — 랙의 slot_access 규칙으로 지금 꺼낼 수 있는 것만 표시. */
    queueOf(m, rackId, slotNo) {
      const rack = L.node(m, rackId);
      const access = rack ? (rack.slot_access || 'FIFO') : 'FIFO';
      const rows = L.at(m, rackId).filter(u => u.slot_no === slotNo)
        .slice().sort((a, b) => a.pos_no - b.pos_no);
      if (!rows.length) return [];
      const pos = rows.map(r => r.pos_no);
      const pick = access === 'FIFO' ? Math.min.apply(null, pos)
                 : access === 'LIFO' ? Math.max.apply(null, pos) : null;
      return rows.map(u => Object.assign({}, u, {
        retrievable: access === 'RANDOM' ? true : u.pos_no === pick,
        total_qty: L.qtyOf(u)
      }));
    },

    // 이하 BATCH_SPLIT
    /** 파트넘버별 판정 행. 부품 ID 를 만들지 않는다 — 아직 존재하지 않는다. */
    judgeRows(m, batch, saved) {
      saved = saved || {};
      return batch.contents.map(c => {
        const s = saved[c.part_no] || {}, p = m.part[c.part_no] || {};
        const ng = s.ng == null ? 0 : s.ng;
        return { part_no: c.part_no, name: p.name || c.part_no, cad_ref: p.cad_ref || null,
                 qty: c.qty, ok: s.ok == null ? c.qty - ng : s.ok, ng: ng, reason: s.reason || '' };
      });
    },
    totals(rows) {
      return rows.reduce((a, r) => ({ qty: a.qty + r.qty, ok: a.ok + (+r.ok || 0), ng: a.ng + (+r.ng || 0) }),
                         { qty: 0, ok: 0, ng: 0 });
    },
    /** 🔴 검증은 파트별로 각각. 합계가 맞아도 파트별이 어긋나면 안 된다. */
    rowValid(r) { return (+r.ok || 0) + (+r.ng || 0) === r.qty && (+r.ng ? !!r.reason : true); },
    badRows(rows) { return rows.filter(r => !L.rowValid(r)); },

    /** 일괄 OK 대상 = 아직 손대지 않은 파트. 이미 입력한 줄은 건드리지 않는다. */
    untouched(rows, saved) {
      saved = saved || {};
      const list = rows.filter(r => saved[r.part_no] == null);
      return { kinds: list.length, qty: list.reduce((a, r) => a + r.qty, 0), parts: list };
    },
    canComplete(rows, interlockOk) { return !!rows.length && interlockOk && rows.every(L.rowValid); },

    /**
     * Split — 배치가 개별 부품으로 분해된다. outputs 에는 OK 수량만.
     * NG 는 part_scrap 으로 기록되고 unit 이 생기지 않는다.
     */
    nextGroupId(m) { m.group_seq += 1; return 'G-' + String(m.group_seq).padStart(4, '0'); },

    splitBatch(m, batch, rows, nodeId, groupId) {
      const node = L.node(m, nodeId);
      const prefix = node && node.id_prefix ? node.id_prefix : 'S';
      // 묶음을 넘겨받으면 거기에 누적한다. 없으면 새로 딴다.
      const group_id = groupId || L.nextGroupId(m);
      const born = [];
      rows.forEach(r => {
        for (let i = 0; i < (+r.ok || 0); i++) {
          m.id_counter[prefix] = (m.id_counter[prefix] || 1) + 1;
          born.push({
            unit_id: batch.unit_id + '-' + prefix + m.id_counter[prefix],
            unit_kind: 'PART', display_id: batch.display_id + '-' + prefix + m.id_counter[prefix],
            parent_display_id: batch.display_id, order_id: batch.order_id,
            node_id: nodeId, group_id: group_id, status: 'WAIT',
            contents: [{ part_no: r.part_no, qty: 1 }]
          });
        }
      });
      const ev = { kind: 'SPLIT', unit_id: batch.unit_id, node_id: nodeId, group_id: group_id,
                   outputs: rows.filter(r => +r.ok > 0).map(r => ({ part_no: r.part_no, qty: +r.ok })) };
      const scraps = rows.filter(r => +r.ng > 0).map(r => ({
        unit_id: batch.unit_id, part_no: r.part_no, qty: +r.ng,
        node_id: nodeId, reason: r.reason, source: 'MANUAL' }));

      // 배치는 소비된다. 랙의 뒤 배치를 한 칸 당긴다 (FIFO 라 2번이 1번이 된다).
      const from = { node_id: batch.node_id, slot_no: batch.slot_no, pos_no: batch.pos_no };
      m.units = m.units.filter(u => u.unit_id !== batch.unit_id);
      m.units.forEach(u => {
        if (u.node_id === from.node_id && u.slot_no === from.slot_no && u.pos_no > from.pos_no) u.pos_no -= 1;
      });
      born.forEach(b => m.units.push(b));
      const t = L.totals(rows);
      return { ok: t.ok, ng: t.ng, group_id: group_id, born: born, event: ev, scraps: scraps };
    },

    /** 묶음째 이동 — 부품 N건이 아니라 Moved 1건. */
    groups(m, nodeId) {
      const g = new Map();
      L.at(m, nodeId).filter(u => u.unit_kind === 'PART' && u.group_id).forEach(u => {
        if (!g.has(u.group_id)) g.set(u.group_id, { group_id: u.group_id, units: [] });
        g.get(u.group_id).units.push(u);
      });
      return Array.from(g.values());
    },
    /** 묶음 안을 출처 배치별로 쪼개 본다 — 여러 배치가 섞이므로 어디서 왔는지 보여야 한다. */
    groupSources(m, nodeId, groupId) {
      const by = new Map();
      L.at(m, nodeId).filter(u => u.group_id === groupId).forEach(u => {
        const src = u.parent_display_id || '?';
        if (!by.has(src)) by.set(src, { display_id: src, parts: {}, qty: 0 });
        const e = by.get(src), pn = u.contents[0].part_no;
        e.parts[pn] = (e.parts[pn] || 0) + 1; e.qty += 1;
      });
      return Array.from(by.values());
    },
    groupCount(m, nodeId, groupId) {
      return L.at(m, nodeId).filter(u => u.group_id === groupId).length;
    },
    /**
     * 묶음 정원 — 이 묶음이 통째로 들어갈 설비의 정원.
     * 분리대에서 만든 묶음은 서포트제거를 거쳐 경화기로 가므로 두 홉을 본다.
     * ponytail: "묶음이 어디서 깨지는가"가 스키마에 없어 capacity>1 로 근사한다
     *           (치수검사는 부품 하나씩이라 capacity=1 로 걸러진다).
     *           node 에 group_breaks 플래그가 생기면 그것으로 바꾼다.
     */
    groupTarget(m, nodeId) {
      const seen = {}; let front = [nodeId], best = null;
      for (let hop = 0; hop < 2; hop++) {
        const nxt = [];
        front.forEach(id => L.nextMain(m, id).forEach(t => { if (!seen[t]) { seen[t] = 1; nxt.push(t); } }));
        nxt.forEach(id => {
          const nd = L.node(m, id);
          // 설비 정원 또는 박스 정원 — 묶음이 통째로 들어가야 하는 곳이면 둘 다 제약이다
          if (nd && (nd.node_kind === 'STATION' || nd.count_by_group)) {
            const c = L.groupCapacity(nd);
            if (c > 1) best = best == null ? c : Math.min(best, c);
          }
        });
        front = nxt;
      }
      return best || 0;
    },

    moveGroup(m, groupId, fromNode, toNode) {
      const moved = m.units.filter(u => u.group_id === groupId && u.node_id === fromNode);
      moved.forEach(u => { u.node_id = toNode; u.status = 'WAIT'; });
      return { count: moved.length,
               event: { kind: 'MOVED', group_id: groupId, from_node: fromNode, to_node: toNode } };
    },

    // 이하 PART_JUDGE
    /** 대기 부품. 파트넘버로 정렬 — 같은 모양끼리 붙어 있어야 손이 덜 간다. */
    waitingParts(m, nodeId) {
      return L.at(m, nodeId).filter(u => u.unit_kind === 'PART')
        .map(u => {
          const pn = u.contents[0] ? u.contents[0].part_no : '';
          return { unit_id: u.unit_id, display_id: u.display_id, group_id: u.group_id,
                   part_no: pn, part_name: (m.part[pn] || {}).name || pn,
                   attrs: (m.part[pn] || {}).attrs || {} };
        })
        .sort((a, b) => a.part_no.localeCompare(b.part_no) || a.display_id.localeCompare(b.display_id));
    },
    /** 측정 스펙이 노드에 있으면 입력란을 띄운다. ui_kind 는 그대로 PART_JUDGE. */
    measureSpec(m, nodeId) { const n = L.node(m, nodeId); return (n && n.measure) || null; },
    inTolerance(v, attrs) {
      if (v == null || v === '' || !attrs || attrs.nominal_mm == null) return null;
      return Math.abs(+v - attrs.nominal_mm) <= (attrs.tol_mm == null ? Infinity : attrs.tol_mm);
    },
    /** 판정 기록 — append only. 사람이 뒤집으면 새 행이 쌓인다. */
    judge(m, unitId, nodeId, verdict, value, note) {
      m.judgement.push({ ts: Date.now(), unit_id: unitId, node_id: nodeId,
                         verdict: verdict, value: value || null, note: note || null, source: 'MANUAL' });
      return m.judgement[m.judgement.length - 1];
    },
    latestVerdict(m, unitId) {
      for (let i = m.judgement.length - 1; i >= 0; i--) if (m.judgement[i].unit_id === unitId) return m.judgement[i];
      return null;
    },
    /** NG 부품은 라인을 떠난다. */
    scrapPart(m, unitId, nodeId, reason) {
      const u = m.units.find(x => x.unit_id === unitId);
      if (!u) return null;
      m.units = m.units.filter(x => x.unit_id !== unitId);
      return { event: { kind: 'MOVED', unit_id: unitId, from_node: nodeId, to_node: 'EXIT-SCRAP' },
               scrap: { unit_id: unitId, part_no: u.contents[0].part_no, qty: 1,
                        node_id: nodeId, reason: reason, source: 'MANUAL' } };
    },

    /** 묶음 정원 — 경화기면 설비 용량, 트레이 랙이면 트레이 정원. */
    groupCapacity(dest) {
      if (!dest) return 0;
      return dest.group_capacity != null ? dest.group_capacity : (dest.capacity || 0);
    },
    isFree(m, node) { return L.at(m, node.node_id).length === 0; },
    occupancy(m, node) {
      return L.at(m, node.node_id).reduce((a, u) => a + (u.unit_kind === 'PART' ? 1 : L.qtyOf(u)), 0);
    },

    /** 이 랙에 담는 중인 박스. 없으면 새로 딴다 — 랙마다 따로다. */
    openBox(m, rackId) {
      m.box = m.box || {};
      if (!m.box[rackId]) {
        m.box_seq += 1;
        m.box[rackId] = { group_id: 'BOX-' + String(m.box_seq).padStart(4, '0'), items: [] };
      }
      return m.box[rackId];
    },
    /** 박스 합류 — 부품 하나씩 join_group 으로 붙는다. */
    joinBox(m, unitId, rackId) {
      const u = m.units.find(x => x.unit_id === unitId);
      if (!u) return null;
      const box = L.openBox(m, rackId);
      m.units = m.units.filter(x => x.unit_id !== unitId);
      box.items.push({ unit_id: unitId, display_id: u.display_id, part_no: u.contents[0].part_no });
      return { kind: 'MOVED', unit_id: unitId, join_group: box.group_id };
    },
    closeBox(m, rackId) {
      const done = m.box && m.box[rackId];
      if (!done || !done.items.length) return null;
      // 마감한 박스는 랙에 올라간다 — 안 그러면 어디에도 안 남고 다음 공정이 못 본다
      m.boxes = m.boxes || [];
      m.boxes.push({ group_id: done.group_id, items: done.items, node_id: rackId || null });
      delete m.box[rackId];                    // 다음 것은 담을 때 새로 열린다
      return done;
    },

    /**
     * 이 설비에 들어올 차례를 기다리는 것들.
     *   직전이 랙  = 적재분 + 그 랙에 올라간 박스
     *   직전이 작업대 = 아직 안 넘긴 묶음
     */
    inbound(m, nodeId) {
      const rows = [];
      L.prevMain(m, nodeId).forEach(id => {
        const n = L.node(m, id);
        if (!n) return;
        const push = (kind, ref, label, qty) => rows.push({
          key: kind + ':' + ref, kind: kind, ref: ref, label: label, qty: qty,
          from: n.label, from_node: id, ready: false });
        if (n.node_kind === 'RACK') {
          (m.boxes || []).filter(b => b.node_id === id)
            .forEach(b => push('BOX', b.group_id, b.group_id, b.items.length));
          L.at(m, id).slice().sort((a, b) => (a.slot_no - b.slot_no) || (a.pos_no - b.pos_no))
            .forEach(u => push('UNIT', u.unit_id, u.display_id, L.qtyOf(u)));
        } else {
          L.groups(m, id).forEach(g => push('GROUP', g.group_id, g.group_id, g.units.length));
        }
      });
      // FIFO — 출처마다 맨 앞 것만 지금 넣을 수 있다
      const seen = {};
      rows.forEach(r => { if (!seen[r.from_node]) { seen[r.from_node] = 1; r.ready = true; } });
      return rows;
    },

    /** 랙에서 하나를 빼면 뒤엣것이 한 칸 당겨진다 (FIFO 라 번호가 밀린다). */
    pullFromRack(m, u) {
      if (u.slot_no == null) return;
      const from = { node_id: u.node_id, slot_no: u.slot_no, pos_no: u.pos_no };
      m.units.forEach(x => {
        if (x !== u && x.node_id === from.node_id && x.slot_no === from.slot_no && x.pos_no > from.pos_no) {
          x.pos_no -= 1;
        }
      });
      u.slot_no = null; u.pos_no = null;
    },

    /** 대기 큐에서 골라 설비에 넣는다. 차 있으면 못 넣는다. */
    loadInto(m, nodeId, key) {
      const dest = L.node(m, nodeId);
      if (!dest || !L.isFree(m, dest)) return null;
      const row = L.inbound(m, nodeId).find(r => r.key === key);
      if (!row || !row.ready) return null;

      let count = 0;
      if (row.kind === 'GROUP') {
        count = L.moveGroup(m, row.ref, row.from_node, nodeId).count;
      } else if (row.kind === 'UNIT') {
        const u = m.units.find(x => x.unit_id === row.ref);
        if (!u) return null;
        L.pullFromRack(m, u);
        u.node_id = nodeId; u.status = 'WAIT'; u.elapsed_s = 0; u.plan_s = null;
        count = L.qtyOf(u);
      } else {                                   // BOX — 담겨 있던 부품이 설비로 들어간다
        const bi = (m.boxes || []).findIndex(b => b.group_id === row.ref);
        if (bi < 0) return null;
        const box = m.boxes[bi];
        box.items.forEach(it => m.units.push({
          unit_id: it.unit_id, unit_kind: 'PART', display_id: it.display_id,
          order_id: it.order_id || null, node_id: nodeId, group_id: box.group_id,
          status: 'WAIT', elapsed_s: 0, contents: [{ part_no: it.part_no, qty: 1 }]
        }));
        count = box.items.length;
        m.boxes.splice(bi, 1);
      }
      return { count: count, label: row.label,
               event: { kind: 'MOVED', node_id: nodeId, from_node: row.from_node,
                        ref: row.ref, source: 'MANUAL' } };
    },

    /**
     * 설비 명령 — 시작 · 중지 · 완료.
     * 실린 것이 없으면 아무 명령도 못 준다 (빈 설비를 돌릴 수는 없다).
     * ponytail: 상태 전이표를 따로 두지 않고 세 줄로 적는다. 명령이 늘면 그때 표로.
     */
    CMD: [{ key: 'start', label: '시작', to: 'RUN' },
          { key: 'stop',  label: '중지', to: 'HOLD' },
          { key: 'done',  label: '완료', to: 'DONE' }],
    cmdOf(key) { return L.CMD.find(c => c.key === key) || null; },
    /** 시작할 때 가동 시간을 받는 설비인가. measure 스펙과 같은 방식 — 노드가 정한다. */
    durationSpec(m, nodeId) {
      const n = L.node(m, nodeId);
      if (!n || !n.duration_input) return null;
      return { label: '가동 시간', unit: '분',
               default: Math.max(1, Math.round((n.std_cycle_s || 0) / 60)) };
    },
    canCmd(m, nodeId, key) {
      const u = L.at(m, nodeId)[0];
      if (!u) return false;
      if (key === 'start') return u.status !== 'RUN';
      if (key === 'stop')  return u.status === 'RUN';
      if (key === 'done')  return u.status === 'RUN' || u.status === 'HOLD';
      return false;
    },
    runCmd(m, nodeId, key, minutes) {
      if (!L.canCmd(m, nodeId, key)) return null;
      const here = L.at(m, nodeId), u = here[0], c = L.cmdOf(key), from = u.status;
      let plan_s = null;
      if (key === 'start') {
        const spec = L.durationSpec(m, nodeId);
        if (spec) {
          const min = Math.round(+minutes);
          if (!(min > 0)) return null;          // 시간을 안 정하면 돌리지 않는다
          plan_s = min * 60;
        }
      }
      here.forEach(x => {
        x.status = c.to;
        if (key === 'start') {
          if (plan_s) x.plan_s = plan_s;
          if (x.elapsed_s == null) x.elapsed_s = 0;
        }
      });
      return { kind: 'CMD', node_id: nodeId, unit_ids: here.map(x => x.unit_id), cmd: key,
               from: from, to: c.to, plan_s: u.plan_s || null, source: 'MANUAL' };
    },
    /** 이 설비가 얼마나 돌기로 되어 있나 — 시작할 때 정한 값이 있으면 그것, 없으면 표준. */
    runTotal(m, node) {
      const u = L.at(m, node.node_id)[0];
      return (u && u.plan_s) || node.std_cycle_s || 0;
    },
    /** 블록 머리의 상태 뱃지. 비어 있으면 unit 이 없다. */
    stateBadge(m, nodeId) {
      const u = L.at(m, nodeId)[0];
      if (!u) return { text: '비어 있음', tone: 'gh' };
      return ({ RUN:   { text: '가동 중', tone: 'tl' },
                WAIT:  { text: '대기',    tone: '' },
                DONE:  { text: '완료',    tone: '' },
                HOLD:  { text: '정지',    tone: 'man' },
                ERROR: { text: '이상',    tone: 'man' } })[u.status] || { text: u.status, tone: '' };
    },

    interlockOf(m, nodeId) { return m.interlock[nodeId] || []; },
    interlockOk(m, nodeId) { return L.interlockOf(m, nodeId).every(i => i.ok); },

    fmt(s) {
      if (s == null) return '-';
      const mm = Math.floor(s / 60), ss = s % 60;
      return mm > 0 ? (ss ? mm + '분 ' + ss + '초' : mm + '분') : ss + '초';
    },
    progress(m, node) {
      const u = L.at(m, node.node_id)[0];
      const total = L.runTotal(m, node);
      if (!u || !total || u.elapsed_s == null) return null;
      return Math.min(100, Math.round(100 * u.elapsed_s / total));
    }
  };

  // 대기 큐 예시 — 앞 공정에서 이미 마감돼 랙에 올라가 있는 박스들.
  //   한 박스에 파트넘버가 섞여 있는 것이 기본이다 (앞 배치들이 함께 담긴다).
  [['BOX-0038', 'RK-CUR-WAIT-01', 'P5-W5', [['PN-A-2026', 7], ['PN-B-1180', 5]]],
   ['BOX-0039', 'RK-CUR-WAIT-01', 'P6-W6', [['PN-C-770', 6], ['PN-A-2026', 3]]],
   ['BOX-0040', 'RK-BPD-WAIT-01', 'P3-W3', [['PN-A-2026', 8], ['PN-C-770', 4]]],
   ['BOX-0041', 'RK-BPD-WAIT-01', 'P4-W4', [['PN-B-1180', 7]]]]
    .forEach(([id, rack, src, mix]) => {
      const items = []; let no = 0;
      mix.forEach(([pn, qty]) => {
        for (let i = 0; i < qty; i++) {
          no += 1;
          items.push({ unit_id: id.toLowerCase() + '-' + no,
                       display_id: src + '-S' + no, part_no: pn });
        }
      });
      MOCK.boxes.push({ group_id: id, node_id: rack, items: items });
    });

  MOCK.judgement = MOCK.judgement || [];
  const API = { MOCK: MOCK, L: L };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else root.CTL = API;

})(typeof window !== 'undefined' ? window : this);
