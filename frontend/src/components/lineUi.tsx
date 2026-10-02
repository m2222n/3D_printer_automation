/**
 * 라인 화면 공통 표시 조각.
 * 색·모서리는 기존 탭(Tailwind)과 같은 값을 쓴다 — 새 탭만 다르게 보이면 안 된다.
 */

import type { DisplayStatus } from '../types/line';

export type Tone = 'run' | 'ok' | 'warn' | 'bad' | 'idle';

export const CARD = 'bg-white rounded-xl border shadow-sm overflow-hidden';
export const HINT = 'text-xs text-gray-500';
export const MONO = 'font-mono text-xs';

const TONE_BG: Record<Tone, string> = {
  run: 'bg-blue-50 text-blue-700',
  ok: 'bg-green-50 text-green-700',
  warn: 'bg-amber-50 text-amber-700',
  bad: 'bg-red-50 text-red-700',
  idle: 'bg-gray-100 text-gray-600',
};

export const DOT: Record<Tone, string> = {
  run: 'bg-blue-500 animate-pulse',
  ok: 'bg-green-500',
  warn: 'bg-amber-500',
  bad: 'bg-red-500',
  idle: 'bg-gray-400',
};

export function Pill({ text, tone = 'idle' }: { text: string; tone?: Tone }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1.5 ${TONE_BG[tone]}`}>
      <span className={`w-2 h-2 rounded-full ${DOT[tone]}`} />
      {text}
    </span>
  );
}

/** 상태 → 색. 정지·이상만 빨강이다 (사람이 봐야 하는 것). */
export function statusTone(s: DisplayStatus): Tone {
  switch (s) {
    case 'RUN': return 'run';
    case 'SETTLING': return 'warn';
    case 'DONE': return 'ok';
    case 'HOLD':
    case 'ERROR': return 'bad';
    default: return 'idle';
  }
}

/** 서브 탭 버튼 — 기존 상단 탭과 같은 모양. */
export function SubTab({ active, onClick, children }: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`py-3 px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
        active
          ? 'border-blue-500 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
      }`}
    >
      {children}
    </button>
  );
}

// ── 제어 화면 공통 ──────────────────────────────────────────

export const BTN = 'px-3 py-2 rounded-lg text-sm font-medium border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors';
export const BTN_PRI = 'px-3 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors';
export const BTN_DANGER = 'px-3 py-2 rounded-lg text-sm font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors';
export const INPUT = 'w-full px-2 py-1.5 rounded-lg border border-gray-200 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400';
export const ROW = 'bg-white rounded-lg border p-3 transition-all hover:shadow-sm';
export const NUM = 'flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold';

/** 작업 순서 머리 — ① 투입 대기 큐 처럼. */
export function Step({ n, title, note }: { n: number; title: string; note?: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className={NUM}>{n}</span>
      <span className="font-semibold text-gray-900 text-sm">{title}</span>
      {note && <span className={`${HINT} ml-auto`}>{note}</span>}
    </div>
  );
}

export function Panel({ title, right, children }: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={CARD}>
      <div className="px-4 py-3 border-b bg-gray-50 flex items-center gap-2">
        <span className="font-semibold text-gray-900 text-sm">{title}</span>
        <span className="flex-1" />
        {right}
      </div>
      <div className="px-4 py-3 space-y-3">{children}</div>
    </div>
  );
}

/**
 * 확인 다이얼로그. 되돌릴 수 없는 조작은 반드시 여기를 거친다.
 * 기존 FE 알림 패널과 같은 rounded-xl / shadow-xl.
 */
export function ConfirmDialog({ open, title, confirmLabel, danger, onConfirm, onCancel, children }: {
  open: boolean;
  title: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-gray-900/40 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="bg-white rounded-xl shadow-xl border w-full max-w-md overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b">
          <h3 className="font-semibold text-gray-900 text-sm">{title}</h3>
        </div>
        <div className="px-4 py-4 text-sm text-gray-700">{children}</div>
        <div className="px-4 pb-4 flex gap-2">
          <button className={`${BTN} flex-1`} onClick={onCancel}>취소</button>
          <button className={`${danger ? BTN_DANGER : BTN_PRI} flex-1`} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
