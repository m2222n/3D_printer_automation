/**
 * 라인 모니터링 탭 — 「설비 · 반송」 + 「플레이트 파이프라인」
 * 와이어프레임 = `docs/plan/20260916_fe_merged.html` 의 `wf-panel-line`.
 *
 * 데이터는 `services/lineApi` 만 통한다(R1 노드 · R2 반송 · R3 재공).
 * 갱신 주기는 API 명세 §6 — 흐름 5초 · 파이프라인 15초. WebSocket 은 쓰지 않는다.
 * 🚨 조회 실패를 삼키지 않는다 — 마지막 갱신 시각과 실패 배지를 띄운다.
 */

import { useCallback, useEffect, useState } from 'react';
import { getNodes, getTransporters, getWip } from '../services/lineApi';
import type { NodeStatusRow, TransporterRow, WipRow } from '../types/line';
import { formatElapsed, statusLabel } from '../types/line';
import { CARD, HINT, MONO, Pill, statusTone, SubTab, type Tone } from './lineUi';
import { LineFlowBoard } from './LineFlowBoard';

type LineView = 'flow' | 'pipeline';

// ── 폴링 ────────────────────────────────────────────────────

interface Polled<T> {
  data: T | null;
  error: string | null;
  at: Date | null;
}

function usePoll<T>(load: () => Promise<T>, intervalMs: number): Polled<T> {
  const [state, setState] = useState<Polled<T>>({ data: null, error: null, at: null });

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const data = await load();
        if (!cancelled) setState({ data, error: null, at: new Date() });
      } catch (err) {
        // 마지막으로 받은 값은 남기고 실패만 표시한다 (화면이 비지 않게)
        if (!cancelled) setState((s) => ({ ...s, error: err instanceof Error ? err.message : String(err) }));
      }
    };
    run();
    const id = setInterval(run, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [load, intervalMs]);

  return state;
}

function FreshnessBadge({ at, error }: { at: Date | null; error: string | null }) {
  if (error) {
    return (
      <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200" title={error}>
        갱신 실패 · 아래는 마지막으로 받은 값
      </span>
    );
  }
  return <span className={HINT}>{at ? `${at.toLocaleTimeString('ko-KR')} 기준` : '불러오는 중…'}</span>;
}

// ── 상단 요약 ───────────────────────────────────────────────

