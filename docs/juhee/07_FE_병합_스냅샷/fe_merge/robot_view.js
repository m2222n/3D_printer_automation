/* ══════════════════════════════════════════════════════════════
   공정 제어 › 로봇암 수동제어 (TRANSPORT)

   🔴 기존 「자동화 수동제어」와 무엇이 다른가
     기존  IP·포트를 타이핑하고 Modbus 주소·값을 직접 넣어 Write
           (AutomationManualPage.tsx:367 'Robot IP' · :404 'Address'/'Value')
     여기  동작 명령만 고른다. 어디에 무엇을 쓰는지는 매핑이 안다.

   🚨 반송 자원은 화면이 지어내지 않는다 — topology.yaml 의 transporters 에서 온다
      (build 때 topo_extract.py 가 추출 · 신규 API 에서는 v_transporter_load 가 준다).
      담당 구간도 nodes 를 groups 로 푼 결과다. 로봇을 늘리면 카드가 는다.

   🚨 명령 목록도 마찬가지다 — 아래 CATALOG 가 그 자리이고 줄을 더하면 버튼이 늘어난다.
   ══════════════════════════════════════════════════════════════ */
(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const TOPO = (window.WF_TOPO && window.WF_TOPO.transporters) || [];

  /* ── 명령 카탈로그는 화면에 없다 ───────────────────────
     topology.yaml 의 transporters[].attrs.commands 가 정본이고 build 때 실려 온다.
     (신규 API 에서는 R11 이 transporter.attrs 에서 같은 것을 준다)
     🚨 여기에 명령을 적으면 자원이 늘 때 화면 코드를 고쳐야 한다 — 그래서 안 적는다.

     그리퍼는 상태 하나에 신호 하나다. "열어라 / 닫아라" 같은 동작 명령이 아니라
     상태마다 D_GEN_OUT_0~3 의 4비트 조합이 하나씩 붙어 있고 고르는 것은 갈 상태다.
     🔴 벌림 폭(span_mm)은 2단계만 9/9 실측이고 나머지는 임의값 — 실측하면 YAML 만 고친다. */

  const C = {
    card: 'bg-white rounded-xl border shadow-sm overflow-hidden',
    hint: 'text-xs text-gray-500', mono: 'font-mono text-xs',
    pill: 'px-2.5 py-1 rounded-full text-xs font-medium',
    btnPri: 'px-3 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors',
    num: 'flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold',
  };
  const step = (n, t, note) =>
    `<div class="flex items-center gap-2 mb-2"><span class="${C.num}">${n}</span>` +
    `<span class="font-semibold text-gray-900 text-sm">${t}</span>` +
    (note ? `<span class="${C.hint} ml-auto">${note}</span>` : '') + '</div>';

  function chunkOf(cmd) {
    const s = cmd.send;
    if (s.kind === 'DO') {
      return s.bits.length > 1 ? `${s.ch} = ${s.bits.join('')}  (${s.pulse_s}s 펄스 → 전부 0)`
                               : `${s.ch} = ${s.bits[0]}`;
    }
    if (s.kind === 'MODBUS') {
      return `reg ${s.reg} ← ${s.value}` + (s.then ? `,  reg ${s.then.reg} ← ${s.then.value}` : '');
    }
    return `TCP :${s.port}  "${s.msg}"`;
  }
  const KIND_LABEL = { DO: '디지털 출력', MODBUS: 'Modbus 레지스터', SOCKET: '펜던트 소켓' };
  // 그리퍼는 폭이 곧 힌트다. 실측 전에는 임의값이므로 그렇다고 적는다.
  const hintOf = (c) => c.span_mm != null
    ? `약 ${c.span_mm}mm` + (c.verified ? '' : ' (임의값)')
    : (c.hint || '');

  const S = { arm: null, picked: null, log: [] };
  const arms = () => TOPO;
  const cur = () => arms().find((a) => a.id === S.arm) || arms()[0] || null;
  const cmdsOf = (id) => (arms().find((a) => a.id === id) || {}).commands || [];
  const picked = () => { const a = cur(); return a ? cmdsOf(a.id).find((c) => c.id === S.picked) || null : null; };
  const manual = (a) => !a.endpoint;        // endpoint 없음 = 수동 반송. 명령을 보낼 수 없다

  function log(text) {
    const d = new Date();
    S.log.unshift({ ts: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`, text });
    S.log = S.log.slice(0, 8);
  }

  function render() {
    if (!arms().length) return '<div class="py-10 text-center text-gray-400 text-sm">토폴로지에 반송 자원이 없습니다.</div>';
    const arm = cur(), cmd = picked();

    /* 1 — 반송 자원. 담당 구간은 topology 의 nodes 를 푼 것이다 */
    let left = step(1, '반송 자원', `${arms().length}건`) + '<div class="space-y-2">' + arms().map((a) => {
      const off = manual(a);
      return `<button data-arm="${esc(a.id)}" class="bg-white rounded-lg border p-3 w-full text-left transition-all hover:shadow-sm ${
        a.id === (arm && arm.id) ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}">` +
      `<div class="flex items-center gap-2"><span class="font-medium text-gray-900 text-sm">${esc(a.label)}</span>` +
      `<span class="${C.pill} ${off ? 'bg-gray-100 text-gray-600' : 'bg-green-50 text-green-700'} ml-auto">` +
      `${off ? '수동' : esc(a.endpoint.protocol)}</span></div>` +
      `<p class="${C.hint} mt-1">${esc(a.kind)} · 담당 ${a.node_ids.length}곳</p>` +
      `<p class="${C.hint} mt-0.5 truncate">${esc(a.node_labels.join(' · '))}</p></button>`;
    }).join('') + '</div>';

    left += `<div class="mt-4">` + step(2, '담당 구간') +
      `<div class="${C.card} px-3 py-2.5">` +
      `<div class="flex flex-wrap gap-1">` + arm.node_labels.map((l) =>
        `<span class="${C.pill} bg-gray-100 text-gray-600">${esc(l)}</span>`).join('') + '</div>' +
      `<p class="${C.hint} mt-2">topology.yaml <span class="${C.mono}">transporters.nodes</span> 에서 옵니다</p></div>` +
      `<div class="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700 mt-2">` +
      `IP·포트를 여기서 입력하지 않습니다. 접속 대상은 설비 설정에 있고, 이 화면은 <b>무엇을 시킬지</b>만 고릅니다.</div></div>`;

    /* 3 — 동작 명령 */
    let main = step(3, '동작 명령', `${cmdsOf(arm.id).length}개`);
    if (manual(arm)) {
      main += `<div class="rounded-lg bg-amber-50 border border-amber-200 px-4 py-6 text-sm text-amber-800 text-center">` +
        `<b>${esc(arm.label)} 은 사람이 옮깁니다.</b><br>` +
        `<span class="text-xs">topology 에 <span class="${C.mono}">endpoint</span> 가 없어 보낼 명령이 없습니다. ` +
        `반송 대기는 라인 모니터링에서 봅니다.</span></div>`;
    } else if (!cmdsOf(arm.id).length) {
      main += `<div class="${C.card} px-4 py-6 text-center ${C.hint}">이 자원에 등록된 명령이 없습니다.</div>`;
    } else {
      const groups = [];
      cmdsOf(arm.id).forEach((c) => {
        let g = groups.find((x) => x.name === c.group);
        if (!g) groups.push(g = { name: c.group, items: [] });
        g.items.push(c);
      });
      main += groups.map((g) =>
        `<div class="mb-4"><p class="${C.hint} mb-2">${esc(g.name)}</p>` +
        `<div class="grid grid-cols-2 sm:grid-cols-3 gap-2">` + g.items.map((c) =>
          `<button data-cmd="${esc(c.id)}" class="bg-white rounded-lg border p-2.5 text-left transition-all hover:shadow-sm ${
            c.id === S.picked ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}">` +
          `<div class="flex items-center gap-1.5"><span class="font-medium text-gray-900 text-sm truncate">${esc(c.label)}</span>` +
          (c.verified ? '' : `<span class="${C.pill} bg-amber-50 text-amber-700 flex-shrink-0">미검증</span>`) +
          `</div><p class="${C.hint} mt-0.5">${esc(hintOf(c))}</p></button>`).join('') +
        '</div></div>').join('');
      main += `<div class="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 space-y-1">` +
        `<p><b>미검증</b> = 실물로 확인되지 않은 명령입니다. 눌러도 나가지 않고, 무엇을 보낼지만 보여줍니다.</p>` +
        `<p><b>폭 미정</b> = 그 상태가 몇 mm 인지 아직 topology 에 없습니다. 신호는 정해져 있고 폭만 모릅니다.</p>` +
        `<p><b>그리퍼</b>는 상태 하나에 신호 하나입니다 — 여는 동작을 지시하는 것이 아니라 <b>갈 상태</b>를 고릅니다.</p></div>`;
    }

    /* 4 — 보낼 것 */
    let side = step(4, '보낼 것');
    if (!cmd) {
      side += `<div class="${C.card} px-4 py-8 text-center ${C.hint}">` +
        (manual(arm) ? '수동 반송이라 보낼 것이 없습니다.' : '명령을 고르면 무엇이 나가는지 여기 보입니다.') + '</div>';
    } else {
      side += `<div class="${C.card}">` +
        `<div class="px-4 py-3 border-b bg-gray-50 flex items-center gap-2">` +
        `<span class="font-semibold text-gray-900 text-sm">${esc(cmd.label)}</span>` +
        `<span class="${C.pill} bg-gray-100 text-gray-600 ml-auto">${esc(KIND_LABEL[cmd.send.kind])}</span></div>` +
        `<div class="px-4 py-3 space-y-3">` +
        `<div><p class="${C.hint} mb-1">보낼 값</p>` +
        `<div class="rounded-lg bg-gray-900 text-gray-100 px-3 py-2 ${C.mono} break-all">${esc(chunkOf(cmd))}</div></div>` +
        `<div><p class="${C.hint} mb-1">이 값의 출처</p><p class="text-xs text-gray-700">${esc(cmd.source)}</p></div>` +
        `<div><p class="${C.hint} mb-1">누르면 일어나는 일</p>` +
        `<p class="text-sm ${cmd.verified ? 'text-gray-900' : 'text-amber-700'}">${esc(cmd.risk)}</p></div>` +
        `<button id="wf-rb-run" class="${C.btnPri} w-full"${cmd.verified ? '' : ' disabled'}>` +
        `${cmd.verified ? '실행' : '미검증 — 실행할 수 없음'}</button></div></div>`;
    }

    side += `<div class="mt-3">` + step(5, '실행 로그') + `<div class="${C.card} px-4 py-2">` +
      (S.log.length
        ? '<div class="divide-y divide-gray-50 -my-1">' + S.log.map((e) =>
            `<div class="py-2 flex items-start gap-2 text-xs"><span class="${C.mono} text-gray-400">${esc(e.ts)}</span>` +
            `<span class="flex-1 text-gray-700">${esc(e.text)}</span></div>`).join('') + '</div>'
        : `<p class="${C.hint} py-3">아직 없습니다.</p>`) + '</div></div>';

    return '<div class="grid grid-cols-1 lg:grid-cols-12 gap-4">' +
      `<div class="lg:col-span-3 space-y-3">${left}</div>` +
      `<div class="lg:col-span-6">${main}</div>` +
      `<div class="lg:col-span-3 space-y-3">${side}</div></div>`;
  }

  window.WF_ROBOT = {
    menuRow: () => arms().length
      ? [{ menu_label: '로봇암 수동제어', ui_kind: 'TRANSPORT', step_order: 999,
           node_count: arms().length, node_ids: arms().map((a) => a.id) }] : [],
    labelOf: (id) => (arms().find((a) => a.id === id) || {}).label || id,
    screen: (nodeId) => { if (nodeId && arms().some((a) => a.id === nodeId)) S.arm = nodeId; return render(); },
    pick: (id) => { S.picked = id; },
    setArm: (id) => { S.arm = id; S.picked = null; },
    current: picked, chunkOf,
    run: () => {
      const c = picked(); if (!c || !c.verified) return null;
      log(`${WF_ROBOT.labelOf(S.arm)} · ${c.label} → ${chunkOf(c)}`);
      return c;
    },
  };
})();
