/**
 * BATCH_SPLIT — 부품 분리대.
 * ①랙 → ②칸 → ③배치 FIFO 대기열 → ④파트별 OK/NG → ⑤묶음 넘기기
 *
 * 🚨 분리 화면은 **부품 ID 를 쓰지 않는다** — 그 시점에 부품은 존재하지 않고
 *    작업자가 손에 든 물건과 매칭할 수도 없다. **파트넘버 × 수량**으로 판정한다.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  getGroups, getRackSlots, getSlotQueue, getSourceRacks, getNodes, postMove, postSplit,
} from '../services/lineApi';
import type { GroupRow, NodeStatusRow, RackRow, SlotQueueRow, SlotRow } from '../types/line';
import { MOCK, NG_REASONS_OF } from '../mocks/lineMock';
import { ControlLayout, ControlSidePanel, interlockOk } from './ControlSidePanel';
import {
  BTN, BTN_PRI, ConfirmDialog, HINT, INPUT, MONO, NUM, Panel, Pill, ROW, Step,
} from './lineUi';

interface JudgeInput { ok: number; ng: number; reason: string }

/** 파트별 판정 행 — 화면이 만든다(부품 unit 이 아직 없으므로). */
function rowsOf(batch: SlotQueueRow | null, input: Record<string, JudgeInput>) {
  if (!batch) return [];
  return batch.contents.map((c) => {
    const s = input[c.part_no];
    return {
      part_no: c.part_no,
      name: c.part_name,
      qty: c.qty,
      ok: s ? s.ok : c.qty,
      ng: s ? s.ng : 0,
      reason: s ? s.reason : '',
      touched: s != null,
    };
  });
}
type Row = ReturnType<typeof rowsOf>[number];

const rowValid = (r: Row) => r.ok + r.ng === r.qty && (r.ng ? !!r.reason : true);

