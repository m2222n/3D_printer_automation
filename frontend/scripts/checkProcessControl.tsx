/**
 * 공정 제어 탭 렌더·조작 검사 — 와이어프레임 `check_control.js` / `check_merged.js` ⑥~⑧ 대응.
 * 조작(투입 → 시작)이 실제로 상태를 바꾸는지까지 본다.
 */

import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/', pretendToBeVisual: true,
});
const g = globalThis as unknown as Record<string, unknown>;
g.window = dom.window;
g.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
g.HTMLElement = dom.window.HTMLElement;
g.Element = dom.window.Element;
g.Node = dom.window.Node;
g.SVGElement = dom.window.SVGElement;
g.localStorage = dom.window.localStorage;
g.IS_REACT_ACT_ENVIRONMENT = false;

const { createElement } = await import('react');
const { createRoot } = await import('react-dom/client');
const { ProcessControlPage } = await import('../src/components/ProcessControlPage');
const { MOCK, at } = await import('../src/mocks/lineMock');

const el = dom.window.document.getElementById('root')!;
createRoot(el).render(createElement(ProcessControlPage));
const settle = () => new Promise((r) => setTimeout(r, 140));
await settle();

let n = 0;
const ok = (m: string) => { n += 1; console.log('  ✓', m); };
const buttons = () => Array.from(el.querySelectorAll('button')) as HTMLButtonElement[];
const click = async (b: HTMLButtonElement) => {
  b.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  await settle();
};
const find = (re: RegExp) => buttons().find((b) => re.test(b.textContent ?? ''));
/** 🚨 확인 버튼은 반드시 다이얼로그 안에서 찾는다 — 설비 블록에도 같은 글자('시작')가 있다. */
const dialogConfirm = () => {
  const dlg = el.querySelector('.fixed.inset-0');
  assert.ok(dlg, '확인 다이얼로그가 열려 있지 않다');
  const bs = Array.from(dlg!.querySelectorAll('button')) as HTMLButtonElement[];
  return bs[bs.length - 1];
};

// ⑥ 서브 탭 = v_control_menu · 공정 순서대로 · 하드코딩 아님
{
  const tabs = buttons().filter((b) => /^(출력 · 세척|부품 분리|서포트 제거|경화기|치수검사|빔피킹)/.test(b.textContent ?? ''));
  assert.ok(tabs.length >= 6, `서브 탭이 모자라다: ${tabs.length}`);
  assert.ok(/출력 · 세척/.test(tabs[0].textContent ?? ''), '첫 탭이 공정 순서 첫 번째가 아니다');
  assert.ok(/설비 6대/.test(el.textContent ?? ''), '프린터 4 + 세척기 2 가 한 화면으로 안 묶였다');
  ok(`서브 탭 ${tabs.length}개 · 공정 순서 · 첫 탭 "출력 · 세척"`);
}

// ⑦ 빈 설비 투입 → 시작
{
  const before = at(MOCK, 'PRT-04').length;
  assert.equal(before, 0, '시험 전에 프린터 4호기가 비어 있어야 한다');

  const load = buttons().find((b) => /투입$/.test(b.textContent ?? '') && !b.disabled);
  assert.ok(load, '투입 가능한 빈 설비가 없다');
  await click(load!);
  assert.ok(/에 넣습니다/.test(el.textContent ?? ''), '투입 확인 다이얼로그가 안 떴다');
  await click(dialogConfirm());

  const loaded = MOCK.nodes.filter((nd) => nd.node_kind === 'STATION' && at(MOCK, nd.node_id).length > 0);
  assert.ok(loaded.length > 0, '투입 후에도 실린 설비가 없다');
  assert.ok(/투입/.test(el.textContent ?? ''), '명령 로그에 투입이 없다');
  ok('빈 설비 투입 — 확인 다이얼로그 경유');
}

