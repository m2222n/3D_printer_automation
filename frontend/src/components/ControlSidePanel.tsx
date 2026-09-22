/**
 * 제어 화면 공통 껍데기 — 좌(작업 입력) · 중앙(화면) · 우(인터록 + 명령 로그).
 * 화면 종류가 달라도 자리는 같다. 작업자가 매번 눈을 다시 맞추지 않게.
 */

import { readCommandLog, readInterlocks, toggleInterlock } from '../services/lineApi';
import { HINT, MONO, Panel, Pill } from './lineUi';

export function ControlLayout({ left, main, side }: {
  left: React.ReactNode;
  main: React.ReactNode;
  side: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      <div className="lg:col-span-3 space-y-3">{left}</div>
      <div className="lg:col-span-6">{main}</div>
      <div className="lg:col-span-3 space-y-3">{side}</div>
    </div>
  );
}

/**
 * 🔴 인터록은 명세 §5 에서 "데이터원이 없다" 로 유보된 항목이다 — 지금 체크박스는 목업이다.
 * 🔴 명령 로그도 **읽는 엔드포인트가 없다**(command_log 를 조회하는 R 번호가 없다).
 */
export function ControlSidePanel({ nodeId, onToggle }: { nodeId: string; onToggle: () => void }) {
  const locks = readInterlocks(nodeId);
  const log = readCommandLog();
  const okCount = locks.filter((i) => i.ok).length;

  return (
    <>
      {locks.length > 0 && (
        <Panel title="인터록" right={<Pill text={`${okCount} / ${locks.length}`} tone={okCount === locks.length ? 'ok' : 'bad'} />}>
          {locks.map((i) => (
            <label
              key={i.key}
              className={`flex items-center gap-2 text-sm cursor-pointer ${i.ok ? 'text-gray-700' : 'text-red-600 font-medium'}`}
            >
              <input
                type="checkbox"
                checked={i.ok}
                onChange={(e) => { toggleInterlock(nodeId, i.key, e.target.checked); onToggle(); }}
                className="w-4 h-4 rounded border-gray-300 accent-blue-600"
              />
              {i.label}
            </label>
          ))}
          <p className={HINT}>미충족이면 판정이 잠깁니다.</p>
        </Panel>
      )}
      <Panel title="명령 로그" right={<span className={HINT}>최근 {log.length}건</span>}>
        <div className="divide-y divide-gray-50 -my-1">
          {log.map((e, i) => (
            <div key={`${e.ts}-${i}`} className="py-2 flex items-start gap-2 text-xs">
              <span className={`${MONO} text-gray-400`}>{e.ts}</span>
              <span className="flex-1 text-gray-700">{e.text}</span>
              <span className="text-gray-400">{e.actor}</span>
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

/** 인터록이 전부 충족인가 — 판정 잠금 판단에 쓴다. */
export function interlockOk(nodeId: string): boolean {
  return readInterlocks(nodeId).every((i) => i.ok);
}
