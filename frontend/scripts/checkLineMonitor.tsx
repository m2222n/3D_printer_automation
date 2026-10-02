/**
 * 라인 모니터링 탭 렌더 검사 — 와이어프레임(`check_merged.js` ③~⑤)이 보던 것을
 * React 산출 DOM 에 대고 다시 본다. 러너를 새로 들이지 않는다(jsdom + esbuild).
 *
 *   cd frontend
 *   NODE_PATH=/tmp/node_modules npx esbuild scripts/checkLineMonitor.tsx --bundle --platform=node \
 *     --format=esm --external:jsdom --outfile=/tmp/checkLineMonitor.mjs && \
 *   NODE_PATH=/tmp/node_modules node /tmp/checkLineMonitor.mjs
 */

import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
const g = globalThis as unknown as Record<string, unknown>;
g.window = dom.window;
g.document = dom.window.document;
// node 24 의 navigator 는 getter 전용이라 대입이 안 된다
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
g.HTMLElement = dom.window.HTMLElement;
g.Element = dom.window.Element;
g.Node = dom.window.Node;
g.SVGElement = dom.window.SVGElement;
g.IS_REACT_ACT_ENVIRONMENT = false;

const { createElement } = await import('react');
const { createRoot } = await import('react-dom/client');
const { LineMonitorPage } = await import('../src/components/LineMonitorPage');

const el = dom.window.document.getElementById('root')!;
const root = createRoot(el);
root.render(createElement(LineMonitorPage));
await new Promise((r) => setTimeout(r, 120));   // 목업 promise + setState 반영

const D = dom.window.document;
let n = 0;
const ok = (m: string) => { n += 1; console.log('  ✓', m); };
const text = () => el.textContent ?? '';

// ③' 본문 폭 컨테이너 — 기존 탭과 같은 규약(안 맞으면 새 탭만 화면 끝까지 퍼진다)
assert.ok(el.querySelector('main.max-w-7xl'), '본문 폭 컨테이너(max-w-7xl)가 없다');

// ③ 요약 · 반송 패널
assert.ok(/공정 설비/.test(text()), '요약 타일이 없다');
assert.ok(/랙 대기/.test(text()), '랙 대기 타일이 없다');
assert.ok(/로봇암 A/.test(text()), '반송 패널이 없다');
assert.ok(/수동 반송/.test(text()), '수동 반송 자원이 없다');
ok('요약 타일 4 + 반송 자원 3');

// ④ 흐름 — 랙(윗단) · 설비(아랫단) · 사이 화살표
{
  const cells = Array.from(el.querySelectorAll('[style*="grid-row"]')) as HTMLElement[];
  const racks = cells.filter((c) => /grid-row: 1/.test(c.getAttribute('style') ?? ''));
  const stations = cells.filter((c) => /grid-row: 3/.test(c.getAttribute('style') ?? ''));
  const links = cells.filter((c) => /grid-row: 2/.test(c.getAttribute('style') ?? ''));
  assert.ok(racks.length >= 4, `윗단 랙이 모자라다: ${racks.length}`);
  assert.ok(stations.length >= 6, `아랫단 설비가 모자라다: ${stations.length}`);
  racks.forEach((c) => assert.ok(/랙/.test(c.textContent ?? ''), `윗단에 랙이 아닌 것: ${c.textContent?.slice(0, 20)}`));
  assert.equal(links.length, racks.length + stations.length - 1, '연결자 수가 열 수와 안 맞는다');
  links.forEach((c) => assert.ok(c.querySelector('polygon'), '화살촉이 없는 구간이 있다'));
  // 랙 구간은 '대기', 설비 구간은 '완료' — 가동 중인 개수를 '대기'로 부르면 오독한다
  links.forEach((c) => assert.ok(/(대기|완료) \d/.test(c.textContent ?? ''), '연결자에 대기/완료 수가 없다'));
  assert.ok(links.some((c) => /대기 \d/.test(c.textContent ?? '')), '랙 구간 대기 수가 없다');
  assert.ok(links.some((c) => /완료 \d/.test(c.textContent ?? '')), '설비 구간 완료 수가 없다');
  const manual = links.filter((c) => /작업자/.test(c.textContent ?? ''));
  assert.ok(manual.length > 0, '수동 반송 구간 표시가 없다');
  assert.ok(manual.every((c) => c.querySelector('path')?.getAttribute('stroke-dasharray')),
    '수동 구간이 점선이 아니다');
  assert.ok(links.filter((c) => /로봇암/.test(c.textContent ?? '')).length > 0, '로봇 반송 구간 표시가 없다');
  // 프린터 열은 베이 4개
  const prt = stations.find((c) => /프린터/.test(c.textContent ?? ''))!;
  assert.ok(/설비 4/.test(prt.textContent ?? ''), '프린터가 4대로 안 묶였다');
  ok(`흐름 — 랙 ${racks.length}(윗단) · 설비 ${stations.length}(아랫단) · 구간 ${links.length}(수동 ${manual.length})`);
}

// ⑤ 파이프라인 탭
{
  const tabs = Array.from(el.querySelectorAll('button')) as HTMLButtonElement[];
  const pipe = tabs.find((b) => /플레이트 파이프라인/.test(b.textContent ?? ''))!;
  assert.ok(pipe, '파이프라인 서브 탭이 없다');
  pipe.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 80));

  const rows = el.querySelectorAll('tbody tr');
  const heads = el.querySelectorAll('thead th');
  assert.ok(rows.length > 3, `파이프라인 행이 없다: ${rows.length}`);
  assert.ok(heads.length >= 7, `공정 열이 모자라다: ${heads.length}`);
  assert.ok(/대기/.test(el.textContent ?? ''), '랙 대기 표시가 없다');
  ok(`파이프라인 ${rows.length}행 × ${heads.length - 1}공정`);
}

// 그물 — 흐름 탭으로 돌아오면 다시 흐름이 그려진다
{
  const flowTab = (Array.from(el.querySelectorAll('button')) as HTMLButtonElement[])
    .find((b) => /설비 · 반송/.test(b.textContent ?? ''))!;
  flowTab.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(el.querySelectorAll('tbody tr').length, 0, '흐름 탭인데 파이프라인 표가 남아 있다');
  assert.ok(el.querySelector('polygon'), '흐름 탭인데 화살표가 없다');
  ok('서브 탭 전환 — 흐름 ↔ 파이프라인');
}

// 갱신 시각 배지 (실패를 삼키지 않는다 — 명세 §6)
assert.ok(/기준/.test(text()), '마지막 갱신 시각 표시가 없다');
ok('마지막 갱신 시각 표시');

console.log(`\n✅ ${n}건 통과`);
root.unmount();
process.exit(0);
