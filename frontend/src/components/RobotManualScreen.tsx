/**
 * TRANSPORT — 로봇암 수동제어 (S8)
 *
 * 🔴 기존 「자동화 수동제어」와 무엇이 다른가
 *   기존  IP·포트를 타이핑하고 Modbus 주소·값을 직접 넣어 Write
 *         (AutomationManualPage.tsx:367 'Robot IP' · :404 'Address'/'Value')
 *   여기  **동작 명령만 고른다.** 어디에 무엇을 쓰는지는 서버(topology)가 안다.
 *
 * 🚨 반송 자원도 명령 목록도 화면이 지어내지 않는다 — R2 · R11 이 준다.
 */

import { useCallback, useEffect, useState } from 'react';
import { getRobotCommands, runRobotCommand } from '../services/lineApi';
import type { CommandSend, RobotCommandListResponse, RobotCommandRow, TransporterRow } from '../types/line';
import { ControlLayout } from './ControlSidePanel';
import { BTN_PRI, CARD, ConfirmDialog, HINT, MONO, ROW, Step } from './lineUi';

const KIND_LABEL: Record<CommandSend['kind'], string> = {
  DO: '디지털 출력', MODBUS: 'Modbus 레지스터', SOCKET: '펜던트 소켓',
};

/** 보낼 값을 사람이 읽는 한 줄로. 해석하지 않고 그대로 찍는다. */
function chunkOf(s: CommandSend): string {
  if (s.kind === 'DO') {
    const bits = s.bits ?? [];
    return bits.length > 1 ? `${s.ch} = ${bits.join('')}  (${s.pulse_s}s 펄스 → 전부 0)` : `${s.ch} = ${bits[0]}`;
  }
  if (s.kind === 'MODBUS') {
    return `reg ${s.reg} ← ${s.value}` + (s.then ? `,  reg ${s.then.reg} ← ${s.then.value}` : '');
  }
  return `TCP :${s.port}  "${s.msg}"`;
}

/** 그리퍼는 폭이 곧 힌트다. 실측 전에는 임의값이므로 그렇다고 적는다. */
function hintOf(c: RobotCommandRow): string {
  if (c.span_mm != null) return `약 ${c.span_mm}mm${c.verified ? '' : ' (임의값)'}`;
  return c.hint ?? '';
}

/**
 * 🚨 어느 자원을 보고 있는지는 **상위(노드 바)가 쥔다** — 화면 안에도 목록이 있어서
 *    둘이 따로 상태를 가지면 노드 바로 고른 것과 화면이 어긋난다.
 */
