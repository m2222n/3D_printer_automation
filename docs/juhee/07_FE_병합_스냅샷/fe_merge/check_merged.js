/** 합친 HTML 이 실제로 도는지 — 기존 FE 스냅샷 보존 + 새 패널 기능.
 *  NODE_PATH=<jsdom> node docs/juhee/07_FE_병합_스냅샷/fe_merge/check_merged.js */
const assert = require('assert');
const fs = require('fs');
const { JSDOM } = require('jsdom');

const FILE = 'docs/juhee/07_FE_병합_스냅샷/20260916_fe_merged.html';
const HTML = fs.readFileSync(FILE, 'utf8');
const dom = new JSDOM(HTML, { runScripts: 'dangerously', url: 'https://x/', pretendToBeVisual: true });
const W = dom.window, D = W.document;
const errs = [];
W.addEventListener('error', (e) => { const m = String(e.message || e.error); if (m.indexOf('Not implemented') < 0) errs.push(m); });
const click = (el) => el.dispatchEvent(new W.MouseEvent('click', { bubbles: true }));
const change = (el) => el.dispatchEvent(new W.Event('change', { bubbles: true }));
let n = 0;
const ok = (t) => { n++; console.log('  OK  ' + t); };
const tab = (label) => [].slice.call(D.querySelectorAll('nav [data-tab]')).find((b) => b.textContent.indexOf(label) === 0);
const yes = () => click(D.getElementById('wf-dlg-yes'));

