/**
 * 제어 화면 수락 기준 C1~C9 검증.
 * 빌드된 wireframe_pages.html 에서 로직 스크립트를 꺼내 실제로 돌린다.
 *   node docs/juhee/06_와이어프레임_HTML/check_control.js
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const HTML = fs.readFileSync(path.resolve(process.cwd(), 'docs/juhee/06_와이어프레임_HTML/wireframe_pages.html'), 'utf8');

const st = HTML.indexOf('id="page-control"');
assert.ok(st > 0, '제어 페이지가 없다');
const nx = HTML.indexOf('<section class="page"', st);
const PAGE = HTML.slice(st, nx > 0 ? nx : HTML.length);

const logicSrc = /<script data-ctl-logic>([\s\S]*?)<\/script>/.exec(PAGE);
assert.ok(logicSrc, '로직 스크립트를 못 찾았다');
const viewSrc = /<script data-ctl-view>([\s\S]*?)<\/script>/.exec(PAGE)[1];

function load() {
  const mod = { exports: {} };
  new Function('module', 'exports', logicSrc[1])(mod, mod.exports);
  return mod.exports;
}
let n = 0;
const ok = (t) => { n++; console.log('  OK  ' + t); };

console.log('\n=== C1 · 2차 서포트제거 노드 추가 -> 탭이 늘고 PART_JUDGE 가 열린다 ===');
{
  const { MOCK: M, L } = load();
  const before = L.menu(M);
  const sup = before.find(r => r.menu_label === '서포트 제거');
  assert.strictEqual(sup.node_count, 1, '기준선 1대');
  assert.strictEqual(sup.ui_kind, 'PART_JUDGE');

  // 목업에 줄 하나. 화면 코드는 건드리지 않는다.
  M.nodes.push({ node_id: 'SUP-02', node_kind: 'STATION', node_type: 'SUPPORT_REMOVAL',
    ui_kind: 'PART_JUDGE', group_label: '서포트 제거', label: '서포트 제거대 2',
    capacity: 16, std_cycle_s: 480 });
  M.routes.push({ from: 'SEP-01', to: 'SUP-02', kind: 'MAIN' },
                { from: 'SUP-02', to: 'CUR-01', kind: 'MAIN' });

  const after = L.menu(M).find(r => r.menu_label === '서포트 제거');
  assert.strictEqual(after.node_count, 2, '탭 뱃지가 2로');
  assert.deepStrictEqual(after.node_ids, ['SUP-01', 'SUP-02'], '노드 선택지가 2개');
  assert.strictEqual(after.ui_kind, 'PART_JUDGE', '같은 화면 종류');
  assert.strictEqual(L.menu(M).length, before.length, '탭 개수는 그대로 (같은 group_label 로 묶임)');

  // 새 group_label 이면 탭 자체가 하나 늘어난다
  M.nodes.push({ node_id: 'FDM-01', node_kind: 'STATION', node_type: 'FDM_PRINTER',
    ui_kind: 'MONITOR', group_label: 'FDM 프린터', label: 'FDM 1호기', capacity: 1, std_cycle_s: 7200 });
  M.routes.push({ from: 'RK-PRE-PRT-01', to: 'FDM-01', kind: 'MAIN' });
  assert.strictEqual(L.menu(M).length, before.length + 1, '새 공정이면 탭이 생긴다');
  ok('노드 추가 -> 뱃지 2 · 새 공정 -> 탭 +1 (화면 코드 수정 0줄)');
}

console.log('\n=== C2 · 경화기를 3대로 -> 코드 수정 0줄 ===');
{
  const { MOCK: M, L } = load();
  const cur = () => L.menu(M).find(r => r.menu_label === '경화기');
  assert.strictEqual(cur().node_count, 2, '기준선 2대');
  // 서포트제거는 경화 대기 랙까지만 보낸다. 경화기는 그 랙에서 가져간다.
  assert.deepStrictEqual(L.nextNodes(M, 'SUP-01').map(x => x.node_id), ['RK-CUR-WAIT-01'],
    '서포트제거 다음은 랙 하나');
  const next = L.nextNodes(M, 'RK-CUR-WAIT-01').filter(x => x.node_kind === 'STATION');
  assert.strictEqual(next.length, 2, '랙에서 가져가는 경화기 2대');

  M.nodes.push({ node_id: 'CUR-03', node_kind: 'STATION', node_type: 'CURER', ui_kind: 'MONITOR',
    group_label: '경화기', label: '경화기 3호기', capacity: 12, std_cycle_s: 1800 });
  M.routes.push({ from: 'RK-CUR-WAIT-01', to: 'CUR-03', kind: 'MAIN' },
                { from: 'CUR-03', to: 'INS-01', kind: 'MAIN' });
  assert.strictEqual(cur().node_count, 3, '탭 뱃지 3');
  assert.strictEqual(L.nextNodes(M, 'RK-CUR-WAIT-01').filter(x => x.node_kind === 'STATION').length, 3,
    '랙에서 가져가는 경화기도 3대');
  // 용량이 다른 경화기가 오면 묶음 정원도 따라간다
  const small = { node_id: 'CUR-04', node_kind: 'STATION', node_type: 'CURER', ui_kind: 'MONITOR',
    group_label: '경화기', label: '경화기 4호기', capacity: 6, std_cycle_s: 1800 };
  assert.strictEqual(L.groupCapacity(small), 6, '묶음 정원은 목적지 용량에서 파생');
  ok('경화기 3대 · 투입 후보 3대 · 정원 파생');
}

console.log('\n=== C3 · 칸에 배치 3장 -> FIFO 순서, 1번만 열림 ===');
{
  const { MOCK: M, L } = load();
  const q = L.queueOf(M, 'RK-WSH-DONE-01', 1);
  assert.strictEqual(q.length, 3);
  assert.deepStrictEqual(q.map(b => b.display_id), ['P9-W9', 'P10-W10', 'P8-W8']);
  assert.deepStrictEqual(q.map(b => b.pos_no), [1, 2, 3]);
  assert.deepStrictEqual(q.map(b => b.retrievable), [true, false, false]);
  assert.deepStrictEqual(q.map(b => b.contents.length), [3, 1, 2], '혼재가 기본 · 단일은 예외 하나');
  ok('P9-W9(3종) -> P10-W10(1종) -> P8-W8(2종) · 1번만 retrievable');
}

console.log('\n=== C4 · 1번 배치 완료 -> 2번이 1번이 되고 열린다 ===');
{
  const { MOCK: M, L } = load();
  const b = L.queueOf(M, 'RK-WSH-DONE-01', 1)[0];
  L.splitBatch(M, b, L.judgeRows(M, b), 'SEP-01');
  const q = L.queueOf(M, 'RK-WSH-DONE-01', 1);
  assert.strictEqual(q.length, 2);
  assert.strictEqual(q[0].display_id, 'P10-W10');
  assert.strictEqual(q[0].pos_no, 1, '뒤가 한 칸 당겨진다');
  assert.strictEqual(q[0].retrievable, true);
  assert.strictEqual(q[1].retrievable, false);
  ok('P10-W10 이 1번으로 올라와 열린다');
}

console.log('\n=== C5 · 혼재 배치 -> 파트넘버당 1줄, 수량만큼 펼치지 않는다 ===');
{
  const { MOCK: M, L } = load();
  const two = L.judgeRows(M, M.units.find(x => x.display_id === 'P8-W8'));
  assert.strictEqual(two.length, 2);
  assert.deepStrictEqual(two.map(r => r.qty), [8, 4]);
  assert.deepStrictEqual(two.map(r => r.ok), [8, 4], '기본 전부 OK');
  assert.strictEqual(L.totals(two).qty, 12);
  assert.ok(two.length < L.totals(two).qty, '수량만큼 행을 만들지 않는다');
  ok('2종 12개 -> 2줄');
}

console.log('\n=== C6 · NG 1개 -> 사유 필요 · 확인 문구 OK 11 / NG 1 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P8-W8');
  let rows = L.judgeRows(M, b, { 'PN-A-2026': { ok: 7, ng: 1, reason: '' } });
  const t = L.totals(rows);
  assert.strictEqual(t.ok, 11); assert.strictEqual(t.ng, 1);
  assert.strictEqual(L.canComplete(rows, true), false, '사유 없으면 완료 불가');
  rows = L.judgeRows(M, b, { 'PN-A-2026': { ok: 7, ng: 1, reason: '서포트 자국' } });
  assert.strictEqual(L.canComplete(rows, true), true);
  const r = L.splitBatch(M, b, rows, 'SEP-01');
  assert.strictEqual(r.ok, 11); assert.strictEqual(r.ng, 1);
  assert.strictEqual(r.event.kind, 'SPLIT');
  assert.strictEqual(r.event.outputs.reduce((a, o) => a + o.qty, 0), 11, 'outputs 에 OK 만');
  assert.strictEqual(r.born.length, 11, '부품 unit 11개가 태어난다');
  assert.strictEqual(r.scraps.length, 1);
  assert.strictEqual(r.scraps[0].reason, '서포트 자국');
  // 확인 문구가 화면에 실제로 있는가
  assert.ok(/OK '\s*\+\s*t\.ok\s*\+\s*'개가 부품으로 등록됩니다/.test(viewSrc), '확인 문구');
  ok('OK 11 / NG 1 · outputs 11 · 부품 11개 탄생 · part_scrap 1건');
}

console.log('\n=== C7 · OK + NG != 총 수량 -> 완료 비활성 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P8-W8');
  const bad = L.judgeRows(M, b, { 'PN-A-2026': { ok: 6, ng: 1, reason: '파손' } });
  assert.strictEqual(L.canComplete(bad, true), false);
  const good = L.judgeRows(M, b, { 'PN-A-2026': { ok: 7, ng: 1, reason: '파손' } });
  assert.strictEqual(L.canComplete(good, true), true);
  assert.strictEqual(L.canComplete(good, false), false, '인터록 미충족도 막는다');
  ok('합계 불일치 · 인터록 미충족 둘 다 차단');
}

console.log('\n=== C8 · 분리 완료 -> 서포트 제거대, 묶음째 이동 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P8-W8');
  const rows = L.judgeRows(M, b, { 'PN-A-2026': { ok: 7, ng: 1, reason: '파손' } });
  const r = L.splitBatch(M, b, rows, 'SEP-01');
  assert.strictEqual(r.ok, 11);
  assert.strictEqual(L.at(M, 'SEP-01').length, 11, '부품 11개가 분리대에 남는다');
  assert.ok(/^G-\d{4}$/.test(r.group_id), '묶음은 일련번호로 딴다');
  assert.ok(r.born.every(u => /^P8-W8-S\d+$/.test(u.display_id)), 'display_id 가 부모를 이어받는다');

  const supBefore = L.waitingParts(M, 'SUP-01').length;
  const mv = L.moveGroup(M, r.group_id, 'SEP-01', 'SUP-01');
  assert.strictEqual(mv.count, 11);
  assert.strictEqual(mv.event.kind, 'MOVED');
  assert.strictEqual(mv.event.group_id, r.group_id, '묶음째 1건 (부품 11건이 아니다)');
  assert.strictEqual(mv.event.unit_id, undefined, 'unit_id 를 싣지 않는다');
  assert.strictEqual(L.at(M, 'SEP-01').length, 0, '분리대가 비었다');
  assert.strictEqual(L.waitingParts(M, 'SUP-01').length, supBefore + 11, '서포트제거 대기 목록에 11개');
  ok('묶음째 Moved 1건 · 서포트제거 대기 +11');
}

console.log('\n=== C9 · 치수검사가 서포트제거와 같은 컴포넌트를 쓴다 ===');
{
  const { MOCK: M, L } = load();
  const menu = L.menu(M);
  const sup = menu.find(r => r.menu_label === '서포트 제거');
  const ins = menu.find(r => r.menu_label === '치수검사');
  assert.strictEqual(sup.ui_kind, 'PART_JUDGE');
  assert.strictEqual(ins.ui_kind, 'PART_JUDGE', '같은 ui_kind');

  // 화면 사전에 ui_kind 당 함수가 하나뿐 = 같은 컴포넌트
  const dict = /const SCREENS = \{([\s\S]*?)\};/.exec(viewSrc)[1];
  assert.ok(/PART_JUDGE:\s*screenPartJudge/.test(dict), 'PART_JUDGE -> screenPartJudge 하나');
  assert.strictEqual((viewSrc.match(/function screenPartJudge/g) || []).length, 1,
    'PART_JUDGE 컴포넌트가 정확히 하나');
  assert.ok(!/screenInspect|screenSupport|screenDim/.test(viewSrc), '공정별 컴포넌트를 따로 만들지 않았다');

  // 차이는 노드의 측정 스펙 유무뿐
  assert.strictEqual(L.measureSpec(M, 'SUP-01'), null, '서포트제거는 측정란 없음');
  assert.ok(L.measureSpec(M, 'INS-01'), '치수검사는 측정란 있음');
  assert.strictEqual(L.measureSpec(M, 'INS-01').key, 'height_mm');
  assert.strictEqual(L.inTolerance(12.03, { nominal_mm: 12.0, tol_mm: 0.15 }), true);
  assert.strictEqual(L.inTolerance(12.24, { nominal_mm: 12.0, tol_mm: 0.15 }), false, '공차 초과');
  ok('같은 screenPartJudge · 차이는 node.measure 유무뿐');
}

console.log('\n=== 부가 · 하지 말 것 검사 ===');
{
  const { MOCK: M, L } = load();
  const markup = PAGE.replace(/<script[\s\S]*?<\/script>/g, '');

  assert.strictEqual(PAGE.match(/PT-\d{4}-\d{4}-\d{2}/g), null, '존재하지 않는 부품 ID');
  assert.ok(!/U-9c4b1e77/.test(PAGE), '임시 ID U-9c4b1e77');
  ok('없는 부품 ID · 임시 ID 0건');

  // ui_kind 로만 분기 — 렌더에 node_type 분기가 없어야 한다
  assert.ok(!/node_type\s*===/.test(viewSrc), '렌더가 node_type 으로 분기한다');
  assert.ok(!/'PRINTER'|'WASHER'|'CURER'|'SUPPORT_REMOVAL'|'INSPECT'/.test(viewSrc),
    '렌더에 공정 타입 리터럴');
  ok('렌더는 ui_kind 로만 분기 (node_type 분기 0건)');

  // 개수·ID 하드코딩 금지
  [['CUR-0', '경화기 ID'], ['SUP-0', '서포트제거 ID'], ['PRT-0', '프린터 ID'],
   ['RK-WSH', '랙 ID'], ['PN-A-2026', '파트넘버'], ['P7-W7', '배치 ID']].forEach(([pat, why]) => {
    assert.ok(viewSrc.indexOf(pat) < 0, '렌더에 ' + why + ' 하드코딩: ' + pat);
    assert.ok(markup.indexOf(pat) < 0, '마크업에 ' + why + ' 하드코딩: ' + pat);
  });
  // 서브 메뉴 라벨도 마크업에 없어야 한다 (v_control_menu 에서 그린다)
  ['출력 · 세척 6', '서포트제거 2', '경화기 2', '치수검사 1'].forEach(lbl => {
    assert.ok(markup.indexOf(lbl) < 0, '서브 메뉴가 마크업에 고정: ' + lbl);
  });
  assert.ok(/id="ct-menu"/.test(markup), '서브 메뉴는 빈 마운트 포인트');
  ok('설비 ID · 파트 · 서브 메뉴 라벨 하드코딩 0건');

  // 집진·조명 같은 장치 콘솔은 제어 화면에 없다 (작업 흐름과 무관해 제거)
  assert.ok(!/ct-dev|집진/.test(viewSrc), '장치 콘솔이 남아 있다');
  ok('장치 콘솔 없음');

  // 랙 · 다음 공정은 route 파생
  assert.deepStrictEqual(L.prevRacks(M, 'SEP-01').map(r => r.node_id), ['RK-WSH-DONE-01']);
  M.routes.push({ from: 'RK-PRT-DONE-01', to: 'SEP-01', kind: 'MAIN' });
  assert.strictEqual(L.prevRacks(M, 'SEP-01').length, 2, '엣지 한 줄로 랙 2개');
  ok('랙 · 다음 공정은 route(MAIN) 파생');

  // 메뉴가 공정 순서대로
  const labels = L.menu(load().MOCK).map(r => r.menu_label);
  assert.deepStrictEqual(labels,
    ['출력 · 세척', '부품 분리', '서포트 제거', '경화기', '치수검사', '빔피킹·드릴링·트림'],
    '메뉴가 step_order 순');
  ok('메뉴 순서 = 공정 순서 (step_order)');
}

console.log('\n=== 부가 · 설비 명령 시작 · 중지 · 완료 ===');
{
  const { MOCK: M, L } = load();
  const RUN = 'PRT-01', IDLE = 'PRT-04', WAIT = 'PRT-03';

  // 빈 설비는 아무 명령도 못 준다
  ['start', 'stop', 'done'].forEach(k =>
    assert.strictEqual(L.canCmd(M, IDLE, k), false, '빈 설비에 ' + k));
  assert.strictEqual(L.runCmd(M, IDLE, 'start'), null, '빈 설비는 명령이 안 나간다');
  assert.strictEqual(L.stateBadge(M, IDLE).text, '비어 있음');

  // 투입만 된 설비 = 시작만
  assert.strictEqual(L.canCmd(M, WAIT, 'start'), true);
  assert.strictEqual(L.canCmd(M, WAIT, 'stop'), false, '안 도는 설비를 중지할 수 없다');

  // 가동 중 = 중지 · 완료만
  assert.strictEqual(L.canCmd(M, RUN, 'start'), false, '이미 도는 설비를 또 시작할 수 없다');
  assert.strictEqual(L.canCmd(M, RUN, 'stop'), true);
  assert.strictEqual(L.canCmd(M, RUN, 'done'), true);
  assert.strictEqual(L.stateBadge(M, RUN).text, '가동 중');

  // 시작 → 중지 → 시작 → 완료 한 바퀴
  assert.strictEqual(L.runCmd(M, WAIT, 'start').to, 'RUN');
  assert.strictEqual(L.at(M, WAIT)[0].status, 'RUN');
  assert.strictEqual(L.runCmd(M, WAIT, 'stop').to, 'HOLD');
  assert.strictEqual(L.canCmd(M, WAIT, 'done'), true, '정지 상태에서도 완료는 된다');
  assert.strictEqual(L.runCmd(M, WAIT, 'start').to, 'RUN', '멈춘 설비는 다시 시작된다');
  const ev = L.runCmd(M, WAIT, 'done');
  assert.strictEqual(ev.to, 'DONE');
  assert.strictEqual(ev.source, 'MANUAL', 'product_event 로 남는다');
  assert.strictEqual(L.canCmd(M, WAIT, 'stop'), false, '끝난 설비를 중지할 수 없다');
  ok('빈 설비 잠금 · 시작/중지/완료 전이 · MANUAL 기록');
}

console.log('\n=== 부가 · 세척기 · 경화기는 시작할 때 가동 시간을 받는다 ===');
{
  const { MOCK: M, L } = load();
  const WSH = 'WSH-02', PRT = 'PRT-03';          // 세척기 = 투입 대기 / 프린터 = 투입 대기

  // 스펙은 노드가 정한다 — 세척기에만 붙어 있다
  const spec = L.durationSpec(M, WSH);
  assert.ok(spec, '세척기는 가동 시간 입력이 있어야 한다');
  assert.strictEqual(spec.default, 10, '기본값 = 표준 600초 = 10분');
  assert.strictEqual(spec.unit, '분');
  assert.strictEqual(L.durationSpec(M, PRT), null, '프린터는 시간 입력이 없다');
  assert.strictEqual(L.durationSpec(M, 'CUR-01').default, 30, '경화기 기본값 = 표준 1800초 = 30분');

  // 시간을 안 주면 시작이 안 된다 (0 · 음수 · 빈값 · 글자)
  [undefined, null, '', 0, -5, 'abc'].forEach(v =>
    assert.strictEqual(L.runCmd(M, WSH, 'start', v), null, '잘못된 시간으로 시작: ' + v));
  assert.strictEqual(L.at(M, WSH)[0].status, 'WAIT', '실패했으면 상태가 그대로여야 한다');

  // 5분으로 시작 -> 진행률이 표준 10분이 아니라 정한 5분 기준
  const ev = L.runCmd(M, WSH, 'start', 5);
  assert.strictEqual(ev.to, 'RUN');
  assert.strictEqual(ev.plan_s, 300, '5분 = 300초');
  assert.strictEqual(L.runTotal(M, L.node(M, WSH)), 300, '기준이 정한 시간으로 바뀐다');
  L.at(M, WSH)[0].elapsed_s = 150;
  assert.strictEqual(L.progress(M, L.node(M, WSH)), 50, '2.5분/5분 = 50% (표준 기준이면 25%)');

  // 시간 입력이 없는 설비는 인자 없이도 시작된다
  assert.strictEqual(L.runCmd(M, PRT, 'start').to, 'RUN', '프린터는 시간 없이 시작');
  ok('세척기 · 경화기 시간 입력 · 안 정하면 시작 거부 · 진행률이 정한 시간 기준');
}

console.log('\n=== 부가 · 여러 개 실린 설비는 명령이 전부에 걸린다 ===');
{
  const { MOCK: M, L } = load();
  // 서포트 제거대의 묶음을 경화기로 통째로 넣는다 (정원 12)
  const g = L.groups(M, 'SUP-01')[0];
  L.moveGroup(M, g.group_id, 'SUP-01', 'CUR-01');
  const here = L.at(M, 'CUR-01');
  assert.ok(here.length > 1, '경화기엔 부품이 여러 개 들어간다 (' + here.length + '개)');

  assert.strictEqual(L.runCmd(M, 'CUR-01', 'start', 0), null, '시간을 안 정하면 거부');
  assert.ok(here.every(u => u.status === 'WAIT'), '거부됐으면 하나도 안 바뀐다');

  const ev = L.runCmd(M, 'CUR-01', 'start', 20);
  assert.strictEqual(ev.unit_ids.length, here.length, '명령이 실린 것 전부에 걸린다');
  assert.ok(here.every(u => u.status === 'RUN' && u.plan_s === 1200),
    '전부 RUN · 전부 20분 (하나만 바뀌면 안 된다)');
  L.runCmd(M, 'CUR-01', 'done');
  assert.ok(here.every(u => u.status === 'DONE'), '완료도 전부에');
  ok('경화기 ' + here.length + '개 적재분에 명령이 한 번에');
}

console.log('\n=== 부가 · 박스를 마감해야 다음 공정 큐에 선다 ===');
{
  const { MOCK: M, L } = load();
  const fill = (nodeId, rackId) => L.waitingParts(M, nodeId).map(p => {   // 화면이 하는 일과 같은 순서
    L.judge(M, p.unit_id, nodeId, 'OK', null, null);
    L.joinBox(M, p.unit_id, rackId);
    return p.unit_id;
  });

  // 서포트제거는 설비로 바로 못 보낸다 — 다음은 랙 하나뿐이다
  assert.deepStrictEqual(L.nextNodes(M, 'SUP-01').map(n => n.node_id), ['RK-CUR-WAIT-01']);
  const before = L.inbound(M, 'CUR-01').length;
  assert.ok(before > 0, '예시 박스가 이미 큐에 있어야 한다');

  // 담기만 해서는 큐에 안 뜬다
  fill('SUP-01', 'RK-CUR-WAIT-01');
  assert.strictEqual(L.openBox(M, 'RK-CUR-WAIT-01').items.length, 3, '박스에 3개 담김');
  assert.strictEqual(L.inbound(M, 'CUR-01').length, before, '담는 중인 박스는 아직 큐가 아니다');

  // 마감하면 경화기 큐 맨 뒤에 선다
  const curBox = L.closeBox(M, 'RK-CUR-WAIT-01');
  const q = L.inbound(M, 'CUR-01');
  assert.strictEqual(q.length, before + 1, '마감한 박스가 경화기 대기 큐에 뜬다');
  const mine = q[q.length - 1];
  assert.strictEqual(mine.label, curBox.group_id);
  assert.strictEqual(mine.qty, 3);
  assert.strictEqual(mine.kind, 'BOX');
  assert.ok(!mine.ready, '뒤에 섰으니 앞의 것부터 나간다');
  assert.ok(q[0].ready && q.filter(r => r.ready).length === 1, '맨 앞 하나만 투입 가능 (FIFO)');
  assert.deepStrictEqual(L.inbound(M, 'CUR-02'), q, '같은 랙을 보는 경화기 2호기도 같은 큐');

  // 박스는 랙마다 따로 열린다 (전엔 하나를 두 공정이 같이 썼다)
  fill('INS-01', 'RK-BPD-WAIT-01');
  const insBox = L.openBox(M, 'RK-BPD-WAIT-01');
  assert.strictEqual(insBox.items.length, 3, '치수검사 박스는 따로 담긴다');
  assert.notStrictEqual(insBox.group_id, curBox.group_id, '박스 번호가 겹치지 않는다');
  assert.strictEqual(L.inbound(M, 'CUR-01').length, before + 1, '치수검사가 담아도 경화기 큐는 그대로');

  // 투입하면 박스가 풀려 설비로 들어가고 큐에서 빠진다
  const head = q[0];
  const r = L.loadInto(M, 'CUR-01', head.key);
  assert.strictEqual(r.count, head.qty);
  assert.strictEqual(L.occupancy(M, L.node(M, 'CUR-01')), head.qty, '박스에 담긴 만큼 적재');
  assert.strictEqual(L.inbound(M, 'CUR-01').length, before, '넣었으면 큐에서 빠진다');
  assert.strictEqual(L.loadInto(M, 'CUR-02', head.key), null, '이미 나간 박스를 또 넣을 수 없다');
  ok('담기 → 마감 → 경화기 큐 → 투입 · 박스는 랙마다 따로');
}

console.log('\n=== 부가 · 첫 화면부터 큐에 예시가 있다 · 치수검사 인터록 충족 ===');
{
  const { MOCK: M, L } = load();
  [['CUR-01', '경화기'], ['CUR-02', '경화기 2호기'], ['BPD-01', '빔피킹']].forEach(([id, lbl]) => {
    const q = L.inbound(M, id);
    assert.ok(q.length >= 2, lbl + ' 대기 큐에 예시가 없다');
    assert.ok(q.every(r => r.kind === 'BOX' && r.qty > 0), lbl + ' 큐는 박스로 선다');
    assert.strictEqual(q.filter(r => r.ready).length, 1, lbl + ' FIFO — 맨 앞 하나만');
  });
  // 박스는 파트넘버가 섞여 있다 (한 종만 담기지 않는다)
  const box = M.boxes.find(b => b.node_id === 'RK-CUR-WAIT-01');
  assert.ok(new Set(box.items.map(i => i.part_no)).size > 1, '박스 안이 혼재여야 한다');

  // 치수검사 인터록 — 기준물 캘리브레이션 포함 전부 충족
  const locks = L.interlockOf(M, 'INS-01');
  assert.ok(locks.find(i => i.key === 'calib').ok, '기준물 캘리브레이션 24h 이내가 미충족이다');
  assert.strictEqual(L.interlockOk(M, 'INS-01'), true, '치수검사 판정이 잠겨 있으면 안 된다');
  ok('경화기 · 빔피킹 큐에 박스 예시 · 치수검사 인터록 2/2 충족');
}

console.log('\n=== 부가 · 치수검사 OK -> 박스 12개 자동 마감 ===');
{
  const { MOCK: M, L } = load();
  const boxRack = L.nextNodes(M, 'INS-01').filter(x => x.count_by_group)[0];
  assert.ok(boxRack, '치수검사 다음은 트레이 랙');
  assert.strictEqual(L.groupCapacity(boxRack), 12, '박스 정원 12');
  for (let i = 0; i < 12; i++) {
    M.units.push({ unit_id: 'x' + i, unit_kind: 'PART', display_id: 'P0-S' + i,
      order_id: 'o', node_id: 'INS-01', group_id: 'G-x', status: 'WAIT',
      contents: [{ part_no: 'PN-A-2026', qty: 1 }] });
    L.joinBox(M, 'x' + i, boxRack.node_id);
  }
  assert.strictEqual(L.openBox(M, boxRack.node_id).items.length, 12, '12개가 찼다');
  const closed = L.closeBox(M, boxRack.node_id);
  assert.strictEqual(closed.items.length, 12);
  const next = L.openBox(M, boxRack.node_id);
  assert.strictEqual(next.items.length, 0, '새 박스가 열린다');
  assert.notStrictEqual(next.group_id, closed.group_id);
  ok('박스 12개 마감 -> 새 박스 개설');
}

// ══ D1~D7 · 혼재 배치 ═══════════════════════════════════════
console.log('\n=== D1 · 3종 혼재 배치 -> 판정 3줄 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P9-W9');
  const rows = L.judgeRows(M, b);
  assert.strictEqual(rows.length, 3, '3줄');
  assert.deepStrictEqual(rows.map(r => r.part_no), ['PN-A-2026', 'PN-B-1180', 'PN-C-770']);
  assert.deepStrictEqual(rows.map(r => r.qty), [6, 3, 3]);
  assert.strictEqual(L.totals(rows).qty, 12);
  assert.ok(rows.length < 12, '12개인데 12줄이 아니다');
  assert.strictEqual(L.queueOf(M, 'RK-WSH-DONE-01', 1)[0].display_id, 'P9-W9',
    '3종 배치가 대기열 1번이라 바로 볼 수 있다');
  ok('3종 12개 -> 3줄 (대기열 1번)');
}

console.log('\n=== D2 · A형 NG 2 입력 후 일괄 OK -> A형은 유지 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P9-W9');
  const saved = { 'PN-A-2026': { ok: 4, ng: 2, reason: '서포트 자국' } };   // A형만 손댐

  const un = L.untouched(L.judgeRows(M, b, saved), saved);
  assert.strictEqual(un.kinds, 2, '남은 2종');
  assert.strictEqual(un.qty, 6, 'B 3 + C 3 = 6개');
  assert.ok(un.parts.every(r => r.part_no !== 'PN-A-2026'), '일괄 대상에 A형이 없다');

  // 화면이 하는 것과 같은 처리
  un.parts.forEach(r => { saved[r.part_no] = { ok: r.qty, ng: 0, reason: '' }; });
  const rows = L.judgeRows(M, b, saved);
  const a = rows.find(r => r.part_no === 'PN-A-2026');
  assert.strictEqual(a.ok, 4, 'A형 OK 가 덮이지 않았다');
  assert.strictEqual(a.ng, 2, 'A형 NG 가 살아 있다');
  assert.strictEqual(a.reason, '서포트 자국', 'A형 사유가 살아 있다');
  assert.strictEqual(rows.find(r => r.part_no === 'PN-B-1180').ok, 3);
  assert.strictEqual(rows.find(r => r.part_no === 'PN-C-770').ok, 3);
  assert.strictEqual(L.canComplete(rows, true), true);
  ok('A형 4/2 유지 · B·C만 채워짐 · 일괄 라벨 "남은 2종 (6개)"');
}

console.log('\n=== D3 · B형만 OK 4 + NG 1 (투입 3) -> 그 줄만 오류 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P9-W9');
  const rows = L.judgeRows(M, b, {
    'PN-A-2026': { ok: 6, ng: 0, reason: '' },
    'PN-B-1180': { ok: 4, ng: 1, reason: '파손' },     // 5 != 3
    'PN-C-770':  { ok: 3, ng: 0, reason: '' }
  });
  const bad = L.badRows(rows);
  assert.strictEqual(bad.length, 1, '어긋난 줄은 하나');
  assert.strictEqual(bad[0].part_no, 'PN-B-1180', '어느 파트인지 지목된다');
  assert.strictEqual(L.rowValid(rows.find(r => r.part_no === 'PN-A-2026')), true, 'A형은 정상');
  assert.strictEqual(L.canComplete(rows, true), false, '완료 버튼 비활성');
  // 합계만 보면 13/12 라 어긋나지만, 합계가 맞아도 파트별이 틀리면 막아야 한다
  const trap = L.judgeRows(M, b, {
    'PN-A-2026': { ok: 5, ng: 0, reason: '' },          // 5 != 6  (부족)
    'PN-B-1180': { ok: 4, ng: 0, reason: '' },          // 4 != 3  (초과)
    'PN-C-770':  { ok: 3, ng: 0, reason: '' }
  });
  assert.strictEqual(L.totals(trap).ok, 12, '합계는 12로 맞는다');
  assert.strictEqual(L.canComplete(trap, true), false, '합계가 맞아도 파트별이 어긋나면 막는다');
  assert.strictEqual(L.badRows(trap).length, 2);
  ok('B형 줄만 오류 · 합계가 맞아도 파트별로 막는다');
}

console.log('\n=== D4 · 파트마다 다른 NG 사유가 공존 ===');
{
  const { MOCK: M, L } = load();
  const b = M.units.find(x => x.display_id === 'P9-W9');
  const rows = L.judgeRows(M, b, {
    'PN-A-2026': { ok: 4, ng: 2, reason: '서포트 자국' },
    'PN-B-1180': { ok: 2, ng: 1, reason: '파손' },
    'PN-C-770':  { ok: 3, ng: 0, reason: '' }
  });
  assert.strictEqual(L.canComplete(rows, true), true);
  const r = L.splitBatch(M, b, rows, 'SEP-01');
  assert.strictEqual(r.scraps.length, 2, '사유가 다른 폐기 2건');
  assert.deepStrictEqual(r.scraps.map(x => [x.part_no, x.qty, x.reason]),
    [['PN-A-2026', 2, '서포트 자국'], ['PN-B-1180', 1, '파손']]);
  assert.strictEqual(r.ok, 9); assert.strictEqual(r.ng, 3);
  ok('서포트 자국 2건 + 파손 1건 공존 · part_scrap 2행');
}

console.log('\n=== D5 · 확인 문구에 파트별 OK/NG 가 각각 ===');
{
  assert.ok(/rows\.map\(r =>[\s\S]{0,200}OK ' \+ \(\+r\.ok \|\| 0\) \+ ' \/ NG ' \+ \(\+r\.ng \|\| 0\)/.test(viewSrc),
    '확인 문구가 파트별로 줄을 만든다');
  assert.ok(/esc\(r\.reason\)/.test(viewSrc), '확인 문구에 파트별 사유');
  ok('확인 다이얼로그가 파트별 OK/NG/사유를 각각 보여준다');
}

console.log('\n=== D6 · 6개짜리 두 배치를 한 묶음에 ===');
{
  const { MOCK: M, L } = load();
  const target = L.groupTarget(M, 'SEP-01');
  assert.strictEqual(target, 12, '묶음 정원 = 경화기 정원 12 (서포트제거 16 이 아니다)');

  const b1 = L.queueOf(M, 'RK-WSH-DONE-01', 2)[0];        // P11-W11 6개
  assert.strictEqual(L.qtyOf(b1), 6);
  const r1 = L.splitBatch(M, b1, L.judgeRows(M, b1), 'SEP-01');
  assert.strictEqual(L.groupCount(M, 'SEP-01', r1.group_id), 6);

  // 같은 group_id 를 넘기면 누적된다
  const b2 = M.units.find(x => x.display_id === 'P10-W10');  // C형 6개
  const r2 = L.splitBatch(M, b2, L.judgeRows(M, b2), 'SEP-01', r1.group_id);
  assert.strictEqual(r2.group_id, r1.group_id, '같은 묶음');
  assert.strictEqual(L.groupCount(M, 'SEP-01', r1.group_id), 12, '묶음 12개');

  const srcs = L.groupSources(M, 'SEP-01', r1.group_id);
  assert.strictEqual(srcs.length, 2, '출처 배치 2개가 표시된다');
  assert.deepStrictEqual(srcs.map(s => s.display_id).sort(), ['P10-W10', 'P11-W11']);
  assert.strictEqual(srcs.find(s => s.display_id === 'P11-W11').qty, 6);
  assert.deepStrictEqual(Object.keys(srcs.find(s => s.display_id === 'P11-W11').parts).sort(),
    ['PN-A-2026', 'PN-B-1180'], '출처별 파트 내역까지');
  ok('두 배치 6+6 = 묶음 12 · 출처 2개 · 파트 내역 보존');
}

console.log('\n=== D7 · 대기열의 파트 구성 표기 ===');
{
  const { MOCK: M, L } = load();
  const q = L.queueOf(M, 'RK-WSH-DONE-01', 1);
  // 말줄임으로 처리하지 않는다 — 종수 배지 + 파트별 칩
  assert.ok(/ct-kinds/.test(viewSrc) && /ct-chip/.test(viewSrc), '종수 배지 + 파트 칩');
  assert.ok(!/…|\.\.\./.test(/'<span class="ct-mix">'[\s\S]{0,400}/.exec(viewSrc)[0]),
    '말줄임을 쓰지 않는다');
  assert.ok(/flex-wrap:wrap/.test(PAGE), '넘치면 줄바꿈');
  // 칸 미리보기에 종수
  const slot1 = L.slotsOf(M, 'RK-WSH-DONE-01')[0];
  assert.deepStrictEqual(slot1.contents, ['P9-W9 (3종)', 'P10-W10 (1종)', 'P8-W8 (2종)']);
  ok('종수 배지 + 파트 칩(줄바꿈) · 칸 미리보기에도 종수');
}

// ══ DOM 검사 — jsdom 이 있을 때만 ════════════════════════════
// 논리는 위에서 다 봤지만 "클릭했을 때 화면이 실제로 어떻게 되는가"는 DOM 이 있어야 안다.
// 2026-09-09 에 여기서 못 잡은 버그가 실제로 났다 (page 섹션의 data-menu 와 선택자 충돌).
//   NODE_PATH=<jsdom 있는 node_modules> node docs/juhee/06_와이어프레임_HTML/check_control.js
let JSDOM = null;
try { JSDOM = require('jsdom').JSDOM; } catch (e) { /* 없으면 건너뛴다 */ }

