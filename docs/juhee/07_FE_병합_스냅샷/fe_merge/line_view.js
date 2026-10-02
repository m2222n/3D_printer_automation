/* 라인 모니터링 — 와이어프레임의 「설비·반송 흐름」 + 「플레이트 파이프라인」을
   기존 FE 디자인으로. 값은 제어 화면과 같은 CTL.MOCK 에서 나온다(조작하면 같이 바뀐다). */
(function () {
  const { MOCK: M, L } = window.CTL;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const card = 'bg-white rounded-xl border shadow-sm overflow-hidden';
  const hint = 'text-xs text-gray-500';
  const mono = 'font-mono text-xs';
  const pillC = 'px-2.5 py-1 rounded-full text-xs font-medium';
  const TONE = { run: 'bg-blue-50 text-blue-700', ok: 'bg-green-50 text-green-700',
                 warn: 'bg-amber-50 text-amber-700', bad: 'bg-red-50 text-red-700', idle: 'bg-gray-100 text-gray-600' };
  const DOT = { run: 'bg-blue-500 animate-pulse', ok: 'bg-green-500', warn: 'bg-amber-500', bad: 'bg-red-500', idle: 'bg-gray-400' };
  const pill = (t, tone) => `<span class="${pillC} ${TONE[tone] || TONE.idle} inline-flex items-center gap-1.5">` +
    `<span class="w-2 h-2 rounded-full ${DOT[tone] || DOT.idle}"></span>${esc(t)}</span>`;

  const order = () => L.stepOrder(M);
  const ordered = () => {
    const o = order();
    return M.nodes.slice().sort((a, b) => (o[a.node_id] ?? 99) - (o[b.node_id] ?? 99) || a.node_id.localeCompare(b.node_id));
  };

  /* ── 상단 요약 (기존 FE 모니터링 탭의 통계 타일과 같은 형태) ── */
  function summary() {
    const stations = M.nodes.filter((n) => n.node_kind === 'STATION');
    const run = stations.filter((n) => (L.at(M, n.node_id)[0] || {}).status === 'RUN').length;
    const busy = stations.filter((n) => !L.isFree(M, n)).length;
    const wip = M.units.length + (M.boxes || []).reduce((a, b) => a + b.items.length, 0);
    const waiting = M.nodes.filter((n) => n.node_kind === 'RACK')
      .reduce((a, r) => a + L.rackLoad(M, r.node_id).used, 0) + (M.boxes || []).length;
    const tile = (label, value, cls) =>
      `<div class="rounded-lg border p-3 sm:p-4 ${cls}"><p class="text-xs sm:text-sm text-gray-500">${label}</p>` +
      `<p class="text-2xl sm:text-3xl font-bold mt-1">${value}</p></div>`;
    return '<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6">' +
      tile('공정 설비', stations.length, 'bg-gray-100 border-gray-400 text-gray-900') +
      tile('가동 중', run, 'bg-blue-50 border-blue-200 text-blue-600') +
      tile('점유 설비', busy, 'bg-gray-50 border-gray-200 text-gray-900') +
      tile('랙 대기', waiting, 'bg-amber-50 border-amber-200 text-amber-600') +
      '</div>';
  }

  /* ── 반송 (수동 구간이 병목) ── */
  function transport() {
    const T = [
      { name: '로봇암 A', tone: 'run', state: '이송 중', note: '프린터 → 완료 랙 · 잔여 8초', load: 'P13-W13' },
      { name: '로봇암 B', tone: 'idle', state: '대기', note: '큐 1건', load: null },
      { name: '작업자 반송', tone: 'bad', state: '수동 구간', note: '경화 반출 대기 3분', load: null },
    ];
    return `<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">` + T.map((t) =>
      `<div class="${card} ${t.tone === 'bad' ? 'border-red-200' : ''}"><div class="px-4 py-3 flex items-center gap-2">` +
      `<span class="font-semibold text-gray-900 text-sm">${t.name}</span>${pill(t.state, t.tone)}</div>` +
      `<div class="px-4 pb-3 flex items-center justify-between ${hint}"><span>${t.note}</span>` +
      `<span class="${mono} ${t.load ? 'text-gray-700' : 'text-gray-300'}">${t.load || '빈손'}</span></div></div>`).join('') + '</div>';
  }

  /* ── 공정 흐름 — 와이어프레임 형태(랙 위 · 설비 아래 · 사이에 반송) ──
     열 = 공정 하나. 랙이면 윗단, 설비면 아랫단. 가운데 띠에 누가 옮기는지와 큐. */
  const OWNER = {          // 데모용 — 어느 구간을 로봇이 하고 어디부터 사람이 하는가
    PRINTER: '로봇암 A', WASHER: '로봇암 A',
    SEPARATION: '작업자', SUPPORT_REMOVAL: '작업자', CURER: '작업자', INSPECT: '작업자',
    BEAMPICK: '로봇암 B',
  };

  /** 열 만들기 — 설비는 group_label 로 묶어 한 장(프린터 4대 = 카드 1장 + 베이 4개). */
  function columns() {
    const cols = [];
    ordered().forEach((n) => {
      const key = n.node_kind === 'RACK' ? n.node_id : (n.group_label || n.label);
      let c = cols.find((x) => x.key === key);
      if (!c) cols.push(c = { key, kind: n.node_kind, label: n.node_kind === 'RACK' ? n.label : key, nodes: [] });
      c.nodes.push(n);
    });
    return cols;
  }

  function rackCard(n) {
    const ld = L.rackLoad(M, n.node_id);
    const boxes = (M.boxes || []).filter((b) => b.node_id === n.node_id);
    const nextOut = L.slotsOf(M, n.node_id).map((s) => s.contents[0]).filter(Boolean)[0];
    return `<div class="${card} border-dashed bg-gray-50">` +
      '<div class="px-3 py-2 border-b bg-white/60 flex items-center gap-2">' +
      `<span class="font-semibold text-gray-900 text-xs truncate">${esc(n.label)}</span>` +
      `<span class="${pillC} ${TONE.idle} ml-auto flex-shrink-0">${ld.used}/${ld.capacity}</span></div>` +
      '<div class="px-3 py-2 space-y-1.5">' +
      L.slotsOf(M, n.node_id).map((s) =>
        `<div><p class="${hint}">칸 ${s.slot_no} · ${s.used}/${s.capacity}</p>` +
        '<div class="grid grid-cols-4 gap-1 mt-1">' +
        Array.from({ length: s.capacity }, (_, i) =>
          `<span class="h-5 rounded border text-[9px] leading-[18px] text-center ${mono} ${
            i < s.used ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-gray-200 text-gray-300'}">${
            i < s.used ? esc((s.contents[i] || '').split(' ')[0].slice(-4)) : i + 1}</span>`).join('') +
        '</div></div>').join('') +
      `<div class="pt-1.5 border-t border-dashed ${hint} space-y-0.5">` +
      (nextOut ? `<p class="truncate">다음 반출 <b class="${mono} text-gray-700">${esc(nextOut.split(' ')[0])}</b></p>` : '<p>반출 대기 없음</p>') +
      (boxes.length ? `<p>박스 ${boxes.length}개 · 부품 ${boxes.reduce((a, b) => a + b.items.length, 0)}개</p>` : '') +
      '</div></div></div>';
  }

  function stationCard(col) {
    const nodes = col.nodes;
    const runN = nodes.filter((n) => (L.at(M, n.node_id)[0] || {}).status === 'RUN').length;
    const freeN = nodes.filter((n) => L.isFree(M, n)).length;
    const bay = (n) => {
      const u = L.at(M, n.node_id)[0];
      const bd = L.stateBadge(M, n.node_id);
      const tone = { tl: 'run', man: 'bad', gh: 'idle' }[bd.tone] || 'idle';
      const pct = L.progress(M, n);
      // 설비가 여럿일 때만 베이 번호를 앞에 붙인다 (1대뿐이면 열 제목과 같은 말이 두 번 나온다)
      const short = nodes.length > 1 ? n.label.replace(/^.*?(\d+호기|\d+)$/, '$1') : '';
      return `<div class="rounded-lg border px-2 py-1.5 ${
        u ? (u.status === 'RUN' ? 'border-blue-200 bg-blue-50' : (u.status === 'HOLD' || u.status === 'ERROR' ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'))
          : 'border-dashed border-gray-200 bg-white'}">` +
        '<div class="flex items-center gap-1.5">' +
        (short ? `<span class="${mono} font-semibold text-gray-600 flex-shrink-0">${esc(short)}</span>` : '') +
        `<span class="${mono} text-gray-900 truncate flex-1">${u ? esc(u.display_id) : '비어 있음'}</span>` +
        `<span class="w-2 h-2 rounded-full flex-shrink-0 ${DOT[tone]}"></span></div>` +
        (u && pct != null
          ? `<div class="h-1 bg-gray-200 rounded-full overflow-hidden mt-1"><div class="h-full bg-blue-500 rounded-full" style="width:${pct}%"></div></div>` +
            `<p class="${hint} mt-0.5">${bd.text} · ${L.fmt(u.elapsed_s)}</p>`
          : `<p class="${hint} mt-0.5">${u ? bd.text : '투입 가능'}</p>`) +
        '</div>';
    };
    return `<div class="${card}">` +
      '<div class="px-3 py-2 border-b bg-gray-50 flex items-center gap-2">' +
      `<span class="font-semibold text-gray-900 text-xs truncate">${esc(col.label)}</span>` +
      `<span class="${pillC} ${TONE.idle} ml-auto flex-shrink-0">설비 ${nodes.length}</span></div>` +
      `<div class="px-3 py-2 space-y-1.5">${nodes.map(bay).join('')}` +
      `<p class="${hint} pt-1.5 border-t border-dashed">가동 ${runN} · 비어 있음 ${freeN}</p></div></div>`;
  }

  /** 두 열 사이 — 와이어프레임처럼 꺾인 화살표를 그린다 (아래로 / 위로).
      열 너비가 고정(px)이라 좌표를 그대로 계산할 수 있다. */
  // 카드 너비보다 열 간격(피치)을 좁게 둔다 — 윗단·아랫단이 가로로 겹쳐 지그재그가 촘촘해진다
  // (원본 와이어프레임도 100px 열에 148px 카드였다)
  const CARD = 216, PITCH = 150, BAND = 72;
  function connector(from, to, pitch) {
    const owner = OWNER[to.nodes[0].node_type] || (to.kind === 'RACK' ? OWNER[from.nodes[0].node_type] : null) || '반송';
    const manual = owner === '작업자';
    const qty = to.nodes.reduce((a, n) => a + L.inbound(M, n.node_id).length, 0);
    const stroke = manual ? '#f87171' : '#9ca3af';       // red-400 / gray-400
    const dash = manual ? ' stroke-dasharray="5 4"' : '';

    const W = pitch + CARD, mid = BAND / 2;      // 왼 카드 왼끝 ~ 오른 카드 오른끝
    const top = 0, bot = BAND;
    const y1 = to.kind === 'RACK' ? top : bot;                // 도착 카드가 있는 단
    const tip = (x, y) => (y === bot ? `${x},${bot} ${x - 5},${bot - 9} ${x + 5},${bot - 9}`
                                     : `${x},${top} ${x - 5},${top + 9} ${x + 5},${top + 9}`);
    let path, head;
    if (from.kind === to.kind) {
      // 같은 단끼리(설비→설비) — 올라갔다 건너 다시 내려간다
      const x1 = CARD / 2, x2 = pitch + CARD / 2;
      path = `M ${x1} ${y1} L ${x1} ${mid} L ${x2} ${mid} L ${x2} ${y1}`;
      head = tip(x2, y1);
    } else {
      // 윗단↔아랫단 — 두 블록이 붙어 있으므로 사이에 세로 화살표 하나
      const x = W / 2;
      path = `M ${x} ${y1 === bot ? top : bot} L ${x} ${y1}`;
      head = tip(x, y1);
    }

    return `<div class="relative" style="width:${W}px;height:${BAND}px;overflow:visible">` +
      `<svg width="${W}" height="${BAND}" class="absolute inset-0">` +
      `<path d="${path}" fill="none" stroke="${stroke}" stroke-width="1.5"${dash}></path>` +
      `<polygon points="${head}" fill="${stroke}"></polygon></svg>` +
      '<span class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 ' +
      `px-2 py-1 rounded-full border text-[10px] font-medium whitespace-nowrap ${
        manual ? 'bg-red-50 border-red-200 text-red-700' : 'bg-white border-gray-200 text-gray-600'}">` +
      `${manual ? '✋ ' : ''}${esc(owner)}<span class="ml-1 text-gray-400">큐 ${qty}</span></span></div>`;
  }

  function flow() {
    const cols = columns();
    // 다음 열이 반대쪽 단이면 가로로 겹쳐도 되니 좁게(PITCH), 같은 단이면 카드가 부딪히므로 넓게
    const widths = cols.map((c, i) =>
      i === cols.length - 1 ? CARD : (cols[i + 1].kind === c.kind ? CARD + 8 : PITCH));
    let cells = '';
    cols.forEach((c, i) => {
      const row = c.kind === 'RACK' ? 1 : 3;
      cells += `<div style="grid-column:${i + 1};grid-row:${row};width:${CARD}px" class="${row === 1 ? 'self-end' : 'self-start'}">` +
        (c.kind === 'RACK' ? rackCard(c.nodes[0]) : stationCard(c)) + '</div>';
      if (i < cols.length - 1) {
        cells += `<div style="grid-column:${i + 1} / span 2;grid-row:2" class="flex items-center justify-center">` +
          connector(c, cols[i + 1], widths[i]) + '</div>';
      }
    });
    return `<div class="${card} p-4 mb-6">` +
      `<div class="flex items-center gap-2 mb-3"><span class="font-semibold text-gray-900 text-sm">공정 흐름</span>` +
      `<span class="${hint}">윗단 = 랙(버퍼) · 아랫단 = 설비 · 사이 = 반송</span></div>` +
      '<div class="overflow-x-auto pb-2"><div class="grid" ' +
      `style="grid-template-columns:${widths.map((w) => w + 'px').join(' ')};` +
      `grid-template-rows:auto ${BAND}px auto">${cells}</div></div></div>`;
  }

  /* ── 플레이트 파이프라인 — 행=재공, 열=공정 ── */
  function pipeline() {
    const o = order();
    const cols = [];
    M.nodes.filter((n) => n.node_kind === 'STATION').forEach((n) => {
      const label = n.group_label || n.label;
      let c = cols.find((x) => x.label === label);
      if (!c) cols.push(c = { label, step: o[n.node_id] ?? 99, ids: [] });
      c.ids.push(n.node_id);
      c.step = Math.min(c.step, o[n.node_id] ?? 99);
    });
    cols.sort((a, b) => a.step - b.step);
    const colOf = (nodeId) => {
      let i = cols.findIndex((c) => c.ids.includes(nodeId));
      if (i >= 0) return { i, waiting: false };
      const nxt = L.nextMain(M, nodeId);          // 랙이면 다음 설비 앞에서 대기
      for (const id of nxt) {
        i = cols.findIndex((c) => c.ids.includes(id));
        if (i >= 0) return { i, waiting: true };
      }
      return { i: cols.length - 1, waiting: true };
    };

    const rows = [];
    M.units.filter((u) => u.unit_kind === 'BATCH').forEach((u) =>
      rows.push({ id: u.display_id, sub: `${L.qtyOf(u)}개 · ${u.contents.length}종`, node: u.node_id, status: u.status }));
    const seen = {};
    M.units.filter((u) => u.unit_kind === 'PART' && u.group_id).forEach((u) => {
      if (seen[u.group_id]) { seen[u.group_id].n += 1; return; }
      seen[u.group_id] = { id: u.group_id, n: 1, node: u.node_id, status: u.status };
    });
    Object.values(seen).forEach((g) => rows.push({ id: g.id, sub: `${g.n}개 부품`, node: g.node, status: g.status }));
    (M.boxes || []).forEach((b) => rows.push({ id: b.group_id, sub: `${b.items.length}개 부품`, node: b.node_id, status: 'DONE' }));

    const head = `<thead class="bg-gray-50 text-gray-500"><tr>` +
      `<th class="px-3 py-2 text-left font-medium sticky left-0 bg-gray-50 w-44">재공</th>` +
      cols.map((c, i) => `<th class="px-3 py-2 text-left font-medium whitespace-nowrap">${i + 1} · ${esc(c.label)}` +
        `<span class="block font-normal text-[10px] text-gray-400">${c.ids.length}대</span></th>`).join('') + '</tr></thead>';

    const body = rows.map((r) => {
      const { i, waiting } = colOf(r.node);
      const nodeLabel = (L.node(M, r.node) || {}).label || r.node;
      return '<tr class="hover:bg-gray-50">' +
        `<td class="px-3 py-2 sticky left-0 bg-white"><p class="${mono} font-semibold text-gray-900">${esc(r.id)}</p>` +
        `<p class="${hint}">${esc(r.sub)}</p></td>` +
        cols.map((_, ci) => {
          if (ci < i) return '<td class="px-3 py-2 bg-gray-50 text-gray-300 text-xs">✓</td>';
          if (ci > i) return '<td class="px-3 py-2 text-gray-300 text-xs">—</td>';
          const tone = waiting ? 'warn' : (r.status === 'RUN' ? 'run' : 'idle');
          return `<td class="px-3 py-2 ${waiting ? 'bg-amber-50' : 'bg-blue-50'}">` +
            `${pill(waiting ? '대기' : (r.status === 'RUN' ? '진행' : '투입됨'), tone)}` +
            `<p class="${hint} mt-1 truncate">${esc(nodeLabel)}</p></td>`;
        }).join('') + '</tr>';
    }).join('');

    return `<div class="${card}"><div class="px-4 py-3 border-b bg-gray-50 flex items-center gap-2">` +
      `<span class="font-semibold text-gray-900 text-sm">플레이트 파이프라인</span>` +
      `<span class="${hint}">행 = 재공 ${rows.length}건 · 열 = 공정</span></div>` +
      `<div class="overflow-x-auto"><table class="w-full text-sm">${head}<tbody class="divide-y divide-gray-100">${body}</tbody></table></div></div>`;
  }

  function render() {
    const view = $('wf-line-view').dataset.view || 'flow';
    $('wf-line-body').innerHTML = view === 'flow'
      ? summary() + transport() + flow()
      : summary() + pipeline();
    Array.from($('wf-line-tabs').children).forEach((b) => {
      const on = b.dataset.lineView === view;
      b.className = `py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
        on ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`;
    });
  }

  $('wf-line-tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-line-view]');
    if (!b) return;
    $('wf-line-view').dataset.view = b.dataset.lineView;
    render();
  });

  window.WF_LINE = { render };
  render();
})();
