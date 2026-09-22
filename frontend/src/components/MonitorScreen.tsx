/**
 * MONITOR — 프린터 · 세척기 · 경화기 · 빔피킹.
 * ①투입 대기 큐 ②설비 블록 ③투입 · 시작 · 중지 · 완료
 *
 * 🚨 설비 개수를 하드코딩하지 않는다 — 어느 설비를 보여줄지는 R4(v_control_menu)가 준다.
 */

import { useCallback, useEffect, useState } from 'react';
import { getInbound, getNodes, postMove, postState } from '../services/lineApi';
import type { InboundRow, NodeStatusRow, StateCommand } from '../types/line';
import { formatElapsed, statusLabel } from '../types/line';
import { ControlLayout, ControlSidePanel } from './ControlSidePanel';
import {
  BTN_DANGER, BTN_PRI, CARD, ConfirmDialog, HINT, INPUT, MONO, NUM, Pill, ROW, statusTone, Step,
} from './lineUi';

/** 시작 · 중지 · 완료 — 명세 W3 의 status 로 그대로 나간다. */
const COMMANDS: { key: string; label: string; status: StateCommand; danger?: boolean }[] = [
  { key: 'start', label: '시작', status: 'RUN' },
  { key: 'stop', label: '중지', status: 'HOLD', danger: true },
  { key: 'done', label: '완료', status: 'DONE' },
];

function canCommand(n: NodeStatusRow, key: string): boolean {
  if (n.occupancy === 0) return false;              // 빈 설비는 돌릴 수 없다
  if (key === 'start') return n.status !== 'RUN';
  if (key === 'stop') return n.status === 'RUN';
  if (key === 'done') return n.status === 'RUN' || n.status === 'HOLD';
  return false;
}

/** 가동 시간을 받는 설비인가 — 노드 속성이 정한다(공정 타입 분기 금지). */
function durationMinutes(n: NodeStatusRow): number | null {
  if (!(n.attrs as { duration_input?: boolean } | null)?.duration_input) return null;
  return Math.max(1, Math.round((n.std_cycle_s ?? 0) / 60));
}

type Pending =
  | { kind: 'load'; node: NodeStatusRow; row: InboundRow }
  | { kind: 'cmd'; node: NodeStatusRow; cmd: typeof COMMANDS[number]; minutes: number | null };