export function RobotManualScreen({ transporters, actor, labels, selected, onSelect }: {
  transporters: TransporterRow[];
  actor: string;
  labels: Record<string, string>;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [cat, setCat] = useState<RobotCommandListResponse | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [ask, setAsk] = useState(false);
  const [log, setLog] = useState<{ ts: string; text: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const arm = transporters.find((t) => t.transporter_id === selected) ?? transporters[0] ?? null;

  const load = useCallback(async () => {
    if (!arm) return;
    setCat(await getRobotCommands(arm.transporter_id));
  }, [arm]);

  useEffect(() => { load(); setPicked(null); setError(null); }, [load]);

  if (!arm) {
    return <div className="py-10 text-center text-gray-400 text-sm">토폴로지에 반송 자원이 없습니다.</div>;
  }

  const cmd = cat?.commands.find((c) => c.command_id === picked) ?? null;
  const manual = cat?.manual ?? arm.kind === 'OPERATOR';
  const nodeLabels = (cat?.node_ids ?? []).map((id) => labels[id] ?? id);

  const run = async () => {
    if (!cmd) return;
    const res = await runRobotCommand(arm.transporter_id, cmd.command_id, actor);
    const d = new Date();
    const ts = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    setLog((l) => [{ ts, text: `${arm.label} · ${cmd.label} → ${chunkOf(cmd.send)}` }, ...l].slice(0, 8));
    setError(res.ok ? null : res.message);
    setAsk(false);
  };

  // ── 좌 ──
  const left = (
    <>
      <div>
        <Step n={1} title="반송 자원" note={`${transporters.length}건`} />
        <div className="space-y-2">
          {transporters.map((t) => {
            const off = !t.auto_dispatch;
            return (
              <button
                key={t.transporter_id}
                onClick={() => { onSelect(t.transporter_id); setPicked(null); setError(null); }}
                className={`${ROW} w-full text-left ${
                  t.transporter_id === arm.transporter_id ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900 text-sm">{t.label}</span>
                  <span className={`px-2.5 py-1 rounded-full text-xs font-medium ml-auto ${
                    off ? 'bg-gray-100 text-gray-600' : 'bg-green-50 text-green-700'}`}>
                    {off ? '수동' : t.kind}
                  </span>
                </div>
                <p className={`${HINT} mt-1`}>큐 {t.queued}건</p>
              </button>
            );
          })}
        </div>
      </div>
      <div className="mt-4">
        <Step n={2} title="담당 구간" />
        <div className={`${CARD} px-3 py-2.5`}>
          <div className="flex flex-wrap gap-1">
            {nodeLabels.map((l) => (
              <span key={l} className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">{l}</span>
            ))}
          </div>
          <p className={`${HINT} mt-2`}>노드 현황(R1)을 담당 자원으로 묶은 결과입니다</p>
        </div>
        <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-700 mt-2">
          IP·포트를 여기서 입력하지 않습니다. 접속 대상은 설비 설정에 있고, 이 화면은 <b>무엇을 시킬지</b>만 고릅니다.
        </div>
      </div>
    </>
  );

  // ── 중앙 ──
  const groups: { name: string; items: RobotCommandRow[] }[] = [];
  (cat?.commands ?? []).forEach((c) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) { g = { name: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  });

  const main = (
    <>
      <Step n={3} title="동작 명령" note={`${cat?.commands.length ?? 0}개`} />
      {manual ? (
        <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-6 text-sm text-amber-800 text-center">
          <b>{arm.label} 은 사람이 옮깁니다.</b>
          <br />
          <span className="text-xs">보낼 명령이 없습니다. 반송 대기는 라인 모니터링에서 봅니다.</span>
        </div>
      ) : groups.length === 0 ? (
        <div className={`${CARD} px-4 py-6 text-center ${HINT}`}>이 자원에 등록된 명령이 없습니다.</div>
      ) : (
        <>
          {groups.map((g) => (
            <div key={g.name} className="mb-4">
              <p className={`${HINT} mb-2`}>{g.name}</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {g.items.map((c) => (
                  <button
                    key={c.command_id}
                    onClick={() => { setPicked(c.command_id); setError(null); }}
                    className={`bg-white rounded-lg border p-2.5 text-left transition-all hover:shadow-sm ${
                      c.command_id === picked ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'}`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-gray-900 text-sm truncate">{c.label}</span>
                      {!c.verified && (
                        <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 flex-shrink-0">미검증</span>
                      )}
                    </div>
                    <p className={`${HINT} mt-0.5`}>{hintOf(c)}</p>
                  </button>
                ))}
              </div>
            </div>
          ))}
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 space-y-1">
            <p><b>미검증</b> = 실물로 확인되지 않은 명령입니다. 눌러도 나가지 않고, 무엇을 보낼지만 보여줍니다.</p>
            <p><b>그리퍼</b>는 상태 하나에 신호 하나입니다 — 여는 동작을 지시하는 것이 아니라 <b>갈 상태</b>를 고릅니다.</p>
          </div>
        </>
      )}
    </>
  );

  // ── 우 ──
  const side = (
    <>
      <div>
        <Step n={4} title="보낼 것" />
        {!cmd ? (
          <div className={`${CARD} px-4 py-8 text-center ${HINT}`}>
            {manual ? '수동 반송이라 보낼 것이 없습니다.' : '명령을 고르면 무엇이 나가는지 여기 보입니다.'}
          </div>
        ) : (
          <div className={CARD}>
            <div className="px-4 py-3 border-b bg-gray-50 flex items-center gap-2">
              <span className="font-semibold text-gray-900 text-sm">{cmd.label}</span>
              <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 ml-auto">
                {KIND_LABEL[cmd.send.kind]}
              </span>
            </div>
            <div className="px-4 py-3 space-y-3">
              <div>
                <p className={`${HINT} mb-1`}>보낼 값</p>
                <div className={`rounded-lg bg-gray-900 text-gray-100 px-3 py-2 ${MONO} break-all`}>{chunkOf(cmd.send)}</div>
              </div>
              <div>
                <p className={`${HINT} mb-1`}>이 값의 출처</p>
                <p className="text-xs text-gray-700">{cmd.source}</p>
              </div>
              <div>
                <p className={`${HINT} mb-1`}>누르면 일어나는 일</p>
                <p className={`text-sm ${cmd.verified ? 'text-gray-900' : 'text-amber-700'}`}>{cmd.risk}</p>
              </div>
              <button className={`${BTN_PRI} w-full`} disabled={!cmd.verified} onClick={() => setAsk(true)}>
                {cmd.verified ? '실행' : '미검증 — 실행할 수 없음'}
              </button>
              {error && <p className="text-xs text-red-600">{error}</p>}
            </div>
          </div>
        )}
      </div>
      <div className="mt-3">
        <Step n={5} title="실행 로그" />
        <div className={`${CARD} px-4 py-2`}>
          {log.length === 0 ? (
            <p className={`${HINT} py-3`}>아직 없습니다.</p>
          ) : (
            <div className="divide-y divide-gray-50 -my-1">
              {log.map((e, i) => (
                <div key={i} className="py-2 flex items-start gap-2 text-xs">
                  <span className={`${MONO} text-gray-400`}>{e.ts}</span>
                  <span className="flex-1 text-gray-700">{e.text}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );

  return (
    <>
      <ControlLayout left={left} main={main} side={side} />
      <ConfirmDialog
        open={ask}
        title={`${cmd?.label ?? ''} — ${arm.label}`}
        confirmLabel="실행"
        danger
        onConfirm={run}
        onCancel={() => setAsk(false)}
      >
        <b>{cmd?.risk}</b>
        <div className="mt-2">
          <p className={`${HINT} mb-1`}>보낼 값</p>
          <div className={`rounded-lg bg-gray-900 text-gray-100 px-3 py-2 ${MONO} break-all`}>
            {cmd && chunkOf(cmd.send)}
          </div>
        </div>
        <p className={`${HINT} mt-2`}>설비가 실제로 움직입니다.</p>
      </ConfirmDialog>
    </>
  );
}
