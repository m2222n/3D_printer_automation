/**
 * PART_JUDGE — 서포트 제거대 · 치수검사.
 * ①대기 묶음 ②부품별 행 + 측정값 ③OK/NG ④박스 적재·마감
 *
 * 🚨 측정란은 **노드 속성(attrs.measure)** 이 있으면 뜬다 — 공정 타입으로 분기하지 않는다.
 * 🚨 NG 는 판정 + 폐기가 **한 번의 호출(W4)** 이다. 나눠 부르면 판정만 남고 부품이 라인에 남는다.
 */

import { useCallback, useEffect, useState } from 'react';
import { getGroups, getNodes, getNodeParts, postCommand, postJudgement, postMove, readOpenBox } from '../services/lineApi';
import type { GroupRow, NodeStatusRow, PartJudgeRow } from '../types/line';
import { ControlLayout, ControlSidePanel, interlockOk } from './ControlSidePanel';
import { BTN, CARD, ConfirmDialog, HINT, INPUT, MONO, Panel, Pill, ROW, Step } from './lineUi';

/** 박스로 담기는 다음 랙. R1 의 attrs.count_by_group 으로 고른다. */
function boxRackOf(nodes: NodeStatusRow[], me: NodeStatusRow | undefined): NodeStatusRow | null {
  if (!me) return null;
  return nodes.find((n) =>
    n.node_kind === 'RACK' && n.step_order === me.step_order + 1
    && (n.attrs as { count_by_group?: boolean } | null)?.count_by_group === true) ?? null;
}

