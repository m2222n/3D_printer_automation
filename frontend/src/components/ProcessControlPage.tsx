/**
 * 공정 제어 탭 — 서브 메뉴(R4) + 설비 선택 + 화면(ui_kind 별)
 * 와이어프레임 = `docs/plan/20260916_fe_merged.html` 의 `wf-panel-control`.
 *
 * 🚨 서브 탭을 하드코딩하지 않는다 — `v_control_menu`(R4)가 유일한 출처다.
 *    설비를 늘리면 탭이 자동으로 늘고 이 파일은 안 바뀐다.
 */

import { useCallback, useEffect, useState } from 'react';
import { getControlMenu, getNodes, getTransporters } from '../services/lineApi';
import type { ControlMenuRow, NodeStatusRow, TransporterRow } from '../types/line';
import { getUsername } from '../services/auth';
import { CARD, SubTab } from './lineUi';
import { MonitorScreen } from './MonitorScreen';
import { BatchSplitScreen } from './BatchSplitScreen';
import { PartJudgeScreen } from './PartJudgeScreen';
import { RobotManualScreen } from './RobotManualScreen';

export function ProcessControlPage() {
  const [menu, setMenu] = useState<ControlMenuRow[]>([]);
  const [transporters, setTransporters] = useState<TransporterRow[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [active, setActive] = useState<string | null>(null);
  const [node, setNode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 🚨 반송은 STATION 이 아니라 v_control_menu(R4)에 안 들어온다 — R2 로 탭을 하나 붙인다
  const TRANSPORT_TAB = '로봇암 수동제어';
  const fullMenu: ControlMenuRow[] = transporters.length
    ? [...menu, { menu_label: TRANSPORT_TAB, ui_kind: 'TRANSPORT' as ControlMenuRow['ui_kind'],
                  step_order: 999, node_count: transporters.length,
                  node_ids: transporters.map((t) => t.transporter_id) }]
    : menu;
  const entry = fullMenu.find((r) => r.menu_label === active) ?? fullMenu[0] ?? null;
  const actor = getUsername() ?? 'unknown';

  // 서브 탭은 진입 시 1회 (토폴로지는 topo_sync 때만 바뀐다)
  useEffect(() => {
    getControlMenu()
      .then((r) => setMenu(r.menu))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getNodes()
      .then(({ nodes }: { nodes: NodeStatusRow[] }) =>
        setLabels(Object.fromEntries(nodes.map((n) => [n.node_id, n.label]))))
      .catch(() => { /* 라벨은 없어도 node_id 로 보여준다 */ });
    getTransporters().then((r) => setTransporters(r.transporters)).catch(() => { /* 반송 탭만 안 뜬다 */ });
  }, []);

  useEffect(() => {
    if (entry && (!node || !entry.node_ids.includes(node))) setNode(entry.node_ids[0]);
  }, [entry, node]);

  const onError = useCallback((m: string | null) => setError(m), []);

  if (menu.length === 0) {
    return error
      ? <div className="text-red-600 text-sm py-12 text-center">제어 메뉴를 불러오지 못했습니다 — {error}</div>
      : <div className="text-gray-400 text-sm py-12 text-center">불러오는 중…</div>;
  }
  if (!entry || !node) return <div className="text-gray-400 text-sm py-12 text-center">제어할 설비가 없습니다.</div>;

  const ids = entry.node_ids;
  const nameOf = (id: string) =>
    labels[id] ?? transporters.find((t) => t.transporter_id === id)?.label ?? id;

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* 서브 메뉴 + 설비 선택 */}
      <div className={`${CARD} mb-4`}>
        <div className="px-4 flex space-x-6 overflow-x-auto">
          {fullMenu.map((r) => (
            <SubTab
              key={r.menu_label}
              active={r.menu_label === entry.menu_label}
              onClick={() => { setActive(r.menu_label); setNode(null); setError(null); }}
            >
              {r.menu_label}
              <span className="ml-1.5 text-xs text-gray-400">{r.node_count}</span>
            </SubTab>
          ))}
        </div>
        <div className="px-4 py-2.5 border-t bg-gray-50 flex items-center gap-2 flex-wrap rounded-b-xl">
          <span className="text-sm text-gray-500">{entry.menu_label}</span>
          {entry.ui_kind === 'MONITOR' ? (
            <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
              설비 {ids.length}대 · 한 화면
            </span>
          ) : ids.length > 1 ? (
            ids.map((id) => (
              <button
                key={id}
                onClick={() => setNode(id)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                  id === node ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {nameOf(id)}
              </button>
            ))
          ) : (
            <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">{nameOf(ids[0])}</span>
          )}
          {error && <span className="ml-auto text-xs text-red-600">{error}</span>}
        </div>
      </div>

      {/* ui_kind 로 화면을 고른다 — 공정 이름으로 분기하지 않는다 */}
      {entry.ui_kind === 'MONITOR' ? (
        <MonitorScreen key={ids.join(',')} nodeIds={ids} actor={actor} onError={onError} />
      ) : entry.ui_kind === 'BATCH_SPLIT' ? (
        <BatchSplitScreen key={node} nodeId={node} actor={actor} />
      ) : entry.ui_kind === 'PART_JUDGE' ? (
        <PartJudgeScreen key={node} nodeId={node} actor={actor} />
      ) : entry.ui_kind === 'TRANSPORT' ? (
        <RobotManualScreen transporters={transporters} actor={actor} labels={labels}
          selected={node} onSelect={setNode} />
      ) : (
        <div className={`${CARD} py-10 text-center text-gray-400 text-sm`}>
          이 화면({entry.ui_kind})은 아직 없습니다.
        </div>
      )}
    </main>
  );
}