if (!JSDOM) {
  console.log('\n=== DOM 검사 건너뜀 (jsdom 없음) ===');
  console.log('  npm i jsdom 후 NODE_PATH 를 지정하면 클릭 동작까지 검사합니다.');
  console.log('\n논리 검사 ' + n + '건 통과 (C1~C9 + 부가)\n');
} else {
  const dom = new JSDOM(HTML, { runScripts: 'dangerously', url: 'https://x/#control', pretendToBeVisual: true });
  const W = dom.window, D = W.document;
  // 클릭 핸들러 안에서 난 예외는 화면상 "아무 일도 안 일어남"으로만 보인다. 모아서 실패시킨다.
  const jsErrors = [];
  // jsdom 이 안 만든 브라우저 기능(scrollTo 등)은 우리 오류가 아니다
  const appError = (m) => m && m.indexOf('Not implemented') < 0;
  W.addEventListener('error', (e) => { const m = e.message || String(e.error); if (appError(m)) jsErrors.push(m); });
  const vc = W.__virtualConsole || dom.virtualConsole;
  if (vc && vc.on) vc.on('jsdomError', (e) => { if (appError(e.message)) jsErrors.push(e.message); });
  const click = (el) => el.dispatchEvent(new W.MouseEvent('click', { bubbles: true }));
  const tabs = () => Array.from(D.querySelectorAll('#ct-menu .ptab'));
  const cur = () => { const t = D.querySelector('#ct-menu .ptab.on'); return t ? t.textContent.trim() : null; };
  const scr = () => { const e = D.querySelector('#ct-screen [data-screen]'); return e ? e.dataset.screen : null; };
  const go = (lbl) => click(tabs().find(t => t.textContent.indexOf(lbl) >= 0));

  setTimeout(() => {
    console.log('\n=== DOM · 첫 진입은 첫 공정 ===');
    assert.ok(cur() && cur().indexOf('출력 · 세척') === 0, '첫 화면은 공정 순서 첫 탭');
    assert.strictEqual(scr(), 'MONITOR');
    ok('첫 공정 탭이 먼저 열린다');

    console.log('\n=== DOM · 중립 클릭이 서브탭을 바꾸지 않는가 ===');
    go('부품 분리');
    assert.strictEqual(scr(), 'BATCH_SPLIT');
    ['#ct-screen .ct-step b', '#ct-screen .hint', '#ct-screen .ct-left',
     '#ct-screen [data-screen]', '#ct-screen .ct-main'].forEach(sel => {
      const el = D.querySelector(sel); if (!el) return;
      click(el);
      assert.ok(cur().indexOf('부품 분리') === 0, '중립 클릭에 탭이 튕겼다: ' + sel);
    });
    ok('중립 클릭 5종에 선택 유지');

    console.log('\n=== DOM · 상단 메뉴 제어 재클릭 ===');
    const navi = Array.from(D.querySelectorAll('#page-control .navi'))
      .find(x => x.textContent.trim() === '제어');
    click(navi);
    assert.ok(cur().indexOf('부품 분리') === 0, '보던 서브탭이 유지되어야 한다');
    ok('보던 화면 유지');

    console.log('\n=== DOM · 탭마다 ui_kind 대로 렌더 ===');
    [['출력 · 세척', 'MONITOR'], ['부품 분리', 'BATCH_SPLIT'], ['서포트 제거', 'PART_JUDGE'],
     ['치수검사', 'PART_JUDGE'], ['경화기', 'MONITOR']]
      .forEach(([lbl, kind]) => { go(lbl); assert.strictEqual(scr(), kind, lbl); });
    ok('탭 전부 ui_kind 대로');

    console.log('\n=== DOM · 프린터 + 세척기가 한 페이지 · 설비마다 블록 ===');
    go('출력 · 세척');
    const eqs = Array.from(D.querySelectorAll('#ct-screen .ct-eq'));
    assert.strictEqual(eqs.length, 6, '프린터 4 + 세척기 2 = 블록 6개');
    const names = eqs.map(e => e.querySelector('b').textContent);
    assert.ok(names.some(x => x.indexOf('프린터') === 0) && names.some(x => x.indexOf('세척기') === 0),
      '두 공정이 같은 화면에 있어야 한다');
    assert.strictEqual(D.querySelectorAll('#ct-nodebar [data-ctl-node]').length, 0,
      'MONITOR 는 노드를 골라 보지 않는다 (다 편다)');
    // 블록마다 상태 뱃지 · 실린 것이 있으면 명령 3개, 비었으면 투입
    let loaded = 0;
    eqs.forEach((e, i) => {
      assert.ok(e.querySelector('.tag'), names[i] + ' 상태 뱃지 없음');
      const cmds = Array.from(e.querySelectorAll('[data-cmd]')).map(b => b.textContent);
      if (e.querySelector('[data-load]')) {
        assert.deepStrictEqual(cmds, [], names[i] + ' 은 비었는데 명령 버튼이 있다');
        assert.strictEqual(e.querySelector('.tag').textContent, '비어 있음', names[i]);
      } else {
        loaded++;
        assert.deepStrictEqual(cmds, ['시작', '중지', '완료'], names[i] + ' 명령 버튼');
      }
    });
    assert.ok(loaded >= 2, '실려 있는 설비가 있어야 명령을 볼 수 있다');
    ok('블록 6개 (' + names.join(' · ') + ') · 실린 것 ' + loaded + '대는 시작/중지/완료, 나머지는 투입');

    console.log('\n=== DOM · 시작 명령이 실제로 상태를 바꾼다 ===');
    {
      const startable = () => Array.from(D.querySelectorAll('#ct-screen .ct-eq'))
        .filter(e => { const b = e.querySelector('[data-cmd="start"]'); return b && !b.disabled; });
      const named = (n) => startable().find(e => e.querySelector('b').textContent.indexOf(n) === 0);
      const blockOf = (id) => D.querySelector('#ct-screen .ct-eq[data-eq="' + id + '"]');

      // 프린터 — 시간을 묻지 않는다
      const prt = named('프린터');
      assert.ok(prt, '시작을 누를 수 있는 프린터가 있어야 한다');
      const prtId = prt.querySelector('[data-cmd="start"]').dataset.n;
      click(prt.querySelector('[data-cmd="start"]'));
      assert.strictEqual(D.querySelector('#ct-run-min'), null, '프린터엔 가동 시간 입력이 없어야 한다');
      click(D.querySelector('#ct-dlg-yes'));                      // 물리 명령이라 확인을 받는다
      assert.strictEqual(blockOf(prtId).querySelector('.tag').textContent, '가동 중');

      // 세척기 — 몇 분 돌릴지 묻는다
      const wsh = named('세척기');
      assert.ok(wsh, '시작을 누를 수 있는 세척기가 있어야 한다');
      const wshId = wsh.querySelector('[data-cmd="start"]').dataset.n;
      click(wsh.querySelector('[data-cmd="start"]'));
      const minInput = D.querySelector('#ct-run-min');
      assert.ok(minInput, '시작 확인창에 가동 시간 입력이 있어야 한다');
      assert.strictEqual(minInput.value, '10', '기본값은 표준 시간 10분');
      minInput.value = '25';
      click(D.querySelector('#ct-dlg-yes'));

      const after = blockOf(wshId);
      assert.strictEqual(after.querySelector('.tag').textContent, '가동 중', '시작 후 가동 중');
      assert.ok(/설정 25분/.test(after.querySelector('.s').textContent),
        '정한 가동 시간이 블록에 보여야 한다: ' + after.querySelector('.s').textContent);
      assert.ok(after.querySelector('[data-cmd="start"]').disabled, '가동 중이면 시작 잠김');
      assert.ok(!after.querySelector('[data-cmd="stop"]').disabled, '가동 중이면 중지 열림');
      const logged = Array.from(D.querySelectorAll('#ct-screen .logrow b')).map(e => e.textContent);
      assert.ok(logged.some(t => /시작 25분/.test(t)), '정한 시간이 로그에 남아야 한다: ' + logged[0]);
      ok('프린터는 바로 시작 · 세척기는 25분 지정 시작 · 버튼 가부 반전 · 로그');
    }

    console.log('\n=== DOM · 서포트 제거는 박스에 담기만 한다 ===');
    let curBoxId = null;
    {
      go('서포트 제거');
      assert.strictEqual(D.querySelectorAll('#ct-screen [data-dispatch]').length, 0,
        '설비로 바로 투입하는 버튼이 남아 있다');
      // 적재량은 박스 카드의 'n / 정원' 뱃지로 본다
      const box = () => D.querySelector('#ct-screen .ct-side .pcard .h .tag').textContent.trim();
      assert.strictEqual(box(), '0 / 12', '판정 전이라 0 · 정원 12');

      click(D.querySelector('#ct-allok-part'));
      assert.strictEqual(box(), '3 / 12', 'OK 3개면 3개가 담긴다');
      const from = D.querySelector('#ct-screen .ct-from').textContent;
      assert.ok(/BOX-\d+ · 3개/.test(from), '담긴 박스 번호와 개수: ' + from);
      curBoxId = /BOX-\d+/.exec(from)[0];

      click(D.querySelector('#ct-closebox'));                    // 다 못 채워도 수동 마감
      click(D.querySelector('#ct-dlg-yes'));
      assert.strictEqual(box(), '0 / 12', '마감하면 새 박스가 빈 채로 열린다');
      ok('서포트 제거 = 박스 3/12 담고 마감 (' + curBoxId + ') · 설비 투입 버튼 없음');
    }

    console.log('\n=== DOM · 마감한 박스가 경화기 대기 큐에 선다 ===');
    {
      go('경화기');
      const rows = () => Array.from(D.querySelectorAll('#ct-screen .ct-left [data-pick]'));
      const labels = () => rows().map(r => r.querySelector('.n').textContent);
      assert.ok(rows().length >= 3, '예시 박스 + 방금 마감한 박스가 줄을 서야 한다: ' + labels());
      assert.ok(/^1 · BOX-\d+/.test(labels()[0]), '순서 번호 + 박스 번호: ' + labels()[0]);
      assert.ok(labels().some(t => t.indexOf(curBoxId) >= 0), '방금 마감한 ' + curBoxId + ' 도 큐에 있다');
      assert.ok(rows()[0].className.indexOf('on') >= 0, '맨 앞 것이 골라져 있다');
      assert.strictEqual(rows().filter(r => !r.disabled).length, 1, 'FIFO — 맨 앞 하나만 눌린다');
      assert.ok(/앞의 것 먼저/.test(rows()[1].textContent), '뒤엣것은 이유를 밝힌다');
      const headQty = +/(\d+)개/.exec(rows()[0].querySelector('.s').textContent)[1];

      // 비어 있는 설비는 명령 대신 '투입'
      const eq = D.querySelector('#ct-screen .ct-eq');
      const loadBtn = eq.querySelector('[data-load]');
      assert.ok(loadBtn, '빈 설비에 투입 버튼이 없다');
      assert.ok(/^BOX-\d+ 투입$/.test(loadBtn.textContent),
        '무엇을 넣는지 버튼에 쓴다: ' + loadBtn.textContent);
      const eqId = eq.dataset.eq;
      const head = /BOX-\d+/.exec(loadBtn.textContent)[0];

      click(loadBtn);
      click(D.querySelector('#ct-dlg-yes'));
      const after = D.querySelector('#ct-screen .ct-eq[data-eq="' + eqId + '"]');
      assert.strictEqual(after.querySelector('.tag').textContent, '대기', '투입하면 대기 상태');
      assert.ok(after.querySelector('.s').textContent.indexOf(headQty + '개 적재') >= 0,
        '넣은 만큼 적재된다: ' + after.querySelector('.s').textContent);
      assert.ok(!labels().some(t => t.indexOf(' · ' + head) >= 0), '넣었으면 큐에서 빠진다');

      // 넣은 것을 25분으로 돌린다
      click(after.querySelector('[data-cmd="start"]'));
      const mi = D.querySelector('#ct-run-min');
      assert.ok(mi && mi.value === '30', '경화기 기본 30분: ' + (mi && mi.value));
      mi.value = '25';
      click(D.querySelector('#ct-dlg-yes'));
      const run = D.querySelector('#ct-screen .ct-eq[data-eq="' + eqId + '"]');
      assert.strictEqual(run.querySelector('.tag').textContent, '가동 중');
      assert.ok(/설정 25분/.test(run.querySelector('.s').textContent), '정한 시간이 보인다');
      ok('큐의 박스를 골라 투입 → 3개 적재 → 25분 가동');
    }

    console.log('\n=== DOM · D1 3종 배치 판정 3줄 ===');
    go('부품 분리');
    click(Array.from(D.querySelectorAll('#ct-screen [data-slot]')).find(b => !b.disabled));
    const jrows = () => Array.from(D.querySelectorAll('#ct-screen .ct-jrow'));
    assert.strictEqual(jrows().length, 3, '3종이면 3줄');
    const pns = Array.from(D.querySelectorAll('#ct-screen .ct-pn')).map(e => e.textContent);
    assert.deepStrictEqual(pns, ['PN-A-2026', 'PN-B-1180', 'PN-C-770']);
    // 대기열 파트 구성이 말줄임 없이 다 보이는가
    const mixChips = Array.from(D.querySelectorAll('#ct-screen [data-batch] .ct-chip')).map(e => e.textContent);
    assert.ok(mixChips.length >= 6, '칩으로 전부 표시 (' + mixChips.length + '개)');
    assert.ok(!mixChips.some(c => c.indexOf('…') >= 0), '말줄임 없음');
    ok('판정 3줄 · 대기열 칩 ' + mixChips.length + '개 (말줄임 0)');

    console.log('\n=== DOM · D2 A형 NG 입력 후 일괄 OK ===');
    const numOf = (i, f) => D.querySelector('#ct-screen .ct-jrow:nth-child(' + (i + 1) +
      ') input[data-f="' + f + '"]');
    const setNum = (i, f, v) => { const el = numOf(i, f); el.value = String(v);
      el.dispatchEvent(new W.Event('change', { bubbles: true })); };
    setNum(0, 'ng', 2);                                   // A형 NG 2 (OK 는 자동 4)
    let sel = D.querySelector('#ct-screen .ct-reason select');
    assert.ok(sel, 'NG 를 넣으면 사유 선택이 나타난다');
    sel.value = '서포트 자국'; sel.dispatchEvent(new W.Event('change', { bubbles: true }));

    const allok = D.querySelector('#ct-allok');
    assert.ok(/남은 2종 전체 OK \(6개\)/.test(allok.textContent),
      '일괄 라벨이 대상 수를 말한다: ' + allok.textContent);
    click(allok);
    assert.strictEqual(numOf(0, 'ok').value, '4', 'A형 OK 가 덮이지 않았다');
    assert.strictEqual(numOf(0, 'ng').value, '2', 'A형 NG 가 살아 있다');
    assert.strictEqual(numOf(1, 'ok').value, '3', 'B형이 채워졌다');
    assert.strictEqual(numOf(2, 'ok').value, '3', 'C형이 채워졌다');
    assert.ok(D.querySelector('#ct-screen .ct-reason select').value === '서포트 자국', '사유 유지');
    ok('A형 4/2 유지 · B·C 채워짐 · 사유 유지');

    console.log('\n=== DOM · D3 한 줄만 어긋나면 그 줄만 오류 ===');
    // 입력은 투입 수량으로 클램프된다. 불일치는 "NG 를 넣은 뒤 OK 를 도로 올리는" 경로로 생긴다.
    setNum(1, 'ng', 1);                                   // B형: NG 1, OK 자동 2 (합 3, 정상)
    const bSel = D.querySelectorAll('#ct-screen .ct-reason select')[1];
    bSel.value = '파손'; bSel.dispatchEvent(new W.Event('change', { bubbles: true }));
    assert.ok(!D.querySelector('#ct-done').disabled, '여기까지는 정상 (합 3)');
    setNum(1, 'ok', 3);                                   // B형: OK 3 + NG 1 = 4 != 투입 3
    assert.ok(D.querySelector('#ct-done').disabled, '완료 버튼 비활성');
    const warn = D.querySelector('#ct-screen .ct-warn');
    assert.ok(warn && warn.textContent.indexOf('PN-B-1180') >= 0, '어느 파트인지 지목: ' +
      (warn ? warn.textContent.trim().slice(0, 50) : '(경고 없음)'));
    assert.ok(warn.textContent.indexOf('PN-A-2026') < 0, 'A형은 지목되지 않는다 (A형도 NG 2 인데)');
    assert.strictEqual(D.querySelectorAll('#ct-screen .ct-num.bad').length, 2, '어긋난 줄의 칸만 빨갛게');
    // 합계만 보면 12/12 로 맞을 수도 있다 — 그래도 막아야 한다
    setNum(1, 'ok', 2);
    assert.ok(!D.querySelector('#ct-done').disabled, '고치면 다시 활성');
    ok('B형만 지목 (A형 NG 는 무관) · 완료 비활성 -> 고치면 활성');

    console.log('\n=== DOM · D6 두 배치를 한 묶음에 (화면 경로) ===');
    go('부품 분리');
    const slots = Array.from(D.querySelectorAll('#ct-screen [data-slot]'));
    click(slots[1]);                                        // 칸 2 (6개짜리 두 장)
    const done = () => { click(D.querySelector('#ct-done')); click(D.querySelector('#ct-dlg-yes')); };
    done();                                                 // P11-W11 6개
    let srcRows = Array.from(D.querySelectorAll('#ct-screen .ct-src b')).map(e => e.textContent);
    assert.deepStrictEqual(srcRows, ['P11-W11'], '첫 배치만 들어 있다');
    let badge = D.querySelector('#ct-screen .ct-side .pcard .tag');
    assert.ok(/6 \/ 12/.test(badge.textContent), '6 / 12 로 표시: ' + badge.textContent);
    assert.ok(D.querySelector('#ct-newgroup'), '누적 중이면 "새 묶음으로 시작" 이 보인다');

    click(slots[1]);
    done();                                                 // P12-W12 6개 -> 같은 묶음
    srcRows = Array.from(D.querySelectorAll('#ct-screen .ct-src b')).map(e => e.textContent);
    assert.deepStrictEqual(srcRows.sort(), ['P11-W11', 'P12-W12'], '출처 배치 2개가 보인다');
    badge = D.querySelector('#ct-screen .ct-side .pcard .tag');
    assert.ok(/12 \/ 12/.test(badge.textContent), '12 / 12 로 찼다: ' + badge.textContent);
    assert.strictEqual(D.querySelectorAll('#ct-screen .ct-src').length, 2, '출처 줄 2개');
    assert.ok(!D.querySelector('#ct-newgroup'), '정원이 차면 누적이 닫힌다');
    assert.ok(/정원 12개가 찼습니다/.test(D.querySelector('#ct-screen .ct-side').textContent), '찼다고 알린다');
    ok('6 + 6 = 12 · 출처 2개 · 차면 자동으로 닫힘');

    console.log('\n=== DOM · 정원을 넘기는 배치는 새 묶음으로 ===');
    // 앞 검사에서 P9-W9 에 NG 를 넣어뒀으므로 완료 수량이 12 가 아니다 —
    // 정확한 숫자에 기대지 않고 "자리가 남은 묶음이 있는데 다음 배치가 안 들어가면 새 묶음" 만 본다.
    const sideTags = () => Array.from(D.querySelectorAll('#ct-screen .ct-side .pcard .tag'))
      .map(e => e.textContent.trim()).filter(t => /\d+ \/ \d+/.test(t));
    const pickSlot = (i) => click(Array.from(D.querySelectorAll('#ct-screen [data-slot]'))[i]);
    pickSlot(0); done();                                   // P9-W9 (NG 3 이라 OK 9) -> 9/12 열림
    pickSlot(0); done();                                   // P10-W10 6개 -> 9+6=15>12 이므로 새 묶음 6/12
    assert.ok(sideTags().indexOf('6 / 12') >= 0, '자리가 남은 묶음이 있다: ' + sideTags().join(', '));
    assert.ok(sideTags().indexOf('15 / 12') < 0, '앞 묶음에 억지로 담지 않았다');
    const before = sideTags().length;
    pickSlot(0); done();                                   // P8-W8 12개 -> 6+12=18>12 이므로 또 새 묶음
    const tags = sideTags();
    assert.strictEqual(tags.length, before + 1, '묶음이 하나 늘어야 한다: ' + tags.join(', '));
    assert.ok(tags.indexOf('6 / 12') >= 0, '6/12 묶음이 그대로 남아 있다 (억지로 18개가 되지 않았다)');
    assert.ok(tags.indexOf('12 / 12') >= 0, '넘친 배치는 제 묶음을 받았다');
    assert.ok(tags.indexOf('18 / 12') < 0, '정원을 넘겨 담지 않았다');
    ok('6/12 에 12개짜리를 넣으면 새 묶음으로 (' + tags.join(' · ') + ')');

    console.log('\n=== DOM · 분리 -> 넘기기 -> 서포트 제거 한 바퀴 ===');
    go('부품 분리');
    click(Array.from(D.querySelectorAll('#ct-screen [data-slot]')).find(b => !b.disabled));
    const q = Array.from(D.querySelectorAll('#ct-screen [data-batch]'));
    assert.strictEqual(q.filter(b => !b.disabled).length, 1, 'FIFO 라 1장만 열린다');
    const supBefore = (go('서포트 제거'), D.querySelectorAll('#ct-screen .ct-parts .uid').length);
    go('부품 분리');
    click(Array.from(D.querySelectorAll('#ct-screen [data-slot]')).find(b => !b.disabled));
    click(D.querySelector('#ct-done')); click(D.querySelector('#ct-dlg-yes'));
    const g = Array.from(D.querySelectorAll('#ct-screen [data-handoff]'));
    assert.ok(g.length, '분리 완료 묶음이 생겨야 한다');
    click(g[0]); click(D.querySelector('#ct-dlg-yes'));
    go('서포트 제거');
    const after = D.querySelectorAll('#ct-screen .ct-parts .uid').length;
    assert.ok(after > supBefore, '서포트 제거 대기 목록이 늘어야 한다 (' + supBefore + ' -> ' + after + ')');
    ok('분리분이 서포트 제거 대기 목록으로 이어진다 (' + supBefore + ' -> ' + after + ')');

    assert.deepStrictEqual(jsErrors, [], '조작 중 자바스크립트 오류가 났다:\n  ' + jsErrors.join('\n  '));
    ok('조작 전 과정에서 자바스크립트 오류 0건');
    console.log('\n검사 ' + n + '건 전부 통과 (C1~C9 + D1~D7 + 부가 + DOM)\n');
  }, 400);
}