export function PartJudgeScreen({ nodeId, actor }: { nodeId: string; actor: string }) {
  const [parts, setParts] = useState<PartJudgeRow[]>([]);
  const [groups, setGroups] = useState<GroupRow[]>([]);
  const [boxRack, setBoxRack] = useState<NodeStatusRow | null>(null);
  const [measure, setMeasure] = useState<Record<string, string>>({});
  const [askNg, setAskNg] = useState<PartJudgeRow | null>(null);
  const [askClose, setAskClose] = useState(false);
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((t) => t + 1);

  const lock = interlockOk(nodeId);

  const reload = useCallback(async () => {
    const [{ parts: ps }, { groups: gs }, { nodes }] = await Promise.all([
      getNodeParts(nodeId), getGroups(nodeId), getNodes(),
    ]);
    setParts(ps);
    setGroups(gs);
    setBoxRack(boxRackOf(nodes, nodes.find((n) => n.node_id === nodeId)));
  }, [nodeId]);

  useEffect(() => { reload(); }, [reload, tick]);

  const spec = parts[0]?.measure_spec ?? null;
  const decided = parts.filter((p) => p.verdict).length;

  /** 측정값 — 스펙이 있을 때만 판정에 싣는다. jsonb 키 이름은 스펙이 준다. */
  const valueOf = (p: PartJudgeRow): Record<string, number> | null => {
    if (!p.measure_spec) return null;
    const v = measure[p.unit_id];
    return v === undefined || v === '' ? null : { [p.measure_spec.key]: Number(v) };
  };

  const inTolerance = (p: PartJudgeRow): boolean | null => {
    const v = measure[p.unit_id];
    const nominal = p.tol?.nominal_mm;
    if (v === undefined || v === '' || nominal == null) return null;
    return Math.abs(Number(v) - nominal) <= (p.tol?.tol_mm ?? Infinity);
  };

  /** OK — 판정(W4) 뒤 다음 랙이 박스 단위면 이어서 합류(W2 join_group). */
  const judgeOk = async (p: PartJudgeRow) => {
    await postJudgement({ unit_id: p.unit_id, node_id: nodeId, verdict: 'OK', value: valueOf(p), note: null, actor });
    if (boxRack) {
      const box = readOpenBox(boxRack.node_id);
      await postMove({ unit_id: p.unit_id, from_node: nodeId, to_node: boxRack.node_id, join_group: box.group_id, actor });
    }
    refresh();
  };

  const judgeNg = async (p: PartJudgeRow) => {
    await postJudgement({ unit_id: p.unit_id, node_id: nodeId, verdict: 'NG', value: valueOf(p), note: null, actor });
    setAskNg(null);
    refresh();
  };

  const allOk = async () => {
    for (const p of parts.filter((x) => !x.verdict)) await judgeOk(p);
    refresh();
  };

  const box = boxRack ? readOpenBox(boxRack.node_id) : null;

  const left = (
    <div>
      <Step n={1} title="대기 묶음" />
      {groups.length === 0 ? (
        <p className={HINT}>대기 중인 부품이 없습니다.</p>
      ) : (
        <div className="space-y-2">
          {groups.map((g) => (
            <div key={g.group_id} className={`${ROW} border-blue-500 ring-1 ring-blue-500`}>
              <p className={`${MONO} font-semibold text-gray-900`}>{g.group_id}</p>
              <p className={`${HINT} mt-0.5`}>{g.unit_qty}개 대기</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const main = (
    <>
      <Step n={2} title="부품별 판정" note={`대기 ${parts.length}개 · 판정 ${decided}개`} />
      {!lock && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">
          인터록 미충족 — 판정 입력이 잠겨 있습니다.
        </div>
      )}
      <button className={`${BTN} mb-3`} disabled={!lock || parts.length === 0} onClick={allOk}>
        일괄 · 남은 부품 전체 OK
      </button>
      {parts.length === 0 ? (
        <div className="py-10 text-center text-gray-400 text-sm">판정할 부품이 없습니다.</div>
      ) : (
        <div className={`${CARD} ${lock ? '' : 'opacity-40 pointer-events-none'}`}>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium w-10">#</th>
                <th className="px-3 py-2 text-left font-medium">부품</th>
                <th className="px-3 py-2 text-left font-medium">파트넘버</th>
                {spec && <th className="px-3 py-2 text-left font-medium w-32">{spec.label} ({spec.unit})</th>}
                <th className="px-3 py-2 text-left font-medium w-32">판정</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {parts.map((p, i) => {
                const tol = inTolerance(p);
                return (
                  <tr key={p.unit_id} className="hover:bg-gray-50">
                    <td className={`px-3 py-2 ${MONO} text-gray-400`}>{String(i + 1).padStart(2, '0')}</td>
                    <td className={`px-3 py-2 ${MONO} font-semibold text-gray-900`}>{p.display_id}</td>
                    <td className="px-3 py-2 text-gray-700">
                      {p.part_no}<span className={`${HINT} ml-1`}>{p.part_name}</span>
                    </td>
                    {spec && (
                      <td className="px-3 py-2">
                        <input
                          type="number" step="0.01"
                          value={measure[p.unit_id] ?? ''}
                          placeholder={p.tol?.nominal_mm == null ? '' : String(p.tol.nominal_mm)}
                          onChange={(e) => setMeasure((s) => ({ ...s, [p.unit_id]: e.target.value }))}
                          className={`${INPUT} ${tol === false ? 'border-red-400 text-red-600' : ''}`}
                        />
                        {p.tol?.tol_mm != null && <span className={`${HINT} ml-1`}>±{p.tol.tol_mm}</span>}
                      </td>
                    )}
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <button
                          onClick={() => judgeOk(p)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${
                            p.verdict === 'OK' ? 'bg-green-600 border-green-600 text-white' : 'border-gray-200 text-gray-500 hover:bg-gray-100'}`}
                        >OK</button>
                        <button
                          onClick={() => setAskNg(p)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${
                            p.verdict === 'NG' ? 'bg-red-600 border-red-600 text-white' : 'border-gray-200 text-gray-500 hover:bg-gray-100'}`}
                        >NG</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );

  const side = (
    <>
      <div>
        <Step n={3} title="다음 공정" />
        {boxRack && box && (
          <Panel
            title={`박스 적재 → ${boxRack.label}`}
            right={<Pill text={`${box.count} / ${box.capacity}`} tone={box.count >= box.capacity ? 'ok' : 'run'} />}
          >
            <p className={HINT}>OK 판정한 부품이 담깁니다. {box.capacity}개가 차면 자동 마감.</p>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full rounded-full bg-blue-500 transition-all duration-500"
                style={{ width: `${box.capacity ? Math.round((box.count / box.capacity) * 100) : 0}%` }} />
            </div>
            <p className="text-sm text-gray-700">{box.count ? `${box.group_id} · ${box.count}개` : '비어 있음'}</p>
            <button className={`${BTN} w-full`} disabled={box.count === 0} onClick={() => setAskClose(true)}>
              박스 수동 마감
            </button>
          </Panel>
        )}
      </div>
      <ControlSidePanel nodeId={nodeId} onToggle={refresh} />
    </>
  );

  return (
    <>
      <ControlLayout left={left} main={main} side={side} />

      <ConfirmDialog
        open={askNg !== null}
        title={`NG 판정 — ${askNg?.display_id ?? ''}`}
        confirmLabel="NG 확정"
        danger
        onConfirm={() => askNg && judgeNg(askNg)}
        onCancel={() => setAskNg(null)}
      >
        <b>{askNg?.display_id} 을(를) 폐기 처리합니다.</b>
        <br />
        <span className={HINT}>라인에서 폐기됩니다. 되돌릴 수 없습니다.</span>
      </ConfirmDialog>

      <ConfirmDialog
        open={askClose}
        title={`박스 수동 마감 — ${box?.group_id ?? ''}`}
        confirmLabel="마감"
        onConfirm={async () => {
          if (boxRack) await postCommand({ kind: 'GROUP_CLOSE', target: boxRack.node_id, payload: { reason: '수동 마감' }, actor });
          setAskClose(false);
          refresh();
        }}
        onCancel={() => setAskClose(false)}
      >
        <b>{box?.group_id} 를 {box?.count}개로 마감합니다.</b>
        <br />
        <span className={HINT}>미달 상태로 다음 공정에 보냅니다.</span>
      </ConfirmDialog>
    </>
  );
}