export function BatchSplitScreen({ nodeId, actor }: { nodeId: string; actor: string }) {
  const [racks, setRacks] = useState<RackRow[]>([]);
  const [slots, setSlots] = useState<SlotRow[]>([]);
  const [queue, setQueue] = useState<SlotQueueRow[]>([]);
  const [groups, setGroups] = useState<GroupRow[]>([]);
  const [nextNodes, setNextNodes] = useState<NodeStatusRow[]>([]);

  const [rack, setRack] = useState<string | null>(null);
  const [slot, setSlot] = useState<number | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [input, setInput] = useState<Record<string, JudgeInput>>({});
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [ask, setAsk] = useState<null | { kind: 'split' } | { kind: 'handoff'; group: GroupRow; to: NodeStatusRow }>(null);
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((t) => t + 1);

  const lock = interlockOk(nodeId);

  // 랙 목록 · 묶음 · 다음 공정
  const reload = useCallback(async () => {
    const [{ racks: rs }, { groups: gs }, { nodes }] = await Promise.all([
      getSourceRacks(nodeId), getGroups(nodeId), getNodes(),
    ]);
    setRacks(rs);
    setGroups(gs);
    // 🚨 다음 공정 후보는 R1 에서 온다 — 설비 개수를 하드코딩하지 않는다
    const step = nodes.find((n) => n.node_id === nodeId)?.step_order ?? 0;
    setNextNodes(nodes.filter((n) => n.node_kind === 'STATION' && n.step_order === step + 1));
  }, [nodeId]);

  useEffect(() => { reload(); }, [reload, tick]);

  useEffect(() => {
    if (racks.length && (!rack || !racks.some((r) => r.node_id === rack))) setRack(racks[0].node_id);
  }, [racks, rack]);

  useEffect(() => {
    if (!rack) { setSlots([]); return; }
    getRackSlots(rack).then((r) => setSlots(r.slots));
  }, [rack, tick]);

  useEffect(() => {
    if (!rack || slot == null) { setQueue([]); return; }
    getSlotQueue(rack, slot).then((r) => setQueue(r.queue));
  }, [rack, slot, tick]);

  // 고른 것이 사라지면 놓는다
  useEffect(() => {
    if (slot != null && !slots.some((s) => s.slot_no === slot && s.occupancy > 0)) setSlot(null);
  }, [slots, slot]);
  useEffect(() => {
    if (open && !queue.some((b) => b.unit_id === open)) setOpen(queue.find((b) => b.retrievable)?.unit_id ?? null);
    else if (!open) setOpen(queue.find((b) => b.retrievable)?.unit_id ?? null);
  }, [queue, open]);

  const batch = queue.find((b) => b.unit_id === open) ?? null;
  const rows = rowsOf(batch, input);
  const sum = rows.reduce((a, r) => ({ qty: a.qty + r.qty, ok: a.ok + r.ok, ng: a.ng + r.ng }), { qty: 0, ok: 0, ng: 0 });
  const bad = rows.filter((r) => !rowValid(r));
  const canDone = rows.length > 0 && lock && bad.length === 0;
  const untouched = rows.filter((r) => !r.touched);
  const target = groups[0]?.capacity ?? 0;

  const setField = (pn: string, f: keyof JudgeInput, v: string) => {
    setInput((s) => {
      const base = s[pn] ?? { ok: rows.find((r) => r.part_no === pn)?.qty ?? 0, ng: 0, reason: '' };
      return { ...s, [pn]: { ...base, [f]: f === 'reason' ? v : Math.max(0, Number(v) || 0) } };
    });
  };

  const doSplit = async () => {
    if (!batch) return;
    const res = await postSplit(batch.unit_id, {
      node_id: nodeId,
      outputs: rows.filter((r) => r.ok > 0).map((r) => ({ part_no: r.part_no, qty: r.ok })),
      scraps: rows.filter((r) => r.ng > 0).map((r) => ({ part_no: r.part_no, qty: r.ng, reason: r.reason })),
      group_id: openGroup,                   // null 이면 새 묶음 — 서버 기본값에 맡기지 않는다
      actor,
    });
    if (res.ok && res.group_id) {
      setOpenGroup(target > 0 && sum.ok >= target ? null : res.group_id);
    }
    setInput({});
    setOpen(null);
    setAsk(null);
    refresh();
  };

  const doHandoff = async (g: GroupRow, to: NodeStatusRow) => {
    await postMove({ group_id: g.group_id, from_node: nodeId, to_node: to.node_id, actor });
    if (openGroup === g.group_id) setOpenGroup(null);
    setAsk(null);
    refresh();
  };

  // ── 좌 ──
  const left = (
    <>
      <div>
        <Step n={1} title="랙 선택" />
        {racks.length === 0 ? (
          <p className={HINT}>직전 공정 랙이 없습니다.</p>
        ) : racks.length === 1 ? (
          <div className={`${ROW} border-dashed`}>
            <p className="font-medium text-gray-900 text-sm">{racks[0].label}</p>
            <p className={`${HINT} mt-0.5`}>적재 {racks[0].occupancy}/{racks[0].capacity} · 칸 {racks[0].slot_count}개 · 자동 선택</p>
          </div>
        ) : (
          <div className="space-y-2">
            {racks.map((r) => (
              <button
                key={r.node_id}
                onClick={() => { setRack(r.node_id); setSlot(null); setOpen(null); }}
                className={`${ROW} w-full text-left ${r.node_id === rack ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}`}
              >
                <p className="font-medium text-gray-900 text-sm">{r.label}</p>
                <p className={`${HINT} mt-0.5`}>적재 {r.occupancy}/{r.capacity} · 칸 {r.slot_count}개</p>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="mt-5">
        <Step n={2} title="칸 선택" note={`${slots.length}칸`} />
        <div className="space-y-2">
          {slots.map((s) => (
            <button
              key={s.slot_no}
              disabled={s.occupancy === 0}
              onClick={() => { setSlot(s.slot_no); setOpen(null); }}
              className={`${ROW} w-full text-left ${s.slot_no === slot ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'} ${
                s.occupancy ? '' : 'opacity-50 cursor-not-allowed'}`}
            >
              <p className="font-medium text-gray-900 text-sm">칸 {s.slot_no} · {s.occupancy}/{s.capacity}</p>
              <p className={`${HINT} mt-0.5 truncate`}>{s.occupancy ? s.contents.join(' → ') : '비어 있음'}</p>
            </button>
          ))}
        </div>
      </div>
    </>
  );

  // ── 중앙 ──
  const main = (
    <>
      <Step n={3} title="배치 대기열" note={slot == null ? '' : `칸 ${slot} · ${queue.length}장 · FIFO`} />
      {slot == null ? (
        <p className={`${HINT} py-4`}>칸을 고르세요.</p>
      ) : (
        <div className="space-y-2">
          {queue.map((b) => (
            <button
              key={b.unit_id}
              disabled={!b.retrievable}
              onClick={() => { setOpen(b.unit_id); setInput({}); }}
              className={`${ROW} w-full text-left flex items-center gap-3 ${
                b.unit_id === open ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'} ${
                b.retrievable ? '' : 'opacity-50 cursor-not-allowed'}`}
            >
              <span className={`${NUM} ${b.retrievable ? '' : 'bg-gray-100 text-gray-400'}`}>{b.pos_no}</span>
              <span className="flex-1 min-w-0">
                <span className="block font-medium text-gray-900 text-sm">{b.display_id}</span>
                <span className="flex flex-wrap items-center gap-1 mt-1">
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-900 text-white">{b.kinds}종</span>
                  {b.contents.map((c) => (
                    <span key={c.part_no} className={`px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 ${MONO}`}>
                      {c.part_no} ×{c.qty}
                    </span>
                  ))}
                </span>
              </span>
              <span className="text-right">
                <span className="block text-sm font-semibold text-gray-900">{b.total_qty}개</span>
                <span className={HINT}>{b.retrievable ? '지금 작업' : '앞 배치 먼저'}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-6">
        {batch ? (
          <>
            <Step n={4} title="파트별 판정 · 배치 완료" note={`${batch.display_id} · 총 ${sum.qty}개`} />
            {!lock && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">
                인터록 미충족 — 판정 입력이 잠겨 있습니다.
              </div>
            )}
            <button
              className={`${BTN} mb-3`}
              disabled={!lock || untouched.length === 0}
              onClick={() => setInput((s) => {
                const next = { ...s };
                untouched.forEach((r) => { next[r.part_no] = { ok: r.qty, ng: 0, reason: '' }; });
                return next;
              })}
            >
              {untouched.length
                ? `남은 ${untouched.length}종 전체 OK (${untouched.reduce((a, r) => a + r.qty, 0)}개)`
                : '전부 입력됨'}
            </button>
            <div className={`space-y-2 ${lock ? '' : 'opacity-40 pointer-events-none'}`}>
              {rows.map((r) => {
                const mismatch = r.ok + r.ng !== r.qty;
                return (
                  <div key={r.part_no} className={`${ROW} ${mismatch ? 'border-red-300' : 'border-gray-200'}`}>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <p className={`${MONO} font-semibold text-gray-900`}>{r.part_no}</p>
                        <p className={HINT}>
                          {r.name} · 투입 {r.qty}개
                          {mismatch && <span className="text-red-600 font-medium"> · 합계 불일치</span>}
                        </p>
                      </div>
                      <div className="w-20">
                        <p className={`${HINT} mb-0.5 text-center`}>OK</p>
                        <input type="number" min={0} max={r.qty} value={r.ok}
                          onChange={(e) => setField(r.part_no, 'ok', e.target.value)}
                          className={`${INPUT} ${mismatch ? 'border-red-300' : ''}`} />
                      </div>
                      <div className="w-20">
                        <p className={`${HINT} mb-0.5 text-center`}>NG</p>
                        <input type="number" min={0} max={r.qty} value={r.ng}
                          onChange={(e) => setField(r.part_no, 'ng', e.target.value)}
                          className={`${INPUT} ${mismatch ? 'border-red-300' : ''} ${r.ng ? 'text-red-600 font-semibold' : ''}`} />
                      </div>
                    </div>
                    {r.ng > 0 && (
                      <div className="flex items-center gap-2 mt-2 pt-2 border-t border-dashed border-gray-200">
                        <span className="text-xs font-medium text-red-600">NG {r.ng}개 사유</span>
                        <select value={r.reason} onChange={(e) => setField(r.part_no, 'reason', e.target.value)}
                          className="px-2 py-1 rounded-lg border border-gray-200 text-xs">
                          <option value="">- 선택 -</option>
                          {NG_REASONS_OF(MOCK).map((x) => <option key={x}>{x}</option>)}
                        </select>
                        {!r.reason && <span className={HINT}>사유를 골라야 완료할 수 있습니다</span>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {bad.length > 0 && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700 mt-3">
                {bad.map((r) => (
                  <div key={r.part_no}>
                    {r.part_no} — {r.ok + r.ng !== r.qty
                      ? `OK ${r.ok} + NG ${r.ng} = ${r.ok + r.ng} (투입 ${r.qty})`
                      : 'NG 사유 미선택'}
                  </div>
                ))}
              </div>
            )}
            <div className="flex items-center gap-3 mt-4">
              <span className="text-sm text-gray-500 flex-1">
                합계 <b className="text-gray-900">OK {sum.ok}</b> · <b className="text-gray-900">NG {sum.ng}</b> / 총 {sum.qty}개
              </span>
              <button className={BTN_PRI} disabled={!canDone} onClick={() => setAsk({ kind: 'split' })}>
                배치 완료 등록
              </button>
            </div>
          </>
        ) : (
          <>
            <Step n={4} title="파트별 판정 · 배치 완료" />
            <p className={`${HINT} py-4`}>대기열에서 배치를 고르세요.</p>
          </>
        )}
      </div>
    </>
  );

  // ── 우 ──
  const side = (
    <>
      <div>
        <Step n={5} title="분리 완료 · 넘기기" />
        {groups.length === 0 ? (
          <p className={HINT}>배치를 완료하면 부품이 묶음으로 쌓입니다.</p>
        ) : groups.map((g) => {
          const full = g.capacity > 0 && g.unit_qty >= g.capacity;
          return (
            <Panel key={g.group_id} title={`묶음 ${g.group_id}`}
              right={<Pill text={`${g.unit_qty}${g.capacity ? ` / ${g.capacity}` : ''}`} tone={full ? 'warn' : 'run'} />}>
              {g.sources.map((sc) => (
                <div key={sc.parent_display_id} className="flex items-baseline gap-2 text-xs py-1 border-b border-dashed border-gray-100 last:border-0">
                  <span className={`${MONO} font-semibold text-gray-900`}>{sc.parent_display_id}</span>
                  <span className="text-gray-500">
                    {Object.entries(sc.parts).map(([pn, q]) => `${pn} ${q}개`).join(' · ')}
                  </span>
                </div>
              ))}
              {g.group_id === openGroup && (
                <>
                  <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700">
                    누적 중{g.capacity ? ` · 남은 자리 ${Math.max(0, g.capacity - g.unit_qty)}개` : ''}
                  </div>
                  <button className={`${BTN} w-full`} onClick={() => setOpenGroup(null)}>새 묶음으로 시작</button>
                </>
              )}
              {full && (
                <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
                  정원 {g.capacity}개가 찼습니다.
                </div>
              )}
              {nextNodes.map((nx) => (
                <button key={nx.node_id} className={`${BTN_PRI} w-full`} onClick={() => setAsk({ kind: 'handoff', group: g, to: nx })}>
                  묶음 마감 · {nx.label}로 넘기기
                </button>
              ))}
            </Panel>
          );
        })}
      </div>
      <ControlSidePanel nodeId={nodeId} onToggle={refresh} />
    </>
  );

  return (
    <>
      <ControlLayout left={left} main={main} side={side} />

      <ConfirmDialog
        open={ask?.kind === 'split'}
        title={`배치 완료 등록 — ${batch?.display_id ?? ''}`}
        confirmLabel="배치 완료"
        onConfirm={doSplit}
        onCancel={() => setAsk(null)}
      >
        <b>OK {sum.ok}개가 부품으로 등록됩니다.{sum.ng ? ` NG ${sum.ng}개는 폐기 처리됩니다.` : ''}</b>
        <div className="mt-2 space-y-0.5">
          {rows.map((r) => (
            <div key={r.part_no} className="text-sm">
              <b className={MONO}>{r.part_no}</b> OK {r.ok} / NG {r.ng}
              {r.ng > 0 && <span className="text-red-600"> ({r.reason})</span>}
            </div>
          ))}
        </div>
        <p className={`${HINT} mt-2`}>
          부품이 {batch?.display_id}-S… 로 생성돼{' '}
          {openGroup ? <>묶음 <b>{openGroup}</b> 에 이어 담깁니다</> : <b>새 묶음</b>}
          . 되돌릴 수 없습니다.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={ask?.kind === 'handoff'}
        title={ask?.kind === 'handoff' ? `다음 단계로 넘기기 — ${ask.to.label}` : ''}
        confirmLabel="넘기기"
        onConfirm={() => ask?.kind === 'handoff' && doHandoff(ask.group, ask.to)}
        onCancel={() => setAsk(null)}
      >
        {ask?.kind === 'handoff' && (
          <b>{ask.group.group_id} ({ask.group.unit_qty}개) 를 {ask.to.label} 로 넘깁니다.</b>
        )}
      </ConfirmDialog>
    </>
  );
}