function InboundQueue({ rows, picked, onPick }: {
  rows: InboundRow[];
  picked: string | null;
  onPick: (key: string) => void;
}) {
  return (
    <div>
      <Step n={1} title="투입 대기 큐" note={`${rows.length}건`} />
      {rows.length === 0 ? (
        <p className={HINT}>들어올 것이 없습니다.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r, i) => (
            <button
              key={r.key}
              disabled={!r.ready}
              onClick={() => onPick(r.key)}
              className={`${ROW} w-full text-left flex items-center gap-3 ${
                r.key === picked ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'
              } ${r.ready ? '' : 'opacity-50 cursor-not-allowed'}`}
            >
              <span className={`${NUM} ${r.ready ? '' : 'bg-gray-100 text-gray-400'}`}>{i + 1}</span>
              <span className="flex-1 min-w-0">
                <span className="block font-medium text-gray-900 text-sm truncate">{r.label}</span>
                <span className={HINT}>{r.qty}개 · {r.from_label}{r.ready ? '' : ' · 앞의 것 먼저'}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700 mt-3">
        FIFO · 출처마다 앞의 것부터
      </div>
    </div>
  );
}

function StationBlock({ n, inbound, picked, onLoad, onCommand }: {
  n: NodeStatusRow;
  inbound: InboundRow[];
  picked: string | null;
  onLoad: (n: NodeStatusRow, row: InboundRow) => void;
  onCommand: (n: NodeStatusRow, cmd: typeof COMMANDS[number]) => void;
}) {
  const filled = n.occupancy > 0;
  const running = n.status === 'RUN';
  const pick = inbound.find((r) => r.key === picked && r.ready) ?? inbound.find((r) => r.ready) ?? null;
  const inbQty = inbound.reduce((a, r) => a + r.qty, 0);

  return (
    <div className={`${CARD} ${running ? 'bg-blue-50' : ''}`}>
      <div className={`px-4 py-3 border-b ${running ? 'bg-white/50' : 'bg-gray-50'} flex items-center justify-between gap-2`}>
        <span className="font-semibold text-gray-900 text-sm truncate">{n.label}</span>
        <Pill text={filled ? statusLabel(n.status) : '비어 있음'} tone={filled ? statusTone(n.status) : 'idle'} />
      </div>
      <div className="px-4 py-3 space-y-2">
        <p className="text-sm text-gray-700 min-h-10">
          {filled ? (
            <>
              <b className={MONO}>{n.display_ids.length > 1 ? `${n.display_ids.length}개` : n.display_id}</b>
              {' · '}
              {n.display_ids.length > 1 ? `${n.occupancy}개 적재` : `${n.part_label ?? '-'} ${n.part_qty}개`}
              <br />
              <span className={HINT}>경과 {formatElapsed(n.elapsed_s)} / 표준 {formatElapsed(n.std_cycle_s)}</span>
            </>
          ) : (
            <span className="text-gray-400">비어 있음 · 표준 {formatElapsed(n.std_cycle_s)}</span>
          )}
        </p>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-blue-500 transition-all duration-500" style={{ width: `${n.progress_pct ?? 0}%` }} />
        </div>
        <div className={`flex items-center justify-between ${HINT}`}>
          <span>대기 큐 {inbound.length}건{inbQty > 0 && ` · ${inbQty}개`}</span>
          <span>{pick && !filled ? `다음 ${pick.label}` : (inbound.length ? '왼쪽에서 선택' : '없음')}</span>
        </div>
        {filled ? (
          <div className="grid grid-cols-3 gap-1.5 pt-1">
            {COMMANDS.map((c) => (
              <button
                key={c.key}
                disabled={!canCommand(n, c.key)}
                onClick={() => onCommand(n, c)}
                className={`${c.danger ? BTN_DANGER : BTN_PRI} !px-2 !py-1.5 text-xs`}
              >
                {c.label}
              </button>
            ))}
          </div>
        ) : (
          <button disabled={!pick} onClick={() => pick && onLoad(n, pick)} className={`${BTN_PRI} w-full !py-1.5 text-xs`}>
            {pick ? `${pick.label} 투입` : '투입할 것 없음'}
          </button>
        )}
      </div>
    </div>
  );
}

export function MonitorScreen({ nodeIds, actor, onError }: {
  nodeIds: string[];
  actor: string;
  onError: (msg: string | null) => void;
}) {
  const [nodes, setNodes] = useState<NodeStatusRow[]>([]);
  const [inbound, setInbound] = useState<Record<string, InboundRow[]>>({});
  const [picked, setPicked] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [minutes, setMinutes] = useState('');
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((t) => t + 1);

  const key = nodeIds.join(',');
  const reload = useCallback(async () => {
    try {
      const { nodes: rows } = await getNodes();
      const mine = rows.filter((n) => key.split(',').includes(n.node_id));
      const queues = await Promise.all(mine.map((n) => getInbound(n.node_id)));
      setNodes(mine);
      setInbound(Object.fromEntries(mine.map((n, i) => [n.node_id, queues[i].inbound])));
      onError(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }, [key, onError]);

  // 명세 §6 — S4 는 3초. 투입 가능 여부가 남의 조작으로 바뀐다
  useEffect(() => {
    reload();
    const id = setInterval(reload, 3000);
    return () => clearInterval(id);
  }, [reload, tick]);

  const confirm = async () => {
    if (!pending) return;
    const res = pending.kind === 'load'
      ? await postMove({
          ...(pending.row.ref_kind === 'UNIT' ? { unit_id: pending.row.ref } : { group_id: pending.row.ref }),
          from_node: pending.row.from_node,
          to_node: pending.node.node_id,
          transporter_id: pending.node.transporter_id,
          actor,
        })
      : await postState(pending.node.node_id, {
          status: pending.cmd.status,
          duration_s: pending.minutes == null ? null : Math.round(Number(minutes || pending.minutes) * 60),
          actor,
        });
    if (!res.ok) onError(res.message);
    setPending(null);
    setPicked(null);
    refresh();
  };

  const groups: { label: string; nodes: NodeStatusRow[] }[] = [];
  nodes.forEach((n) => {
    let g = groups.find((x) => x.label === n.group_label);
    if (!g) { g = { label: n.group_label, nodes: [] }; groups.push(g); }
    g.nodes.push(n);
  });
  const merged: InboundRow[] = [];
  nodes.forEach((n) => (inbound[n.node_id] ?? []).forEach((r) => {
    if (!merged.some((x) => x.key === r.key)) merged.push(r);
  }));
  const running = nodes.filter((n) => n.status === 'RUN').length;

  const main = (
    <>
      <Step n={2} title="설비 상태 · 명령" note={`설비 ${nodeIds.length}대 · 가동 ${running}대`} />
      {groups.map((g) => (
        <div key={g.label} className="mb-5">
          <p className="text-sm text-gray-500 mb-2">
            {g.label} <span className="text-gray-400">{g.nodes.length}대</span>
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {g.nodes.map((n) => (
              <StationBlock
                key={n.node_id}
                n={n}
                inbound={inbound[n.node_id] ?? []}
                picked={picked}
                onLoad={(node2, row) => setPending({ kind: 'load', node: node2, row })}
                onCommand={(node2, cmd) => {
                  const d = cmd.key === 'start' ? durationMinutes(node2) : null;
                  setMinutes(d == null ? '' : String(d));
                  setPending({ kind: 'cmd', node: node2, cmd, minutes: d });
                }}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );

  return (
    <>
      <ControlLayout
        left={<InboundQueue rows={merged} picked={picked} onPick={setPicked} />}
        main={main}
        side={<ControlSidePanel nodeId={nodeIds[0]} onToggle={refresh} />}
      />

      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'load'
          ? `투입 — ${pending.node.label}`
          : pending ? `${pending.cmd.label} — ${pending.node.label}` : ''}
        confirmLabel={pending?.kind === 'load' ? '투입' : pending?.cmd.label ?? ''}
        danger={pending?.kind === 'cmd' && pending.cmd.danger}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      >
        {pending?.kind === 'load' ? (
          <>
            <b>{pending.row.label} ({pending.row.qty}개) 를 {pending.node.label} 에 넣습니다.</b>
            <br />
            <span className={HINT}>{pending.row.from_label} 에서 옵니다.</span>
          </>
        ) : pending ? (
          <>
            <b>{pending.node.label} 에 {pending.cmd.label} 명령을 보냅니다.</b>
            <br />
            <span className={HINT}>
              {pending.node.display_ids.length > 1 ? `${pending.node.display_ids.length}개 적재분` : pending.node.display_id}
              {' · '}{pending.node.status} → {pending.cmd.status}
            </span>
            {pending.minutes != null && (
              <div className="mt-3">
                <p className={`${HINT} mb-1`}>가동 시간 · 표준 {pending.minutes}분</p>
                <div className="flex items-center gap-2">
                  <input type="number" min={1} step={1} value={minutes}
                    onChange={(e) => setMinutes(e.target.value)} className={`${INPUT} !w-24 !text-left`} />
                  <span className={HINT}>분</span>
                </div>
              </div>
            )}
          </>
        ) : null}
      </ConfirmDialog>
    </>
  );
}