// ⑦' 시작 — 가동 시간 입력이 있는 설비는 값을 받는다
{
  const runCount = () => MOCK.nodes.filter((nd) => at(MOCK, nd.node_id)[0]?.status === 'RUN').length;
  const before = runCount();
  const start = buttons().find((b) => b.textContent === '시작' && !b.disabled);
  assert.ok(start, '시작 버튼이 전부 비활성이다');
  await click(start!);
  assert.ok(/명령을 보냅니다/.test(el.textContent ?? ''), '명령 확인 다이얼로그가 안 떴다');
  const hasMin = /가동 시간/.test(el.textContent ?? '');
  await click(dialogConfirm());
  assert.equal(runCount(), before + 1, `시작했는데 가동 대수가 안 늘었다: ${before} → ${runCount()}`);
  ok(`시작 명령${hasMin ? ' (가동 시간 입력 있음)' : ''} — 가동 ${before} → ${runCount()}대`);
}

// ⑧ BATCH_SPLIT — 랙 → 칸 → 배치 → 전체 OK → 배치 완료 등록
{
  await click(find(/^부품 분리/)!);
  assert.ok(/인터록/.test(el.textContent ?? ''), '인터록 패널이 없다');
  assert.ok(/집진 가동 중/.test(el.textContent ?? ''), '인터록 항목이 없다');
  assert.ok(!el.querySelector('[data-batch]'), '칸을 고르기 전인데 대기열이 떠 있다');

  const slot = buttons().find((b) => /^칸 1/.test(b.textContent ?? ''));
  assert.ok(slot, '칸 버튼이 없다');
  await click(slot!);
  const batches = buttons().filter((b) => /지금 작업|앞 배치 먼저/.test(b.textContent ?? ''));
  assert.ok(batches.length >= 3, `배치 대기열이 모자라다: ${batches.length}`);
  assert.equal(batches.filter((b) => !b.disabled).length, 1, 'FIFO — 지금 작업 가능한 배치는 하나여야 한다');

  const allOk = find(/전체 OK \(/);
  assert.ok(allOk && !allOk.disabled, '일괄 OK 버튼이 없다/비활성이다');
  await click(allOk!);
  const done = find(/^배치 완료 등록$/);
  assert.ok(done && !done.disabled, '전체 OK 후에도 배치 완료가 비활성');

  const groupsBefore = new Set(MOCK.units.filter((u) => u.unit_kind === 'PART' && u.group_id).map((u) => u.group_id)).size;
  await click(done!);
  assert.ok(/되돌릴 수 없습니다/.test(el.textContent ?? ''), '되돌릴 수 없다는 경고가 없다');
  await click(dialogConfirm());
  const groupsAfter = new Set(MOCK.units.filter((u) => u.unit_kind === 'PART' && u.group_id).map((u) => u.group_id)).size;
  assert.equal(groupsAfter, groupsBefore + 1, `묶음이 안 생겼다: ${groupsBefore} → ${groupsAfter}`);
  assert.ok(/묶음 G-/.test(el.textContent ?? ''), '묶음 카드가 안 보인다');
  ok(`부품 분리 — 칸 → 배치(FIFO) → 전체 OK → 완료 등록 · 묶음 ${groupsBefore} → ${groupsAfter}`);
}

// ⑨ PART_JUDGE — 측정값 입력란 + OK 판정 → 박스 적재
{
  await click(find(/^치수검사/)!);
  assert.ok(/부품별 판정/.test(el.textContent ?? ''), '판정 화면이 아니다');
  assert.ok(/높이 \(mm\)/.test(el.textContent ?? ''), '측정 스펙이 있는 노드인데 입력란이 없다');
  assert.ok(/박스 적재/.test(el.textContent ?? ''), '박스 적재 패널이 없다');

  const rows = el.querySelectorAll('tbody tr').length;
  assert.ok(rows > 0, '판정할 부품이 없다');
  const okBtn = buttons().find((b) => b.textContent === 'OK');
  assert.ok(okBtn, 'OK 버튼이 없다');
  await click(okBtn!);
  await settle();
  assert.equal(el.querySelectorAll('tbody tr').length, rows - 1, 'OK 판정한 부품이 목록에서 안 빠졌다');
  assert.ok(MOCK.judgement.some((j) => j.verdict === 'OK'), 'judgement 에 OK 가 안 남았다');
  ok(`치수검사 — 측정 입력란 + OK 판정 (부품 ${rows} → ${rows - 1}) · 박스로 합류`);
}

// ⑩ NG 판정은 확인을 거치고 라인에서 빠진다
{
  const before = el.querySelectorAll('tbody tr').length;
  const ngBtn = buttons().find((b) => b.textContent === 'NG');
  assert.ok(ngBtn, 'NG 버튼이 없다');
  await click(ngBtn!);
  assert.ok(/폐기 처리합니다/.test(el.textContent ?? ''), 'NG 확인 다이얼로그가 안 떴다');
  await click(dialogConfirm());
  assert.equal(el.querySelectorAll('tbody tr').length, before - 1, 'NG 부품이 목록에서 안 빠졌다');
  assert.ok(MOCK.judgement.some((j) => j.verdict === 'NG'), 'judgement 에 NG 가 안 남았다');
  ok('NG 판정 — 확인 경유 · 라인에서 폐기');
}

// ⑪ TRANSPORT — 로봇암 수동제어: 값을 타이핑하지 않고 고른다 · 미검증은 잠긴다
{
  await click(find(/^로봇암 수동제어/)!);
  assert.ok(/동작 명령/.test(el.textContent ?? ''), '로봇암 화면이 아니다');
  assert.ok(!el.querySelector('input[type="text"]'), '🚨 IP·주소를 타이핑하는 입력란이 있다');
  assert.ok(/IP·포트를 여기서 입력하지 않습니다/.test(el.textContent ?? ''), '기존 수동제어와의 차이 설명이 없다');

  // 검증된 명령 → 실행 가능 · 보낼 값이 그대로 보인다
  const verified = find(/프린터 이송/);
  assert.ok(verified, '검증된 명령 버튼이 없다');
  await click(verified!);
  assert.ok(/reg 130 ← 1/.test(el.textContent ?? ''), '보낼 값이 안 보인다');
  assert.ok(/config\.py/.test(el.textContent ?? ''), '값의 출처가 안 보인다');
  const run = find(/^실행$/);
  assert.ok(run && !run.disabled, '검증된 명령인데 실행이 잠겨 있다');
  await click(run!);
  assert.ok(/설비가 실제로 움직입니다/.test(el.textContent ?? ''), '실행 확인 다이얼로그가 안 떴다');
  await click(dialogConfirm());
  assert.ok(/프린터 이송/.test(el.textContent ?? ''), '실행 로그가 없다');
  ok('로봇암 — 명령 선택 · 보낼 값/출처 표시 · 확인 후 실행');
}

// ⑫ 미검증 명령은 실행이 잠긴다 (W6 도 409 로 거부한다)
{
  const armB = find(/^로봇암 B/);
  assert.ok(armB, '로봇암 B 카드가 없다');
  await click(armB!);
  const unverified = find(/열기 1단계/);
  assert.ok(unverified, '미검증 명령 버튼이 없다');
  await click(unverified!);
  assert.ok(/임의값/.test(el.textContent ?? ''), '임의값이라는 표시가 없다');
  const locked = find(/미검증 — 실행할 수 없음/);
  assert.ok(locked?.disabled, '미검증인데 실행 버튼이 열려 있다');
  ok('미검증 명령 — 값만 보여주고 실행은 잠긴다');
}

// ⑬ 수동 반송 자원은 보낼 명령이 없다
{
  await click(find(/^경화 구간 수동 반송/)!);
  assert.ok(/사람이 옮깁니다/.test(el.textContent ?? ''), '수동 반송 안내가 없다');
  assert.ok(!find(/^실행$/), '수동 반송인데 실행 버튼이 있다');
  ok('수동 반송 자원 — 보낼 명령 없음');
}

// 그물 — 명령 로그에 방금 조작이 남았는가
{
  assert.ok(MOCK.log.some((r) => /투입/.test(r.text)), '명령 로그에 투입 기록이 없다');
  assert.ok(MOCK.log.some((r) => /시작/.test(r.text)), '명령 로그에 시작 기록이 없다');
  assert.ok(MOCK.log.some((r) => /NG/.test(r.text)), '명령 로그에 NG 기록이 없다');
  ok('명령 로그(감사 이력)에 조작이 남는다');
}

console.log(`\n✅ ${n}건 통과`);
process.exit(0);
