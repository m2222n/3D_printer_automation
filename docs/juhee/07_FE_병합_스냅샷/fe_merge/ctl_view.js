/* ══════════════════════════════════════════════════════════════
   공정 제어 뷰 — 와이어프레임의 기능을 그대로, 디자인만 기존 FE(Tailwind)로.
   로직(window.CTL)은 손대지 않는다. 여기는 그리기와 클릭 배선만 한다.
   ══════════════════════════════════════════════════════════════ */
(function () {
  const { MOCK: M, L } = window.CTL;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* ── 기존 FE 에서 그대로 가져온 클래스 조합 ────────────────── */
  const C = {
    card: 'bg-white rounded-xl border shadow-sm overflow-hidden',
    cardHead: 'px-4 py-3 border-b bg-gray-50 flex items-center gap-2',
    cardTitle: 'font-semibold text-gray-900 text-sm',
    cardBody: 'px-4 py-3 space-y-3',
    row: 'bg-white rounded-lg border p-3 transition-all hover:shadow-sm',
    num: 'flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold',
    pill: 'px-2.5 py-1 rounded-full text-xs font-medium',
    hint: 'text-xs text-gray-500',
    label: 'text-sm text-gray-500',
    btn: 'px-3 py-2 rounded-lg text-sm font-medium border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors',
    btnPri: 'px-3 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors',
    btnDanger: 'px-3 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors',
    input: 'w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400',
    mono: 'font-mono text-xs',
  };
  const TONE = {
    run: 'bg-blue-50 text-blue-700', ok: 'bg-green-50 text-green-700',
    warn: 'bg-amber-50 text-amber-700', bad: 'bg-red-50 text-red-700',
    idle: 'bg-gray-100 text-gray-600',
  };
  const DOT = { run: 'bg-blue-500 animate-pulse', ok: 'bg-green-500', warn: 'bg-amber-500', bad: 'bg-red-500', idle: 'bg-gray-400' };

  const pill = (text, tone) =>
    `<span class="${C.pill} ${TONE[tone] || TONE.idle} inline-flex items-center gap-1.5">` +
    `<span class="w-2 h-2 rounded-full ${DOT[tone] || DOT.idle}"></span>${esc(text)}</span>`;
  const card = (title, right, body, extra) =>
    `<div class="${C.card} ${extra || ''}"><div class="${C.cardHead}">` +
    `<span class="${C.cardTitle}">${title}</span><span class="flex-1"></span>${right || ''}` +
    `</div><div class="${C.cardBody}">${body}</div></div>`;
  const step = (n, title, note) =>
    `<div class="flex items-center gap-2 mb-2"><span class="${C.num}">${n}</span>` +
    `<span class="font-semibold text-gray-900 text-sm">${title}</span>` +
    (note ? `<span class="${C.hint} ml-auto">${note}</span>` : '') + '</div>';
  const bar = (pct, tone) =>
    `<div class="h-2 bg-gray-200 rounded-full overflow-hidden"><div class="h-full rounded-full transition-all duration-500 ${tone || 'bg-blue-500'}" style="width:${pct}%"></div></div>`;
  const empty = (t) => `<div class="py-10 text-center text-gray-400 text-sm">${esc(t)}</div>`;

  /* 상태 → 색 */
  const badgeOf = (nodeId) => {
    const b = L.stateBadge(M, nodeId);
    const tone = { tl: 'run', man: 'bad', gh: 'idle' }[b.tone] || 'idle';
    return pill(b.text, b.text === '완료' ? 'ok' : tone);
  };

  const S = { menu: null, node: null, rack: null, slot: null, open: null,
              judge: {}, verdict: {}, measure: {}, pick: null, openGroup: null };

  function log(kind, text) {
    const d = new Date();
    M.log.unshift({ ts: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
                    actor: '담당자', kind, text });
    M.log = M.log.slice(0, 8);
  }

  /* ── 확인 모달 (기존 FE 알림 패널과 같은 rounded-xl/shadow-xl) ── */
  let onYes = null;
  function confirmBox(title, html, yesLabel, cb, danger) {
    $('wf-dlg-t').textContent = title;
    $('wf-dlg-c').innerHTML = html;
    const y = $('wf-dlg-yes');
    y.textContent = yesLabel;
    y.className = danger ? C.btnDanger + ' flex-1' : C.btnPri + ' flex-1';
    onYes = cb;
    $('wf-mask').classList.remove('hidden');
  }
  function closeDlg() { $('wf-mask').classList.add('hidden'); onYes = null; }

  /* ── 사이드: 인터록 + 명령 로그 ───────────────────────────── */
  function sidePanel(nodeId, extra) {
    const locks = L.interlockOf(M, nodeId);
    const okCount = locks.filter((i) => i.ok).length;
    return (extra || '') +
      (locks.length ? card('인터록',
        pill(`${okCount} / ${locks.length}`, L.interlockOk(M, nodeId) ? 'ok' : 'bad'),
        locks.map((i) => `<label class="flex items-center gap-2 text-sm ${i.ok ? 'text-gray-700' : 'text-red-600 font-medium'} cursor-pointer">` +
          `<input type="checkbox" class="w-4 h-4 rounded border-gray-300 accent-blue-600" data-lock="${esc(i.key)}"${i.ok ? ' checked' : ''}>` +
          `${esc(i.label)}</label>`).join('') +
        `<p class="${C.hint}">미충족이면 판정이 잠깁니다.</p>`) : '') +
      card('명령 로그', `<span class="${C.hint}">최근 ${M.log.length}건</span>`,
        `<div class="divide-y divide-gray-50 -my-1">` + M.log.map((e) =>
          `<div class="py-2 flex items-start gap-2 text-xs"><span class="${C.mono} text-gray-400">${esc(e.ts)}</span>` +
          `<span class="flex-1 text-gray-700">${esc(e.text)}</span>` +
          `<span class="text-gray-400">${esc(e.actor)}</span></div>`).join('') + '</div>');
  }

  /* ══ 공정 탭 ══════════════════════════════════════════════ */
  /** 서브 탭 = v_control_menu(공정) + 반송 자원.
   *  반송은 STATION 이 아니라 v_control_menu 에 안 들어온다 — 별도 항목으로 붙인다. */
  const menuRows = () =>
    L.menu(M).concat(window.WF_ROBOT ? window.WF_ROBOT.menuRow() : []);

  function renderMenu() {
    const rows = menuRows();
    if (!S.menu || !rows.some((r) => r.menu_label === S.menu)) S.menu = rows[0] ? rows[0].menu_label : null;
    $('wf-ct-menu').innerHTML = rows.map((r) =>
      `<button data-ctl-menu="${esc(r.menu_label)}" class="py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
        r.menu_label === S.menu ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
      }">${esc(r.menu_label)}<span class="ml-1.5 text-xs text-gray-400">${r.node_count}</span></button>`).join('');
    return rows.find((r) => r.menu_label === S.menu) || null;
  }

  function renderNodeBar(entry) {
    if (!entry) { $('wf-ct-nodebar').innerHTML = ''; S.node = null; return; }
    const ids = entry.node_ids;
    if (!S.node || ids.indexOf(S.node) < 0) { S.node = ids[0]; S.rack = null; S.slot = null; S.open = null; }
    const name = (id) => {
      const n = L.node(M, id);
      return n ? n.label : (window.WF_ROBOT ? window.WF_ROBOT.labelOf(id) : id);
    };
    $('wf-ct-nodebar').innerHTML =
      `<span class="${C.label}">${esc(entry.menu_label)}</span>` +
      (entry.ui_kind === 'MONITOR'
        ? `<span class="${C.pill} ${TONE.idle}">설비 ${ids.length}대 · 한 화면</span>`
        : ids.length > 1
        ? ids.map((id) => `<button data-ctl-node="${esc(id)}" class="${C.pill} ${
            id === S.node ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}">${esc(name(id))}</button>`).join('')
        : `<span class="${C.pill} ${TONE.idle}">${esc(name(ids[0]))}</span>`);
  }

  /* ══ 화면 A — BATCH_SPLIT (부품 분리) ═════════════════════ */
  function screenBatchSplit(nodeId) {
    const racks = L.prevRacks(M, nodeId);
    if (S.rack === null && racks.length) S.rack = racks[0].node_id;
    const slots = S.rack ? L.slotsOf(M, S.rack) : [];
    if (S.slot !== null && !slots.some((s) => s.slot_no === S.slot && s.used > 0)) S.slot = null;
    const q = (S.rack && S.slot !== null) ? L.queueOf(M, S.rack, S.slot) : [];
    if (S.open && !q.some((b) => b.unit_id === S.open)) S.open = null;
    if (!S.open) { const f = q.find((b) => b.retrievable); if (f) S.open = f.unit_id; }

    /* 1·2 — 랙 / 칸 */
    let left = step(1, '랙 선택');
    if (!racks.length) left += `<p class="${C.hint}">직전 공정 랙이 없습니다.</p>`;
    else if (racks.length === 1) {
      const ld = L.rackLoad(M, racks[0].node_id);
      left += `<div class="${C.row} border-dashed"><p class="font-medium text-gray-900 text-sm">${esc(racks[0].label)}</p>` +
        `<p class="${C.hint} mt-0.5">적재 ${ld.used}/${ld.capacity} · 칸 ${ld.slots}개 · 자동 선택</p></div>`;
    } else {
      left += '<div class="space-y-2">' + racks.map((r) => {
        const ld = L.rackLoad(M, r.node_id);
        return `<button data-rack="${esc(r.node_id)}" class="${C.row} w-full text-left ${r.node_id === S.rack ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}">` +
          `<p class="font-medium text-gray-900 text-sm">${esc(r.label)}</p>` +
          `<p class="${C.hint} mt-0.5">적재 ${ld.used}/${ld.capacity} · 칸 ${ld.slots}개</p></button>`;
      }).join('') + '</div>';
    }
    left += '<div class="mt-5">' + step(2, '칸 선택', `${slots.length}칸`) + '<div class="space-y-2">' +
      slots.map((s) => `<button data-slot="${s.slot_no}"${s.used ? '' : ' disabled'} class="${C.row} w-full text-left ${
        s.slot_no === S.slot ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'} ${s.used ? '' : 'opacity-50 cursor-not-allowed'}">` +
        `<p class="font-medium text-gray-900 text-sm">칸 ${s.slot_no} · ${s.used}/${s.capacity}</p>` +
        `<p class="${C.hint} mt-0.5 truncate">${s.used ? esc(s.contents.join(' → ')) : '비어 있음'}</p></button>`).join('') +
      '</div></div>';

    /* 3 — 배치 대기열 */
    let main = step(3, '배치 대기열', S.slot === null ? '' : `칸 ${S.slot} · ${q.length}장 · FIFO`);
    main += S.slot === null ? `<p class="${C.hint} py-4">칸을 고르세요.</p>` :
      '<div class="space-y-2">' + q.map((b) =>
        `<button data-batch="${esc(b.unit_id)}"${b.retrievable ? '' : ' disabled'} class="${C.row} w-full text-left flex items-center gap-3 ${
          b.unit_id === S.open ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'} ${b.retrievable ? '' : 'opacity-50 cursor-not-allowed'}">` +
        `<span class="${C.num} ${b.retrievable ? '' : 'bg-gray-100 text-gray-400'}">${b.pos_no}</span>` +
        `<span class="flex-1 min-w-0"><span class="block font-medium text-gray-900 text-sm">${esc(b.display_id)}</span>` +
        `<span class="flex flex-wrap items-center gap-1 mt-1">` +
        `<span class="${C.pill} bg-gray-900 text-white">${b.contents.length}종</span>` +
        b.contents.map((c) => `<span class="${C.pill} bg-gray-100 text-gray-600 ${C.mono}">${esc(c.part_no)} ×${c.qty}</span>`).join('') +
        '</span></span>' +
        `<span class="text-right"><span class="block text-sm font-semibold text-gray-900">${b.total_qty}개</span>` +
        `<span class="${C.hint}">${b.retrievable ? '지금 작업' : '앞 배치 먼저'}</span></span></button>`).join('') + '</div>';

    /* 4 — 파트별 판정 */
    const lock = L.interlockOk(M, nodeId);
    main += '<div class="mt-6">';
    if (S.open) {
      const b = M.units.find((x) => x.unit_id === S.open);
      const rows = L.judgeRows(M, b, S.judge[b.unit_id]);
      const t = L.totals(rows), can = L.canComplete(rows, lock);
      const un = L.untouched(rows, S.judge[b.unit_id]);
      const bad = L.badRows(rows);
      main += step(4, '파트별 판정 · 배치 완료', `${esc(b.display_id)} · 총 ${t.qty}개`);
      if (!lock) main += `<div class="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">인터록 미충족 — 판정 입력이 잠겨 있습니다.</div>`;
      main += `<button id="wf-allok" class="${C.btn} mb-3"${lock && un.kinds ? '' : ' disabled'}>` +
        (un.kinds ? `남은 ${un.kinds}종 전체 OK (${un.qty}개)` : '전부 입력됨') + '</button>';
      main += `<div class="space-y-2 ${lock ? '' : 'opacity-40 pointer-events-none'}">` + rows.map((r, i) => {
        const mismatch = (+r.ok || 0) + (+r.ng || 0) !== r.qty;
        return `<div class="${C.row} ${mismatch ? 'border-red-300' : 'border-gray-200'}">` +
          '<div class="flex items-center gap-3">' +
          `<div class="flex-1 min-w-0"><p class="${C.mono} font-semibold text-gray-900">${esc(r.part_no)}</p>` +
          `<p class="${C.hint}">${esc(r.name)} · 투입 ${r.qty}개${mismatch ? ' · <span class="text-red-600 font-medium">합계 불일치</span>' : ''}</p></div>` +
          `<div class="w-20"><p class="${C.hint} mb-0.5 text-center">OK</p>` +
          `<input type="number" min="0" max="${r.qty}" value="${+r.ok || 0}" data-j="${i}" data-f="ok" class="${C.input} ${mismatch ? 'border-red-300' : ''}"></div>` +
          `<div class="w-20"><p class="${C.hint} mb-0.5 text-center">NG</p>` +
          `<input type="number" min="0" max="${r.qty}" value="${+r.ng || 0}" data-j="${i}" data-f="ng" class="${C.input} ${mismatch ? 'border-red-300' : ''} ${+r.ng ? 'text-red-600 font-semibold' : ''}"></div>` +
          '</div>' +
          (+r.ng > 0 ? '<div class="flex items-center gap-2 mt-2 pt-2 border-t border-dashed border-gray-200">' +
            `<span class="text-xs font-medium text-red-600">NG ${+r.ng}개 사유</span>` +
            `<select data-j="${i}" data-f="reason" class="px-2 py-1 rounded-lg border border-gray-200 text-xs">` +
            '<option value="">- 선택 -</option>' +
            M.NG_REASONS.map((x) => `<option${r.reason === x ? ' selected' : ''}>${esc(x)}</option>`).join('') +
            '</select>' + (r.reason ? '' : `<span class="${C.hint}">사유를 골라야 완료할 수 있습니다</span>`) + '</div>' : '') +
          '</div>';
      }).join('') + '</div>';
      if (bad.length) main += `<div class="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700 mt-3">` +
        bad.map((r) => esc(r.part_no) + ' — ' + ((+r.ok || 0) + (+r.ng || 0) !== r.qty
          ? `OK ${+r.ok || 0} + NG ${+r.ng || 0} = ${(+r.ok || 0) + (+r.ng || 0)} (투입 ${r.qty})` : 'NG 사유 미선택')).join('<br>') + '</div>';
      main += '<div class="flex items-center gap-3 mt-4">' +
        `<span class="${C.label} flex-1">합계 <b class="text-gray-900">OK ${t.ok}</b> · <b class="text-gray-900">NG ${t.ng}</b> / 총 ${t.qty}개</span>` +
        `<button id="wf-done" class="${C.btnPri}"${can ? '' : ' disabled'}>배치 완료 등록</button></div>`;
    } else {
      main += step(4, '파트별 판정 · 배치 완료') + `<p class="${C.hint} py-4">대기열에서 배치를 고르세요.</p>`;
    }
    main += '</div>';

    /* 5 — 묶음 넘기기 */
    const groups = L.groups(M, nodeId);
    const nexts = L.nextNodes(M, nodeId).filter((n) => n.node_kind === 'STATION');
    const target = L.groupTarget(M, nodeId);
    let side = step(5, '분리 완료 · 넘기기') +
      (groups.length ? groups.map((g) => {
        const srcs = L.groupSources(M, nodeId, g.group_id);
        const open = g.group_id === S.openGroup;
        const full = target > 0 && g.units.length >= target;
        return card(`묶음 ${esc(g.group_id)}`, pill(`${g.units.length}${target ? ' / ' + target : ''}`, full ? 'warn' : 'run'),
          srcs.map((sc) => `<div class="flex items-baseline gap-2 text-xs py-1 border-b border-dashed border-gray-100 last:border-0">` +
            `<span class="${C.mono} font-semibold text-gray-900">${esc(sc.display_id)}</span>` +
            `<span class="text-gray-500">${Object.keys(sc.parts).map((pn) => esc(pn) + ' ' + sc.parts[pn] + '개').join(' · ')}</span></div>`).join('') +
          (open ? `<div class="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700">누적 중${
            target ? ` · 남은 자리 ${Math.max(0, target - g.units.length)}개` : ''}</div>` +
            `<button id="wf-newgroup" class="${C.btn} w-full">새 묶음으로 시작</button>` : '') +
          (full ? `<div class="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">정원 ${target}개가 찼습니다.</div>` : '') +
          nexts.map((nx) => `<button data-handoff="${esc(g.group_id)}" data-to="${esc(nx.node_id)}" class="${C.btnPri} w-full">묶음 마감 · ${esc(nx.label)}로 넘기기</button>`).join(''),
          'mb-3');
      }).join('') : `<p class="${C.hint}">배치를 완료하면 부품이 묶음으로 쌓입니다.</p>`);

    return layout(left, main, sidePanel(nodeId, side));
  }

  /* ══ 화면 B — PART_JUDGE (서포트 제거 · 치수검사) ═════════ */
  function screenPartJudge(nodeId) {
    const parts = L.waitingParts(M, nodeId);
    const spec = L.measureSpec(M, nodeId);
    const lock = L.interlockOk(M, nodeId);
    const boxRack = L.nextNodes(M, nodeId).filter((n) => n.node_kind === 'RACK' && n.count_by_group)[0] || null;
    const groups = L.groups(M, nodeId);

    let left = step(1, '대기 묶음') +
      (groups.length ? '<div class="space-y-2">' + groups.map((g) =>
        `<div class="${C.row} border-blue-500 ring-1 ring-blue-500"><p class="${C.mono} font-semibold text-gray-900">${esc(g.group_id)}</p>` +
        `<p class="${C.hint} mt-0.5">${g.units.length}개 대기</p></div>`).join('') + '</div>'
        : `<p class="${C.hint}">대기 중인 부품이 없습니다.</p>`);

    const decided = parts.filter((p) => L.latestVerdict(M, p.unit_id)).length;
    let main = step(2, '부품별 판정', `대기 ${parts.length}개 · 판정 ${decided}개`);
    if (!lock) main += '<div class="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">인터록 미충족 — 판정 입력이 잠겨 있습니다.</div>';
    main += `<button id="wf-allok-part" class="${C.btn} mb-3"${lock && parts.length ? '' : ' disabled'}>일괄 · 남은 부품 전체 OK</button>`;

    if (!parts.length) main += empty('판정할 부품이 없습니다.');
    else {
      main += `<div class="${C.card} ${lock ? '' : 'opacity-40 pointer-events-none'}"><table class="w-full text-sm">` +
        '<thead class="bg-gray-50 text-gray-500"><tr>' +
        '<th class="px-3 py-2 text-left font-medium w-10">#</th>' +
        '<th class="px-3 py-2 text-left font-medium">부품</th>' +
        '<th class="px-3 py-2 text-left font-medium">파트넘버</th>' +
        (spec ? `<th class="px-3 py-2 text-left font-medium w-32">${esc(spec.label)} (${esc(spec.unit)})</th>` : '') +
        '<th class="px-3 py-2 text-left font-medium w-32">판정</th></tr></thead><tbody class="divide-y divide-gray-100">' +
        parts.map((p, i) => {
          const v = L.latestVerdict(M, p.unit_id);
          const mv = S.measure[p.unit_id];
          const tol = L.inTolerance(mv, p.attrs);
          return '<tr class="hover:bg-gray-50">' +
            `<td class="px-3 py-2 ${C.mono} text-gray-400">${String(i + 1).padStart(2, '0')}</td>` +
            `<td class="px-3 py-2 ${C.mono} font-semibold text-gray-900">${esc(p.display_id)}</td>` +
            `<td class="px-3 py-2 text-gray-700">${esc(p.part_no)}<span class="${C.hint} ml-1">${esc(p.part_name)}</span></td>` +
            (spec ? `<td class="px-3 py-2"><input type="number" step="0.01" data-meas="${esc(p.unit_id)}" value="${mv == null ? '' : mv}" placeholder="${p.attrs.nominal_mm == null ? '' : p.attrs.nominal_mm}" class="${C.input} ${tol === false ? 'border-red-400 text-red-600' : ''}">` +
              (p.attrs.tol_mm != null ? `<span class="${C.hint} ml-1">±${p.attrs.tol_mm}</span>` : '') + '</td>' : '') +
            '<td class="px-3 py-2"><div class="flex gap-1">' +
            `<button data-v="OK" data-u="${esc(p.unit_id)}" class="px-2.5 py-1 rounded-lg text-xs font-medium border ${
              v && v.verdict === 'OK' ? 'bg-green-600 border-green-600 text-white' : 'border-gray-200 text-gray-500 hover:bg-gray-100'}">OK</button>` +
            `<button data-v="NG" data-u="${esc(p.unit_id)}" class="px-2.5 py-1 rounded-lg text-xs font-medium border ${
              v && v.verdict === 'NG' ? 'bg-red-600 border-red-600 text-white' : 'border-gray-200 text-gray-500 hover:bg-gray-100'}">NG</button>` +
            '</div></td></tr>';
        }).join('') + '</tbody></table></div>';
    }

    let side = step(3, '다음 공정');
    if (boxRack) {
      const box = L.openBox(M, boxRack.node_id);
      const cap = L.groupCapacity(boxRack), n = box.items.length;
      side += card(`박스 적재 → ${esc(boxRack.label)}`, pill(`${n} / ${cap}`, n >= cap ? 'ok' : 'run'),
        `<p class="${C.hint}">OK 판정한 부품이 담깁니다. ${cap}개가 차면 자동 마감.</p>` +
        bar(Math.round((n / cap) * 100)) +
        `<p class="text-sm text-gray-700">${n ? esc(box.group_id) + ' · ' + n + '개' : '비어 있음'}</p>` +
        `<button id="wf-closebox" class="${C.btn} w-full"${n ? '' : ' disabled'}>박스 수동 마감</button>`, 'mb-3');
    }
    return layout(left, main, sidePanel(nodeId, side));
  }

  /* ══ 화면 C — MONITOR (프린터·세척기·경화기·빔피킹) ═══════ */
  function screenMonitor(_nodeId, entry) {
    const ids = (entry && entry.node_ids.length ? entry.node_ids : [_nodeId]).filter(Boolean);
    const groups = [];
    ids.map((id) => L.node(M, id)).filter(Boolean).forEach((n) => {
      const g = n.group_label || n.label;
      let row = groups.find((x) => x.label === g);
      if (!row) groups.push(row = { label: g, nodes: [] });
      row.nodes.push(n);
    });

    const queue = [];
    ids.forEach((id) => L.inbound(M, id).forEach((r) => { if (!queue.some((x) => x.key === r.key)) queue.push(r); }));
    if (!queue.some((r) => r.key === S.pick && r.ready)) { const f = queue.find((r) => r.ready); S.pick = f ? f.key : null; }

    let left = step(1, '투입 대기 큐', `${queue.length}건`) +
      (queue.length ? '<div class="space-y-2">' + queue.map((r, i) =>
        `<button data-pick="${esc(r.key)}"${r.ready ? '' : ' disabled'} class="${C.row} w-full text-left flex items-center gap-3 ${
          r.key === S.pick ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'} ${r.ready ? '' : 'opacity-50 cursor-not-allowed'}">` +
        `<span class="${C.num} ${r.ready ? '' : 'bg-gray-100 text-gray-400'}">${i + 1}</span>` +
        `<span class="flex-1 min-w-0"><span class="block font-medium text-gray-900 text-sm truncate">${esc(r.label)}</span>` +
        `<span class="${C.hint}">${r.qty}개 · ${esc(r.from)}${r.ready ? '' : ' · 앞의 것 먼저'}</span></span></button>`).join('') + '</div>'
        : `<p class="${C.hint}">들어올 것이 없습니다.</p>`) +
      `<div class="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700 mt-3">FIFO · 출처마다 앞의 것부터</div>`;

    const block = (n) => {
      const here = L.at(M, n.node_id);
      const q = L.inbound(M, n.node_id);
      const pick = q.find((r) => r.key === S.pick && r.ready) || q.find((r) => r.ready) || null;
      const u = here[0] || null;
      const pct = L.progress(M, n);
      const inbQty = q.reduce((a, r) => a + r.qty, 0);
      return `<div class="${C.card} ${u && u.status === 'RUN' ? 'bg-blue-50' : ''}">` +
        `<div class="px-4 py-3 border-b ${u && u.status === 'RUN' ? 'bg-white/50' : 'bg-gray-50'} flex items-center justify-between gap-2">` +
        `<span class="font-semibold text-gray-900 text-sm truncate">${esc(n.label)}</span>${badgeOf(n.node_id)}</div>` +
        '<div class="px-4 py-3 space-y-2">' +
        `<p class="text-sm text-gray-700 min-h-10">` +
        (u ? `<b class="${C.mono}">${here.length > 1 ? here.length + '개' : esc(u.display_id)}</b> · ` +
             `${esc(here.length > 1 ? L.occupancy(M, n) + '개 적재' : L.mixOf(u))}<br>` +
             `<span class="${C.hint}">경과 ${L.fmt(u.elapsed_s)}${u.plan_s ? ' / 설정 ' + L.fmt(u.plan_s) : ' / 표준 ' + L.fmt(n.std_cycle_s)}</span>`
           : `<span class="text-gray-400">비어 있음 · 표준 ${L.fmt(n.std_cycle_s)}</span>`) + '</p>' +
        bar(pct == null ? 0 : pct) +
        `<div class="flex items-center justify-between ${C.hint}"><span>대기 큐 ${q.length}건${inbQty ? ' · ' + inbQty + '개' : ''}</span>` +
        `<span>${pick && !u ? '다음 ' + esc(pick.label) : (q.length ? '왼쪽에서 선택' : '없음')}</span></div>` +
        (u ? '<div class="grid grid-cols-3 gap-1.5 pt-1">' + L.CMD.map((c) =>
              `<button data-cmd="${c.key}" data-n="${esc(n.node_id)}" class="${c.key === 'stop' ? C.btnDanger : C.btnPri} !px-2 !py-1.5 text-xs"${
                L.canCmd(M, n.node_id, c.key) ? '' : ' disabled'}>${c.label}</button>`).join('') + '</div>'
           : `<button data-load="${esc(n.node_id)}" class="${C.btnPri} w-full !py-1.5 text-xs"${pick ? '' : ' disabled'}>` +
             `${pick ? esc(pick.label) + ' 투입' : '투입할 것 없음'}</button>`) +
        '</div></div>';
    };

    const running = ids.filter((id) => (L.at(M, id)[0] || {}).status === 'RUN').length;
    const main = step(2, '설비 상태 · 명령', `설비 ${ids.length}대 · 가동 ${running}대`) +
      groups.map((g) =>
        `<div class="mb-5"><p class="${C.label} mb-2">${esc(g.label)} <span class="text-gray-400">${g.nodes.length}대</span></p>` +
        `<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${g.nodes.map(block).join('')}</div></div>`).join('');

    return layout(left, main, sidePanel(ids[0], ''));
  }

  const layout = (left, main, side) =>
    '<div class="grid grid-cols-1 lg:grid-cols-12 gap-4">' +
    `<div class="lg:col-span-3 space-y-3">${left}</div>` +
    `<div class="lg:col-span-6">${main}</div>` +
    `<div class="lg:col-span-3 space-y-3">${side}</div></div>`;

  const SCREENS = {
    BATCH_SPLIT: screenBatchSplit, PART_JUDGE: screenPartJudge, MONITOR: screenMonitor,
    // 🔴 기존 「자동화 수동제어」와 다르다 — IP·청크를 타이핑하지 않고 동작 명령만 고른다.
    TRANSPORT: (nodeId) => window.WF_ROBOT ? window.WF_ROBOT.screen(nodeId) : empty('로봇암 화면이 없습니다.'),
  };

  function render() {
    const entry = renderMenu();
    renderNodeBar(entry);
    if (!entry) { $('wf-ct-screen').innerHTML = empty('제어할 설비가 없습니다.'); return; }
    const fn = SCREENS[entry.ui_kind];
    $('wf-ct-screen').innerHTML = fn
      ? `<div data-screen="${esc(entry.ui_kind)}" data-node="${esc(S.node || '')}">${fn(S.node, entry)}</div>`
      : empty(`이 화면 종류(${entry.ui_kind})는 아직 없습니다.`);
  }

  /* ══ 조작 ═════════════════════════════════════════════════ */
  const root = $('wf-panel-control');

  root.addEventListener('click', (e) => {
    const t = e.target;
    const hit = (sel) => t.closest(sel);
    let el;
    if ((el = hit('[data-ctl-menu]'))) { S.menu = el.dataset.ctlMenu; S.node = S.rack = S.slot = S.open = null; return render(); }
    if ((el = hit('[data-ctl-node]'))) { S.node = el.dataset.ctlNode; S.rack = S.slot = S.open = null; return render(); }
    if ((el = hit('[data-rack]'))) { S.rack = el.dataset.rack; S.slot = S.open = null; return render(); }
    if ((el = hit('[data-slot]'))) { S.slot = +el.dataset.slot; S.open = null; return render(); }
    if ((el = hit('[data-batch]'))) { S.open = el.dataset.batch; return render(); }
    if (t.id === 'wf-allok') {
      const b = M.units.find((x) => x.unit_id === S.open);
      const saved = S.judge[b.unit_id] = S.judge[b.unit_id] || {};
      L.untouched(L.judgeRows(M, b, saved), saved).parts.forEach((r) => { saved[r.part_no] = { ok: r.qty, ng: 0, reason: '' }; });
      return render();
    }
    if (t.id === 'wf-done') return askSplit();
    if (t.id === 'wf-newgroup') { S.openGroup = null; log('BOX_CLOSE', '새 묶음으로 전환'); return render(); }
    if ((el = hit('[data-handoff]'))) return askHandoff(el.dataset.handoff, el.dataset.to);
    if ((el = hit('[data-v]'))) return onVerdict(el.dataset.u, el.dataset.v);
    if (t.id === 'wf-allok-part') {
      L.waitingParts(M, S.node).forEach((p) => {
        if (!L.latestVerdict(M, p.unit_id)) L.judge(M, p.unit_id, S.node, 'OK', measureValue(p), null);
      });
      log('JUDGE', '남은 부품 전체 OK');
      return render();
    }
    if (t.id === 'wf-closebox') return askCloseBox();
    if ((el = hit('[data-pick]'))) { S.pick = el.dataset.pick; return render(); }
    if ((el = hit('[data-load]'))) return askLoad(el.dataset.load);
    if ((el = hit('[data-cmd]')) && el.dataset.n) return askCmd(el.dataset.n, el.dataset.cmd);
    // ── 로봇암 수동제어 ──
    if ((el = hit('[data-arm]'))) { window.WF_ROBOT.setArm(el.dataset.arm); S.node = el.dataset.arm; return render(); }
    if ((el = hit('[data-cmd]'))) { window.WF_ROBOT.pick(el.dataset.cmd); return render(); }
    if (t.id === 'wf-rb-run') return askRobot();
  });

  root.addEventListener('change', (e) => {
    const t = e.target;
    const lk = t.closest('[data-lock]');
    if (lk) {
      const it = L.interlockOf(M, S.node).find((i) => i.key === lk.dataset.lock);
      if (it) it.ok = lk.checked;
      return render();
    }
    const ms = t.closest('[data-meas]');
    if (ms) { S.measure[ms.dataset.meas] = ms.value === '' ? null : +ms.value; return render(); }
    const j = t.closest('[data-j]');
    if (!j) return;
    const b = M.units.find((x) => x.unit_id === S.open);
    const rows = L.judgeRows(M, b, S.judge[b.unit_id]);
    const r = rows[+j.dataset.j], f = j.dataset.f;
    if (f === 'reason') r.reason = j.value;
    else {
      const v = Math.max(0, Math.min(r.qty, +j.value || 0));
      r[f] = v;
      if (f === 'ng') { r.ok = r.qty - v; if (!v) r.reason = ''; }
    }
    S.judge[b.unit_id] = S.judge[b.unit_id] || {};
    S.judge[b.unit_id][r.part_no] = { ok: r.ok, ng: r.ng, reason: r.reason };
    render();
  });

  $('wf-dlg-no').onclick = closeDlg;
  $('wf-dlg-yes').onclick = () => { const f = onYes, body = $('wf-dlg-c'); closeDlg(); if (f) f(body); };

  /** 로봇 실동작이므로 확인을 거친다. 다이얼로그가 "보낼 값"을 그대로 다시 보여준다 —
   *  작업자가 타이핑하지 않았으니 최소한 눈으로는 확인하게 한다. */
  function askRobot() {
    const R = window.WF_ROBOT, c = R && R.current();
    if (!c) return;
    confirmBox(`${c.label} — 로봇암`,
      `<b>${esc(c.risk)}</b>` +
      `<div class="mt-2"><p class="${C.hint} mb-1">보낼 값</p>` +
      `<div class="rounded-lg bg-gray-900 text-gray-100 px-3 py-2 ${C.mono} break-all">${esc(R.chunkOf(c))}</div></div>` +
      `<p class="${C.hint} mt-2">설비가 실제로 움직입니다.</p>`,
      '실행', () => { R.run(); render(); }, true);
  }

  function measureValue(p) {
    const spec = L.measureSpec(M, S.node);
    if (!spec) return null;
    const v = S.measure[p.unit_id];
    return v == null ? null : { [spec.key]: v, tol: p.attrs.tol_mm, nominal: p.attrs.nominal_mm };
  }

  function onVerdict(unitId, verdict) {
    const p = L.waitingParts(M, S.node).find((x) => x.unit_id === unitId);
    if (!p) return;
    if (verdict === 'NG') {
      return confirmBox(`NG 판정 — ${p.display_id}`,
        `<b>${esc(p.display_id)} 을(를) 폐기 처리합니다.</b><br><span class="${C.hint}">라인에서 폐기됩니다.</span>`,
        'NG 확정', () => {
          L.judge(M, unitId, S.node, 'NG', measureValue(p), null);
          L.scrapPart(M, unitId, S.node, '판정 NG');
          log('JUDGE', `${p.display_id} NG · 폐기`);
          render();
        }, true);
    }
    L.judge(M, unitId, S.node, 'OK', measureValue(p), null);
    log('JUDGE', `${p.display_id} OK`);
    render();
  }

  function askSplit() {
    const b = M.units.find((x) => x.unit_id === S.open);
    const rows = L.judgeRows(M, b, S.judge[b.unit_id]);
    const t = L.totals(rows);
    const target = L.groupTarget(M, S.node);
    const fits = S.openGroup && (!target || L.groupCount(M, S.node, S.openGroup) + t.ok <= target);
    confirmBox(`배치 완료 등록 — ${b.display_id}`,
      `<b>OK ${t.ok}개가 부품으로 등록됩니다.${t.ng ? ` NG ${t.ng}개는 폐기 처리됩니다.` : ''}</b>` +
      '<div class="mt-2 space-y-0.5">' + rows.map((r) =>
        `<div class="text-sm"><b class="${C.mono}">${esc(r.part_no)}</b> OK ${+r.ok || 0} / NG ${+r.ng || 0}` +
        (+r.ng ? ` <span class="text-red-600">(${esc(r.reason)})</span>` : '') + '</div>').join('') + '</div>' +
      `<p class="${C.hint} mt-2">부품이 ${esc(b.display_id)}-S... 로 생성돼 ` +
      (fits ? `묶음 <b>${esc(S.openGroup)}</b> 에 이어 담깁니다` : '<b>새 묶음</b>에 담깁니다') + '. 되돌릴 수 없습니다.</p>',
      '배치 완료', () => {
        let gid = S.openGroup;
        if (gid && target && L.groupCount(M, S.node, gid) + t.ok > target) gid = null;
        const r = L.splitBatch(M, b, rows, S.node, gid);
        S.openGroup = r.group_id;
        if (target && L.groupCount(M, S.node, r.group_id) >= target) S.openGroup = null;
        delete S.judge[b.unit_id]; S.open = null;
        log('JUDGE', `${b.display_id} 분리 완료 (OK ${r.ok}${r.ng ? ' / NG ' + r.ng : ''}) → ${r.group_id}`);
        render();
      });
  }

  function askHandoff(groupId, toNodeId) {
    const to = L.node(M, toNodeId);
    const g = L.groups(M, S.node).find((x) => x.group_id === groupId);
    confirmBox(`다음 단계로 넘기기 — ${to.label}`,
      `<b>${esc(groupId)} (${g.units.length}개) 를 ${esc(to.label)} 로 넘깁니다.</b>`,
      '넘기기', () => {
        const r = L.moveGroup(M, groupId, S.node, toNodeId);
        if (S.openGroup === groupId) S.openGroup = null;
        log('MOVED', `${groupId} → ${to.label} (${r.count}개)`);
        render();
      });
  }

  function askLoad(nodeId) {
    const n = L.node(M, nodeId);
    const q = L.inbound(M, nodeId);
    const row = q.find((r) => r.key === S.pick && r.ready) || q.find((r) => r.ready);
    if (!n || !row) return;
    confirmBox(`투입 — ${n.label}`,
      `<b>${esc(row.label)} (${row.qty}개) 를 ${esc(n.label)} 에 넣습니다.</b><br>` +
      `<span class="${C.hint}">${esc(row.from)} 에서 옵니다.</span>`,
      '투입', () => {
        const r = L.loadInto(M, nodeId, row.key);
        if (r) { S.pick = null; log('MOVED', `${r.label} → ${n.label} 투입 (${r.count}개)`); }
        render();
      });
  }

  function askCmd(nodeId, key) {
    const n = L.node(M, nodeId), c = L.cmdOf(key), here = L.at(M, nodeId), u = here[0];
    if (!n || !c || !u) return;
    const spec = key === 'start' ? L.durationSpec(M, nodeId) : null;
    confirmBox(`${c.label} — ${n.label}`,
      `<b>${esc(n.label)} 에 ${c.label} 명령을 보냅니다.</b><br>` +
      `<span class="${C.hint}">${esc(here.length > 1 ? here.length + '개 적재분' : u.display_id)} · ${esc(u.status)} → ${c.to}</span>` +
      (spec ? `<div class="mt-3"><p class="${C.hint} mb-1">${esc(spec.label)} · 표준 ${spec.default}${esc(spec.unit)}</p>` +
        `<div class="flex items-center gap-2"><input id="wf-run-min" type="number" min="1" step="1" value="${spec.default}" class="${C.input} !w-24 !text-left">` +
        `<span class="${C.hint}">${esc(spec.unit)}</span></div></div>` : ''),
      c.label, (body) => {
        const el = spec && body.querySelector('#wf-run-min');
        const ev = L.runCmd(M, nodeId, key, el ? el.value : null);
        if (!ev) { log('CMD', `${n.label} ${c.label} 실패 — 가동 시간을 정해야 합니다`); return render(); }
        log('CMD', `${n.label} ${c.label}${ev.plan_s && key === 'start' ? ' ' + L.fmt(ev.plan_s) : ''} (${ev.from} → ${ev.to})`);
        render();
      }, key === 'stop');
  }

  const boxRackId = (nodeId) => {
    const r = L.nextNodes(M, nodeId).filter((n) => n.node_kind === 'RACK' && n.count_by_group)[0];
    return r ? r.node_id : null;
  };

  function askCloseBox() {
    const rackId = boxRackId(S.node);
    const box = L.openBox(M, rackId);
    confirmBox(`박스 수동 마감 — ${box.group_id}`,
      `<b>${esc(box.group_id)} 를 ${box.items.length}개로 마감합니다.</b><br>` +
      `<span class="${C.hint}">미달 상태로 다음 공정에 보냅니다.</span>`,
      '마감', () => {
        const c = L.closeBox(M, rackId);
        if (c) log('BOX_CLOSE', `${c.group_id} 수동 마감 (${c.items.length}개)`);
        render();
      });
  }

  /* 판정 OK 가 박스로 가는 노드에서는 OK 즉시 박스에 담는다 (와이어프레임과 동일) */
  const _judge = L.judge;
  L.judge = function (m, unitId, nodeId, verdict, value, note) {
    const rec = _judge(m, unitId, nodeId, verdict, value, note);
    if (verdict === 'OK') {
      const boxRack = L.nextNodes(m, nodeId).filter((n) => n.node_kind === 'RACK' && n.count_by_group)[0];
      if (boxRack) {
        L.joinBox(m, unitId, boxRack.node_id);
        if (L.openBox(m, boxRack.node_id).items.length >= L.groupCapacity(boxRack)) {
          const c = L.closeBox(m, boxRack.node_id);
          if (c) log('BOX_CLOSE', `${c.group_id} 자동 마감 (${c.items.length}개)`);
        }
      }
    }
    return rec;
  };

  window.WF_CONTROL = { render, S };
  render();
})();
