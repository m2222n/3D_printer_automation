/**
 * lineApi 투영 자체검사 — `services/lineApi.ts` 가 목업을 R1~R4 응답 모양으로
 * 제대로 접는지 본다. 러너·의존성을 새로 들이지 않는다(esbuild 는 vite 가 이미 갖고 있다).
 *
 *   cd frontend
 *   npx esbuild scripts/checkLineApi.ts --bundle --format=esm --outfile=/tmp/checkLineApi.mjs \
 *     && node /tmp/checkLineApi.mjs
 */

import assert from 'node:assert/strict';
import { getControlMenu, getNodes, getTransporters, getWip } from '../src/services/lineApi';
import { MOCK } from '../src/mocks/lineMock';

let n = 0;
const ok = (msg: string) => { n += 1; console.log('  ✓', msg); };

// ── R4 · 제어 서브 메뉴 ─────────────────────────────────────
{
  const { menu } = await getControlMenu();
  // 🚨 개수·이름은 토폴로지(라인)마다 다르다 — 목업(RESIN-1)은 6개, 실물(RESIN-1-ASIS)은 3개. 구조만 단정한다.
  assert.ok(menu.length > 0, '서브 탭이 하나도 없다');
  assert.ok(menu.every((r) => r.menu_label.trim().length > 0), '빈 이름의 탭이 있다');
  assert.ok(menu.every((r) => r.node_count > 0), 'node_count 0 인 탭이 있다');
  const steps = menu.map((r) => r.step_order);
  assert.deepEqual(steps, [...steps].sort((a, b) => a - b), '공정 순서대로여야 한다');
  assert.ok(menu.every((r) => r.node_ids.length === r.node_count), 'node_count 와 node_ids 가 어긋난다');
  assert.ok(!menu.some((r) => r.ui_kind == null), 'ui_kind 가 빈 탭이 있다');
  ok(`R4 서브 탭 ${menu.length}개 · 공정 순서 · 첫 탭 "${menu[0].menu_label}"`);
}

// ── R1 · 노드 현황 ──────────────────────────────────────────
{
  const { nodes } = await getNodes();
  assert.equal(nodes.length, MOCK.nodes.length, '노드가 빠졌다');

  const steps = nodes.map((r) => r.step_order);
  assert.deepEqual(steps, [...steps].sort((a, b) => a - b), 'step_order 정렬이 안 됐다');

  const racks = nodes.filter((r) => r.node_kind === 'RACK');
  const stations = nodes.filter((r) => r.node_kind === 'STATION');
  assert.ok(racks.length >= 4 && stations.length >= 6, `랙 ${racks.length} · 설비 ${stations.length}`);
  assert.ok(racks.every((r) => Array.isArray(r.slots) && r.slots.length > 0), '랙에 slots 가 없다');
  assert.ok(stations.every((r) => r.slots === null), '설비에 slots 가 붙었다');
  assert.ok(stations.every((r) => r.ui_kind !== null), '설비에 ui_kind 가 없다');
  assert.ok(racks.every((r) => r.ui_kind === null), '랙에 ui_kind 가 붙었다');

  const prt1 = nodes.find((r) => r.node_id === 'PRT-01')!;
  assert.equal(prt1.status, 'RUN');
  assert.equal(prt1.display_id, 'P13');
  assert.equal(prt1.progress_pct, Math.round((100 * 2100) / 5400), '진행률 계산이 다르다');
  assert.equal(prt1.part_label, 'PN-A-2026', '한 종이면 파트넘버');

  // v_unit_summary 규칙 — 여러 종이면 '혼재 N종'
  const wshDone = nodes.find((r) => r.node_id === 'RK-WSH-DONE-01')!;
  assert.equal(wshDone.part_label, null, '랙은 part_label 이 없다');
  assert.ok(wshDone.occupancy > 0 && wshDone.capacity === 8, `랙 적재 ${wshDone.occupancy}/${wshDone.capacity}`);

  // 목업이 못 내는 값은 비어 있어야 한다 (그럴싸한 값을 지어내면 안 된다)
  assert.ok(nodes.every((r) => r.settle_left_s === null && r.transport_wait_s === null),
    'settle/transport 대기는 서버(v_product_display)만 낼 수 있다');

  assert.ok(stations.every((r) => r.transporter_id !== null), '담당 반송 자원이 빈 설비가 있다');
  ok(`R1 노드 ${nodes.length} (랙 ${racks.length} · 설비 ${stations.length}) · 진행률 ${prt1.progress_pct}%`);
}

// ── R2 · 반송 자원 ──────────────────────────────────────────
{
  const { transporters } = await getTransporters();
  assert.equal(transporters.length, 3);
  const armA = transporters.find((t) => t.transporter_id === 'ARM-A')!;
  assert.ok(armA.queued > 0, '프린터·세척기 담당인데 대기 큐가 0');
  assert.equal(armA.kind, 'ROBOT');
  assert.ok(transporters.some((t) => t.kind === 'OPERATOR'), '수동 반송 구간이 없다');
  ok(`R2 반송 자원 ${transporters.length} · ARM-A 큐 ${armA.queued}`);
}

// ── R3 · 재공 파이프라인 ────────────────────────────────────
{
  const { wip } = await getWip();
  const batches = MOCK.units.filter((u) => u.unit_kind === 'BATCH').length;
  const groups = new Set(MOCK.units.filter((u) => u.unit_kind === 'PART' && u.group_id).map((u) => u.group_id)).size;
  assert.equal(wip.length, batches + groups + MOCK.boxes.length,
    `재공 행 = 배치 ${batches} + 묶음 ${groups} + 박스 ${MOCK.boxes.length}`);
  assert.ok(wip.some((r) => r.ref_kind === 'UNIT') && wip.some((r) => r.ref_kind === 'GROUP'));

  const onRack = wip.filter((r) => r.waiting);
  assert.ok(onRack.length > 0, '랙 대기가 하나도 없다');
  assert.ok(onRack.every((r) => MOCK.nodes.find((n2) => n2.node_id === r.node_id)?.node_kind === 'RACK'),
    'waiting 인데 랙이 아닌 곳에 있다');
  ok(`R3 재공 ${wip.length}행 (배치 ${batches} · 묶음 ${groups} · 박스 ${MOCK.boxes.length}) · 랙 대기 ${onRack.length}`);
}

// ── 그물이 찢어지는지 ───────────────────────────────────────
// "통과하는 검사" 와 "실패할 수 있는 검사" 는 다르다. 목업을 흔들어 투영이 따라오는지 본다.
{
  const before = (await getNodes()).nodes.find((r) => r.node_id === 'PRT-01')!;
  assert.equal(before.status, 'RUN');

  const saved = MOCK.units;
  MOCK.units = MOCK.units.filter((u) => u.node_id !== 'PRT-01');
  const empty = (await getNodes()).nodes.find((r) => r.node_id === 'PRT-01')!;
  assert.equal(empty.status, 'IDLE', '설비를 비웠는데 상태가 안 따라온다');
  assert.equal(empty.display_id, null);
  assert.equal(empty.progress_pct, null);
  assert.equal(empty.occupancy, 0);

  MOCK.units = saved;
  const back = (await getNodes()).nodes.find((r) => r.node_id === 'PRT-01')!;
  assert.equal(back.status, 'RUN', '되돌리기 실패');
  ok('그물 확인 — 설비를 비우면 RUN → IDLE · 진행률 null 로 따라온다');
}

console.log(`\n✅ ${n}건 통과`);