function SummaryTiles({ nodes }: { nodes: NodeStatusRow[] }) {
  const stations = nodes.filter((n) => n.node_kind === 'STATION');
  const racks = nodes.filter((n) => n.node_kind === 'RACK');
  const tiles: [string, number, string][] = [
    ['공정 설비', stations.length, 'bg-gray-100 border-gray-400 text-gray-900'],
    ['가동 중', stations.filter((n) => n.status === 'RUN').length, 'bg-blue-50 border-blue-200 text-blue-600'],
    ['점유 설비', stations.filter((n) => n.occupancy > 0).length, 'bg-gray-50 border-gray-200 text-gray-900'],
    ['랙 대기', racks.reduce((a, n) => a + n.occupancy, 0), 'bg-amber-50 border-amber-200 text-amber-600'],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6">
      {tiles.map(([label, value, cls]) => (
        <div key={label} className={`rounded-lg border p-3 sm:p-4 ${cls}`}>
          <p className="text-xs sm:text-sm text-gray-500">{label}</p>
          <p className="text-2xl sm:text-3xl font-bold mt-1">{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── 반송 ────────────────────────────────────────────────────

const TRANSPORTER_TONE: Record<TransporterRow['status'], Tone> = {
  BUSY: 'run', IDLE: 'idle', ERROR: 'bad', OFFLINE: 'bad',
};
const TRANSPORTER_LABEL: Record<TransporterRow['status'], string> = {
  BUSY: '이송 중', IDLE: '대기', ERROR: '이상', OFFLINE: '정지',
};

function TransporterPanel({ transporters }: { transporters: TransporterRow[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
      {transporters.map((t) => {
        const manual = t.kind === 'OPERATOR';
        return (
          <div key={t.transporter_id} className={`${CARD} ${manual ? 'border-red-200' : ''}`}>
            <div className="px-4 py-3 flex items-center gap-2">
              <span className="font-semibold text-gray-900 text-sm">{t.label}</span>
              <Pill text={manual ? '수동 구간' : TRANSPORTER_LABEL[t.status]} tone={manual ? 'bad' : TRANSPORTER_TONE[t.status]} />
            </div>
            <div className={`px-4 pb-3 flex items-center justify-between ${HINT}`}>
              <span>큐 {t.queued}건{t.max_wait_s > 0 && ` · 최대 대기 ${formatElapsed(t.max_wait_s)}`}</span>
              <span className={MONO}>{t.auto_dispatch ? '자동 배정' : '수동 배정'}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── 플레이트 파이프라인 ─────────────────────────────────────

interface PipeColumn {
  label: string;
  step_order: number;
  node_ids: string[];
}

function buildPipeColumns(nodes: NodeStatusRow[]): PipeColumn[] {
  const cols: PipeColumn[] = [];
  nodes.filter((n) => n.node_kind === 'STATION').forEach((n) => {
    let c = cols.find((x) => x.label === n.group_label);
    if (!c) { c = { label: n.group_label, step_order: n.step_order, node_ids: [] }; cols.push(c); }
    c.node_ids.push(n.node_id);
    c.step_order = Math.min(c.step_order, n.step_order);
  });
  return cols.sort((a, b) => a.step_order - b.step_order);
}

function PipelineTable({ nodes, wip }: { nodes: NodeStatusRow[]; wip: WipRow[] }) {
  const cols = buildPipeColumns(nodes);
  /** 랙에 있는 재공은 "다음 공정 앞에서 대기" 로 놓는다. */
  const columnOf = (row: WipRow) => {
    const own = cols.findIndex((c) => c.node_ids.includes(row.node_id));
    if (own >= 0) return own;
    const next = cols.findIndex((c) => c.step_order > row.step_order);
    return next >= 0 ? next : cols.length - 1;
  };

  return (
    <div className={CARD}>
      <div className="px-4 py-3 border-b bg-gray-50 flex items-center gap-2">
        <span className="font-semibold text-gray-900 text-sm">플레이트 파이프라인</span>
        <span className={HINT}>행 = 재공 {wip.length}건 · 열 = 공정</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500">
            <tr>
              <th className="px-3 py-2 text-left font-medium sticky left-0 bg-gray-50 w-44">재공</th>
              {cols.map((c, i) => (
                <th key={c.label} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                  {i + 1} · {c.label}
                  <span className="block font-normal text-[10px] text-gray-400">{c.node_ids.length}대</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {wip.map((r) => {
              const i = columnOf(r);
              return (
                <tr key={`${r.ref_kind}:${r.ref}`} className="hover:bg-gray-50">
                  <td className="px-3 py-2 sticky left-0 bg-white">
                    <p className={`${MONO} font-semibold text-gray-900`}>{r.display_id ?? r.ref}</p>
                    <p className={HINT}>
                      {r.part_qty}개{r.part_label ? ` · ${r.part_label}` : (r.ref_kind === 'GROUP' ? ' 부품' : '')}
                    </p>
                  </td>
                  {cols.map((c, ci) => {
                    if (ci < i) return <td key={c.label} className="px-3 py-2 bg-gray-50 text-gray-300 text-xs">✓</td>;
                    if (ci > i) return <td key={c.label} className="px-3 py-2 text-gray-300 text-xs">—</td>;
                    return (
                      <td key={c.label} className={`px-3 py-2 ${r.waiting ? 'bg-amber-50' : 'bg-blue-50'}`}>
                        <Pill
                          text={r.waiting ? '대기' : statusLabel(r.display_status)}
                          tone={r.waiting ? 'warn' : statusTone(r.display_status)}
                        />
                        <p className={`${HINT} mt-1 truncate`}>{r.node_label}</p>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── 페이지 ──────────────────────────────────────────────────

export function LineMonitorPage() {
  const [view, setView] = useState<LineView>('flow');

  const loadNodes = useCallback(() => getNodes(), []);
  const loadTransporters = useCallback(() => getTransporters(), []);
  const loadWip = useCallback(() => getWip(), []);

  // 명세 §6 — 흐름 5초 · 파이프라인 15초
  const nodes = usePoll(loadNodes, view === 'flow' ? 5000 : 15000);
  const transporters = usePoll(loadTransporters, 5000);
  const wip = usePoll(loadWip, 15000);

  const error = nodes.error ?? transporters.error ?? wip.error;
  const nodeRows = nodes.data?.nodes ?? [];

  return (
    // 본문 폭은 기존 탭과 같은 컨테이너를 쓴다 (Dashboard.tsx 와 같은 규약)
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className={`${CARD} mb-6`}>
        <div className="px-4 flex items-center justify-between gap-4">
          <div className="flex space-x-6">
            <SubTab active={view === 'flow'} onClick={() => setView('flow')}>설비 · 반송</SubTab>
            <SubTab active={view === 'pipeline'} onClick={() => setView('pipeline')}>플레이트 파이프라인</SubTab>
          </div>
          <FreshnessBadge at={nodes.at} error={error} />
        </div>
      </div>

      {nodes.at === null && !error ? (
        <div className="text-gray-400 text-sm py-12 text-center">불러오는 중…</div>
      ) : (
        <>
          <SummaryTiles nodes={nodeRows} />
          {view === 'flow' ? (
            <>
              <TransporterPanel transporters={transporters.data?.transporters ?? []} />
              <LineFlowBoard nodes={nodeRows} transporters={transporters.data?.transporters ?? []} />
            </>
          ) : (
            <PipelineTable nodes={nodeRows} wip={wip.data?.wip ?? []} />
          )}
        </>
      )}
    </main>
  );
}