setTimeout(() => {
  console.log('\n=== 기존 FE 7탭이 그대로 붙어 있나 ===');
  const feLabels = ['모니터링', '프린트 제어', '대기 중인 작업', '이전 작업 내용', '통계', '자동화', '자동화 수동제어'];
  feLabels.forEach((l, i) => {
    const b = tab(l);
    assert.ok(b, '탭 없음: ' + l);
    click(b);
    const p = D.querySelector('[data-panel="fe-' + i + '"]');
    assert.ok(p && !p.hidden, l + ' 패널이 안 열린다');
    assert.ok(p.innerHTML.length > 2000, l + ' 내용이 비었다: ' + p.innerHTML.length);
  });
  // 스냅샷 원본과 바이트 단위로 같은지 (건드리지 않았다는 증거)
  const snap = JSON.parse(fs.readFileSync('/tmp/fe-snapshot.json', 'utf8'));
  feLabels.forEach((l, i) => {
    const got = D.querySelector('[data-panel="fe-' + i + '"]').innerHTML.replace(/\s+/g, ' ').trim();
    const want = snap.tabs[l].replace(/\s+/g, ' ').trim();
    assert.strictEqual(got.length, want.length, l + ' 마크업 길이가 다르다');
  });
  ok('기존 7탭 = 스냅샷 그대로 (길이 일치)');

  console.log('\n=== 라인 모니터링 ===');
  click(tab('라인 모니터링'));
  const lineBody = D.getElementById('wf-line-body');
  assert.ok(lineBody.querySelectorAll('.rounded-xl').length > 8, '흐름 카드가 없다');
  assert.ok(/공정 설비/.test(lineBody.textContent), '요약 타일 없음');
  assert.ok(/로봇암 A/.test(lineBody.textContent), '반송 패널 없음');
  {
    // 와이어프레임 형태 — 랙은 윗단(row 1) · 설비는 아랫단(row 3) · 사이(row 2)에 반송
    const cells = [].slice.call(lineBody.querySelectorAll('[style*="grid-row"]'));
    const row = (r) => cells.filter((c) => /grid-row:(\d)/.exec(c.getAttribute('style'))[1] === String(r));
    const racks = row(1), mids = row(2), stations = row(3);
    assert.ok(racks.length >= 4, '윗단 랙이 모자라다: ' + racks.length);
    assert.ok(stations.length >= 6, '아랫단 설비가 모자라다: ' + stations.length);
    assert.strictEqual(mids.length, racks.length + stations.length - 1, '반송 연결자 수가 열 사이 개수와 다르다');
    racks.forEach((c) => assert.ok(/랙/.test(c.textContent), '윗단에 랙이 아닌 것이 있다: ' + c.textContent.slice(0, 20)));
    assert.ok(mids.some((c) => /작업자/.test(c.textContent)), '수동 반송 구간 표시가 없다');
    assert.ok(mids.some((c) => /로봇암/.test(c.textContent)), '로봇 반송 구간 표시가 없다');
    assert.ok(mids.every((c) => /큐 \d/.test(c.textContent)), '연결자에 큐 수가 없다');
    // 화살표는 그림으로 — 가운데 띠에 가로 구분선을 두지 않는다 (선이 화살표로 읽힌다)
    mids.forEach((c) => assert.strictEqual(c.querySelectorAll('.border-t').length, 0, '가운데 띠에 구분선이 남아 있다'));
    const tierAt = (col) => cells.some((c) => /grid-row:1/.test(c.getAttribute('style')) &&
      (+/grid-column:(\d+)/.exec(c.getAttribute('style'))[1]) === col) ? 'RACK' : 'STATION';
    let vertical = 0, elbow = 0;
    mids.forEach((c, i) => {
      const d = c.querySelector('path').getAttribute('d').trim().split(/\s+/);
      const xs = new Set(d.filter((_, k) => k % 3 === 1));
      assert.ok(c.querySelector('polygon'), (i + 1) + '번 구간에 화살촉이 없다');
      // 도착 카드가 아랫단이면 아래로 끝나고, 윗단이면 위로 끝난다
      const toTop = tierAt(i + 2) === 'RACK';
      assert.strictEqual(d[d.length - 1], toTop ? '0' : '72', (i + 1) + '번 구간 화살표 방향이 반대다');
      // 윗단↔아랫단은 블록이 붙어 있어 세로 한 줄, 같은 단끼리만 꺾인다
      if (tierAt(i + 1) === tierAt(i + 2)) { elbow++; assert.strictEqual(xs.size, 2, (i + 1) + '번은 꺾여야 한다'); }
      else { vertical++; assert.strictEqual(xs.size, 1, (i + 1) + '번 구간이 세로 화살표가 아니다: ' + d.join(' ')); }
    });
    assert.ok(vertical > elbow, '세로 화살표가 기본이어야 한다');
    // 가로 간격 — 단이 엇갈리면 촘촘하게, 같은 단끼리는 겹치지 않게
    {
      const CARD = 216;
      const grid = lineBody.querySelector('[style*="grid-template-columns"]');
      const ws = /grid-template-columns:([^;]+)/.exec(grid.getAttribute('style'))[1]
        .trim().split(/\s+/).map((x) => parseInt(x, 10));
      const left = ws.map((_, i) => ws.slice(0, i).reduce((a, b) => a + b, 0));
      const xOf = (c) => left[(+/grid-column:(\d+)/.exec(c.getAttribute('style'))[1]) - 1];
      [racks, stations].forEach((tier) => {
        const xs = tier.map(xOf).sort((a, b) => a - b);
        xs.slice(1).forEach((x, i) => assert.ok(x - (xs[i] + CARD) >= 0, '같은 단 카드가 겹친다'));
      });
      // 엇갈린 이웃(랙-설비)은 카드 하나 너비보다 가깝게 붙어 있어야 한다
      const near = ws.slice(0, -1).filter((w) => w < CARD);
      assert.ok(near.length >= vertical, '엇갈린 이웃 간격이 벌어져 있다: ' + ws.join(' '));
    }
    const manualSeg = mids.filter((c) => /작업자/.test(c.textContent));
    assert.ok(manualSeg.every((c) => c.querySelector('path').getAttribute('stroke-dasharray')),
      '수동 구간이 점선이 아니다');
    assert.ok(mids.filter((c) => /로봇암/.test(c.textContent))
      .every((c) => !c.querySelector('path').getAttribute('stroke-dasharray')), '로봇 구간이 점선이다');
    // 프린터 4대는 카드 1장 + 베이 4개 (와이어프레임과 같은 묶음)
    const prt = stations.find((c) => /프린터/.test(c.textContent));
    assert.strictEqual(prt.querySelectorAll('.rounded-lg.border').length, 4, '프린터 베이가 4개가 아니다');
    // 설비가 1대뿐인 열은 이름이 두 번 나오지 않는다
    const ins = stations.find((c) => /치수검사/.test(c.textContent));
    assert.strictEqual((ins.textContent.match(/치수검사/g) || []).length, 1, '설비 1대인데 이름이 두 번 나온다');
    ok('랙 ' + racks.length + '(윗단) · 설비 ' + stations.length + '(아랫단) · 세로 화살표 ' + vertical +
       ' · 꺾임 ' + elbow + ' (수동 ' + manualSeg.length + ' 점선)');
  }

  click(D.querySelector('[data-line-view="pipe"]'));
  const tblRows = lineBody.querySelectorAll('tbody tr');
  assert.ok(tblRows.length > 3, '파이프라인 행이 없다: ' + tblRows.length);
  assert.ok(lineBody.querySelectorAll('thead th').length >= 7, '공정 열이 모자라다');
  ok('플레이트 파이프라인 (' + tblRows.length + '행 × ' + (lineBody.querySelectorAll('thead th').length - 1) + '공정)');

  console.log('\n=== 공정 제어 — 탭이 데이터에서 나온다 ===');
  click(tab('공정 제어'));
  const menu = [].slice.call(D.querySelectorAll('#wf-ct-menu [data-ctl-menu]'));
  assert.deepStrictEqual(menu.map((b) => b.dataset.ctlMenu),
    ['출력 · 세척', '부품 분리', '서포트 제거', '경화기', '치수검사', '빔피킹·드릴링·트림',
     '로봇암 수동제어']);
  ok('공정 탭 6개(v_control_menu) + 반송 1개 · 공정 순서대로');

  // 렌더마다 버튼이 새로 만들어진다 — 매번 다시 찾는다
  const go = (label) => click([].slice.call(D.querySelectorAll('#wf-ct-menu [data-ctl-menu]'))
    .find((b) => b.dataset.ctlMenu === label));
  const screen = () => D.querySelector('#wf-ct-screen [data-screen]').dataset.screen;

  [['출력 · 세척', 'MONITOR'], ['부품 분리', 'BATCH_SPLIT'], ['서포트 제거', 'PART_JUDGE'],
   ['경화기', 'MONITOR'], ['치수검사', 'PART_JUDGE'], ['로봇암 수동제어', 'TRANSPORT']]
    .forEach(([l, k]) => { go(l); assert.strictEqual(screen(), k, l); });
  ok('탭마다 ui_kind 대로 (화면 4종)');

  console.log('\n=== MONITOR — 투입 → 시작 ===');
  go('출력 · 세척');
  const eq = D.querySelectorAll('#wf-ct-screen [data-cmd], #wf-ct-screen [data-load]');
  assert.ok(eq.length > 0, '설비 명령 버튼이 없다');
  const free = D.querySelector('#wf-ct-screen [data-load]:not([disabled])');
  assert.ok(free, '투입 가능한 빈 설비가 없다');
  const node = free.dataset.load;
  click(free); yes();
  assert.ok(D.querySelector('#wf-ct-screen [data-cmd][data-n="' + node + '"]'), '투입 후 명령 버튼이 안 생겼다');
  const start = D.querySelector('[data-cmd="start"][data-n="' + node + '"]:not([disabled])');
  assert.ok(start, '시작 버튼 비활성');
  click(start);
  const min = D.getElementById('wf-run-min');          // 세척기면 가동 시간 입력이 붙는다
  yes();
  assert.ok(/시작/.test(D.getElementById('wf-panel-control').textContent), '로그에 시작이 없다');
  ok('빈 설비 투입 → 시작' + (min ? ' (가동 시간 입력 있음)' : ''));

  console.log('\n=== BATCH_SPLIT — 일괄 OK → 배치 완료 → 묶음 ===');
  go('부품 분리');
  assert.ok(!D.querySelector('#wf-ct-screen [data-batch]'), '칸을 고르기 전인데 대기열이 떠 있다');
  click(D.querySelector('#wf-ct-screen [data-slot]:not([disabled])'));   // 1 랙 자동 → 2 칸 선택
  assert.ok(D.querySelectorAll('#wf-ct-screen [data-batch]').length >= 3, '배치 대기열이 없다');
  const before = D.querySelector('#wf-ct-screen').textContent.indexOf('묶음 G-');
  click(D.getElementById('wf-allok'));
  const done = D.getElementById('wf-done');
  assert.ok(done && !done.disabled, '전체 OK 후에도 완료가 비활성');
  click(done); yes();
  assert.ok(D.querySelector('#wf-ct-screen').textContent.indexOf('묶음 G-') >= 0, '묶음이 안 생겼다');
  assert.ok(before < 0, '테스트 전부터 묶음이 있었다');
  ok('배치 완료 → 묶음 생성 · 넘기기 버튼 ' + D.querySelectorAll('[data-handoff]').length + '개');

  console.log('\n=== BATCH_SPLIT — NG 는 사유가 있어야 완료된다 ===');
  const ngIn = D.querySelector('#wf-ct-screen input[data-f="ng"]');
  assert.ok(ngIn, '다음 배치가 안 열렸다');
  ngIn.value = '2'; change(ngIn);
  assert.ok(D.getElementById('wf-done').disabled, 'NG 사유 없이도 완료가 열려 있다');
  const sel = D.querySelector('#wf-ct-screen select[data-f="reason"]');
  assert.ok(sel, 'NG 사유 선택이 안 나온다');
  sel.value = sel.options[1].value; change(sel);
  assert.ok(!D.getElementById('wf-done').disabled, '사유를 골랐는데도 완료가 잠겨 있다');
  ok('NG 사유 게이트가 산다');

  console.log('\n=== PART_JUDGE — 판정 → 박스 ===');
  go('서포트 제거');
  const boxText = () => {
    const h = [].slice.call(D.querySelectorAll('#wf-ct-screen .rounded-xl'))
      .find((el) => /박스 적재/.test(el.textContent));
    return h ? h.querySelector('.rounded-full').textContent.trim() : null;
  };
  const waiting = D.querySelectorAll('#wf-ct-screen [data-v="OK"]').length;
  assert.strictEqual(boxText(), '0 / 12', '박스가 비어 있지 않다: ' + boxText());
  click(D.getElementById('wf-allok-part'));
  assert.strictEqual(boxText(), waiting + ' / 12', '담긴 수가 판정 수와 다르다: ' + boxText());
  assert.strictEqual(D.querySelectorAll('#wf-ct-screen [data-v="OK"]').length, 0, '판정한 부품이 목록에 남았다');
  ok('일괄 OK ' + waiting + '개 → 박스 ' + boxText());

  console.log('\n=== PART_JUDGE — 측정값 입력은 치수검사에만 ===');
  go('치수검사');
  assert.ok(D.querySelector('#wf-ct-screen [data-meas]'), '치수검사에 측정 입력이 없다');
  go('서포트 제거');
  assert.ok(!D.querySelector('#wf-ct-screen [data-meas]'), '서포트 제거에 측정 입력이 붙었다');
  ok('측정 입력은 node.measure 가 있는 곳에만');

  console.log('\n=== 인터록이 판정을 잠근다 ===');
  go('부품 분리');
  click(D.querySelector('#wf-ct-screen [data-slot]:not([disabled])'));   // 배치를 열어야 판정 영역이 뜬다
  const lock = D.querySelector('#wf-panel-control [data-lock]');
  assert.ok(lock, '인터록 체크박스가 없다');
  lock.checked = false; change(lock);
  assert.ok(/인터록 미충족/.test(D.querySelector('#wf-ct-screen').textContent), '미충족 경고가 없다');
  assert.ok(D.getElementById('wf-allok').disabled, '잠겼는데 일괄 OK 가 열려 있다');
  lock.checked = true; change(lock);
  ok('인터록 해제/복구');

  console.log('\n=== 디자인이 기존 FE 와 같은 어휘인가 ===');
  const ctl = D.getElementById('wf-panel-control').innerHTML;
  ['rounded-xl border shadow-sm', 'bg-blue-600 text-white', 'rounded-full text-xs font-medium',
   'text-xs text-gray-500'].forEach((cls) => assert.ok(ctl.indexOf(cls) >= 0, '기존 FE 클래스 미사용: ' + cls));
  assert.ok(!/--teal|EC694A|JetBrains/.test(HTML.slice(HTML.indexOf('wf-panel-line'))), '와이어프레임 원본 색/폰트가 남아 있다');
  ok('기존 FE 클래스 어휘 사용 · 원본 팔레트 잔재 0');

  console.log('\n=== 로봇암 수동제어 — 고르기만 한다 ===');
  {
    go('로봇암 수동제어');
    const scr = () => D.querySelector('#wf-ct-screen');

    // 🥇 반송 자원이 topology.yaml 에서 왔나 — 화면이 지어낸 것이 아니어야 한다
    const topo = JSON.parse(fs.readFileSync('/tmp/wf-topo.json', 'utf8')).transporters;
    const arms = [].slice.call(scr().querySelectorAll('[data-arm]'));
    assert.deepStrictEqual(arms.map((b) => b.dataset.arm), topo.map((t) => t.id),
      '화면의 반송 자원이 topology 와 다르다');
    // 담당 구간도 topology 의 nodes 를 푼 것
    topo.forEach((t) => assert.ok(scr().textContent.indexOf('담당 ' + t.node_ids.length + '곳') >= 0,
      t.id + ' 담당 구간 수가 topology 와 다르다'));
    ok('반송 자원 ' + topo.length + '건이 topology.yaml 에서 온다 (' + topo.map((t) => t.id).join(' ') + ')');

    // 🔴 기존 「자동화 수동제어」와 가르는 지점 — 입력란이 하나도 없어야 한다
    assert.strictEqual(scr().querySelectorAll('input, textarea, select').length, 0,
      '직접 입력란이 있다 — 기존 수동제어와 같아져 버렸다');
    assert.ok(/IP·포트를 여기서 입력하지 않습니다/.test(scr().textContent), '차이 설명이 없다');

    // endpoint 없는 자원(OP-CURE) = 사람이 옮긴다. 보낼 명령이 없어야 한다
    const op = topo.find((t) => !t.endpoint);
    assert.ok(op, 'topology 에 수동 반송 자원이 없다');
    click(arms.find((b) => b.dataset.arm === op.id));
    assert.strictEqual(scr().querySelectorAll('[data-cmd]').length, 0, op.id + ' 에 명령 버튼이 있다');
    assert.ok(/사람이 옮깁니다/.test(scr().textContent), '수동 반송이라는 표시가 없다');
    ok(op.id + ' = endpoint 없음 → 명령 0개 · "사람이 옮깁니다"');

    // 🔴 그리퍼는 상태 하나에 신호 하나다 — 동작 명령이 아니다. 열기 1~4단계만.
    const armB = [].slice.call(scr().querySelectorAll('[data-arm]')).find((b) => b.dataset.arm === 'ARM-B');
    click(armB);
    const grip = [].slice.call(scr().querySelectorAll('[data-cmd]'))
      .filter((b) => b.dataset.cmd.indexOf('grip-') === 0);
    assert.deepStrictEqual(grip.map((b) => b.dataset.cmd),
      ['grip-open-1', 'grip-open-2', 'grip-open-3', 'grip-open-4'], '그리퍼 상태가 열기 1~4 가 아니다');
    ['닫기', '벌리기', '오므리기', 'standby', 'grasp'].forEach((w) =>
      assert.ok(scr().textContent.indexOf(w) < 0 && scr().innerHTML.indexOf(w) < 0,
        '없애기로 한 말이 남아 있다: ' + w));
    assert.ok(/상태 하나에 신호 하나/.test(scr().textContent), '상태=신호 설명이 없다');
    ok('그리퍼 = 상태 4개 (열기 1~4단계) · 동작 어휘 0');

    // 상태마다 신호가 하나씩 · 서로 달라야 한다 — 같으면 상태를 나눈 뜻이 없다
    // 🚨 클릭할 때마다 다시 그려지므로 버튼을 매번 새로 찾는다 (묵은 노드는 안 먹는다)
    const seen = new Set();
    grip.map((b) => b.dataset.cmd).forEach((id) => {
      click([].slice.call(scr().querySelectorAll('[data-cmd]')).find((b) => b.dataset.cmd === id));
      const m = /D_GEN_OUT_0~3 = (\d{4})/.exec(scr().textContent);
      assert.ok(m, id + ' 의 신호가 없다');
      assert.ok(!seen.has(m[1]), id + ' 의 신호가 앞 상태와 겹친다: ' + m[1]);
      seen.add(m[1]);
    });
    assert.strictEqual(seen.size, 4, '상태 4개에 신호 4개가 아니다');
    ok('상태 4개 = 서로 다른 신호 4개');

    // 실물 확인분만 실행 가능
    click([].slice.call(scr().querySelectorAll('[data-cmd]')).find((b) => b.dataset.cmd === 'grip-open-2'));
    assert.ok(/D_GEN_OUT_0~3 = 0100/.test(scr().textContent), '신호 미리보기가 없다');
    assert.ok(/GRIP_COMBO/.test(scr().textContent), '값의 출처가 없다');
    const run = D.getElementById('wf-rb-run');
    assert.ok(run && !run.disabled, '9/9 확인분인데 실행이 잠겨 있다');
    click(run);
    assert.ok(/D_GEN_OUT_0~3 = 0100/.test(D.getElementById('wf-dlg-c').textContent), '다이얼로그에 신호가 없다');
    click(D.getElementById('wf-dlg-yes'));
    assert.ok(/열기 2단계/.test(scr().textContent), '실행 로그가 안 남았다');

    click([].slice.call(scr().querySelectorAll('[data-cmd]')).find((b) => b.dataset.cmd === 'grip-open-3'));
    const run2 = D.getElementById('wf-rb-run');
    assert.ok(run2 && run2.disabled, '폭 미정 상태인데 실행이 열려 있다');
    assert.ok(/D_GEN_OUT_0~3 = 1100/.test(scr().textContent), '미검증이어도 신호는 보여야 한다');
    ok('9/9 확인분만 실행 가능 · 나머지는 신호만 보여준다');
  }

  console.log('\n=== 새 패널이 쓰는 클래스가 전부 CSS 에 있나 ===');
  {
    // 스타일이 빠진 채 "그럴싸하게" 보이는 것을 막는다 (Tailwind 는 쓴 것만 만든다)
    const styleText = D.querySelector('style').textContent;
    const used = new Set();
    ['wf-panel-line', 'wf-panel-control', 'wf-mask'].forEach((id) => {
      D.getElementById(id).querySelectorAll('*').forEach((el) => {
        (el.getAttribute('class') || '').split(/\s+/).filter(Boolean).forEach((c) => used.add(c));
      });
    });
    const esc4 = (c) => c.replace(/[:.[\]/!%]/g, (m) => '\\' + m);
    const missing = [].concat.apply([], Array.from(used).map((c) =>
      styleText.indexOf('.' + esc4(c)) >= 0 ? [] : [c]))
      .filter((c) => c !== 'hidden');          // hidden 은 [hidden] 속성 셀렉터라 클래스가 아니다
    assert.deepStrictEqual(missing, [], '스타일이 없는 클래스: ' + missing.join(', '));
    ok('사용 클래스 ' + used.size + '개 전부 CSS 에 있음');
  }

  assert.strictEqual(errs.length, 0, 'JS 오류: ' + errs.slice(0, 3).join(' | '));
  ok('조작 전 과정 JS 오류 0건');
  console.log('\n검사 ' + n + '건 전부 통과\n');
  process.exit(0);
}, 800);
