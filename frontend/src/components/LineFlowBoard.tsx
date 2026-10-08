/**
 * 공정 흐름 — 윗단 = 랙(버퍼) · 아랫단 = 설비 · 사이 = 반송.
 * 와이어프레임(`docs/plan/fe_merge/line_view.js` flow())의 지그재그 배치를 그대로 옮겼다.
 *
 * 열 = 공정 하나. 설비는 group_label 로 묶어 한 장(프린터 4대 = 카드 1장 + 베이 4개).
 * 열 너비가 고정(px)이라 화살표 좌표를 그대로 계산할 수 있다.
 */

import type { NodeStatusRow, TransporterRow } from '../types/line';
import { formatElapsed, statusLabel } from '../types/line';
import { CARD, DOT, HINT, MONO, statusTone } from './lineUi';

// 카드 너비보다 열 간격(피치)을 좁게 둔다 — 윗단·아랫단이 가로로 겹쳐 지그재그가 촘촘해진다
const CARD_W = 216;
const PITCH = 150;
const BAND = 72;

interface Column {
  key: string;
  kind: NodeStatusRow['node_kind'];
  label: string;
  nodes: NodeStatusRow[];
}

/** 랙은 한 노드가 한 열, 설비는 group_label 로 묶는다. */
function buildColumns(nodes: NodeStatusRow[]): Column[] {
  const cols: Column[] = [];
  nodes.forEach((n) => {
    const key = n.node_kind === 'RACK' ? n.node_id : n.group_label;
    let c = cols.find((x) => x.key === key);
    if (!c) {
      c = { key, kind: n.node_kind, label: n.node_kind === 'RACK' ? n.label : key, nodes: [] };
      cols.push(c);
    }
    c.nodes.push(n);
  });
  return cols;
}

function RackCard({ n }: { n: NodeStatusRow }) {
  const slots = n.slots ?? [];
  const nextOut = slots.map((s) => s.contents[0]).find(Boolean);
  return (
    <div className={`${CARD} border-dashed bg-gray-50`}>
      <div className="px-3 py-2 border-b bg-white/60 flex items-center gap-2">
        <span className="font-semibold text-gray-900 text-xs truncate">{n.label}</span>
        <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 ml-auto flex-shrink-0">
          {n.occupancy}/{n.capacity}
        </span>
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {slots.map((s) => (
          <div key={s.slot_no}>
            <p className={HINT}>칸 {s.slot_no} · {s.used}/{s.capacity}</p>
            <div className="grid grid-cols-4 gap-1 mt-1">
              {Array.from({ length: s.capacity }, (_, i) => (
                <span
                  key={i}
                  className={`h-5 rounded border text-[9px] leading-[18px] text-center ${MONO} ${
                    i < s.used
                      ? 'bg-blue-50 border-blue-200 text-blue-700'
                      : 'bg-white border-gray-200 text-gray-300'
                  }`}
                >
                  {i < s.used ? (s.contents[i] ?? '').split(' ')[0].slice(-4) : i + 1}
                </span>
              ))}
            </div>
          </div>
        ))}
        <div className={`pt-1.5 border-t border-dashed ${HINT} space-y-0.5`}>
          {nextOut ? (
            <p className="truncate">
              다음 반출 <b className={`${MONO} text-gray-700`}>{nextOut.split(' ')[0]}</b>
            </p>
          ) : (
            <p>반출 대기 없음</p>
          )}
          {n.part_qty > 0 && <p>부품 {n.part_qty}개</p>}
        </div>
      </div>
    </div>
  );
}

function StationCard({ col }: { col: Column }) {
  const runN = col.nodes.filter((n) => n.status === 'RUN').length;
  const freeN = col.nodes.filter((n) => n.occupancy === 0).length;

  return (
    <div className={CARD}>
      <div className="px-3 py-2 border-b bg-gray-50 flex items-center gap-2">
        <span className="font-semibold text-gray-900 text-xs truncate">{col.label}</span>
        <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 ml-auto flex-shrink-0">
          설비 {col.nodes.length}
        </span>
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {col.nodes.map((n) => {
          const filled = n.occupancy > 0;
          const bad = n.status === 'HOLD' || n.status === 'ERROR';
          // 설비가 여럿일 때만 식별 태그를 앞에 붙인다 (1대뿐이면 열 제목과 같은 말이 두 번 나온다)
          // 라벨이 "N호기"로 끝나면 번호만, 프린터처럼 실제 이름(ShrewdStork 등)이면 이름 그대로
          const short = col.nodes.length > 1 ? n.label.replace(/^.*?(\d+호기|\d+)$/, '$1') : '';
          return (
            <div
              key={n.node_id}
              className={`rounded-lg border px-2 py-1.5 ${
                !filled ? 'border-dashed border-gray-200 bg-white'
                  : bad ? 'border-red-200 bg-red-50'
                  : n.status === 'RUN' ? 'border-blue-200 bg-blue-50'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-center gap-1.5">
                {short && <span className={`${MONO} font-semibold text-gray-600 flex-shrink-0`}>{short}</span>}
                <span className={`${MONO} text-gray-900 truncate flex-1`}>{n.display_id ?? '비어 있음'}</span>
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${DOT[statusTone(n.status)]}`} />
              </div>
              {filled && n.progress_pct != null ? (
                <>
                  <div className="h-1 bg-gray-200 rounded-full overflow-hidden mt-1">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: `${n.progress_pct}%` }} />
                  </div>
                  <p className={`${HINT} mt-0.5`}>{statusLabel(n.status)} · {formatElapsed(n.elapsed_s)}</p>
                </>
              ) : (
                <p className={`${HINT} mt-0.5`}>{filled ? statusLabel(n.status) : '투입 가능'}</p>
              )}
            </div>
          );
        })}
        <p className={`${HINT} pt-1.5 border-t border-dashed`}>가동 {runN} · 비어 있음 {freeN}</p>
      </div>
    </div>
  );
}

/** 두 열 사이 — 꺾인 화살표. 도착 카드가 윗단이면 위로, 아랫단이면 아래로. */
function Connector({ from, to, pitch, owner, manual }: {
  from: Column;
  to: Column;
  pitch: number;
  owner: string;
  manual: boolean;
}) {
  /**
   * 🚨 앞 열이 랙인지 설비인지에 따라 세는 것이 다르다.
   *    랙  = 지금 쌓여 있는 건수  → 이 구간이 밀린 양
   *    설비 = 완료돼 나갈 대수     → 가동 중인 개수를 "대기"라 부르면 오독한다
   */
  const fromRack = from.kind === 'RACK';
  const count = fromRack
    ? from.nodes.reduce((a, n) => a + n.occupancy, 0)
    : from.nodes.filter((n) => n.status === 'DONE' || n.status === 'SETTLING').length;
  const stroke = manual ? '#f87171' : '#9ca3af';   // red-400 / gray-400

  const W = pitch + CARD_W;
  const mid = BAND / 2;
  const top = 0;
  const bot = BAND;
  const y1 = to.kind === 'RACK' ? top : bot;
  const tip = (x: number, y: number) =>
    y === bot ? `${x},${bot} ${x - 5},${bot - 9} ${x + 5},${bot - 9}`
              : `${x},${top} ${x - 5},${top + 9} ${x + 5},${top + 9}`;

  let path: string;
  let head: string;
  if (from.kind === to.kind) {
    // 같은 단끼리(설비→설비) — 올라갔다 건너 다시 내려간다
    const x1 = CARD_W / 2;
    const x2 = pitch + CARD_W / 2;
    path = `M ${x1} ${y1} L ${x1} ${mid} L ${x2} ${mid} L ${x2} ${y1}`;
    head = tip(x2, y1);
  } else {
    // 윗단↔아랫단 — 두 블록이 붙어 있으므로 사이에 세로 화살표 하나
    const x = W / 2;
    path = `M ${x} ${y1 === bot ? top : bot} L ${x} ${y1}`;
    head = tip(x, y1);
  }

  return (
    <div className="relative" style={{ width: W, height: BAND, overflow: 'visible' }}>
      <svg width={W} height={BAND} className="absolute inset-0">
        <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeDasharray={manual ? '5 4' : undefined} />
        <polygon points={head} fill={stroke} />
      </svg>
      <span
        className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 px-2 py-1 rounded-full border text-[10px] font-medium whitespace-nowrap ${
          manual ? 'bg-red-50 border-red-200 text-red-700' : 'bg-white border-gray-200 text-gray-600'
        }`}
      >
        {manual && '✋ '}{owner}
        <span className="ml-1 text-gray-400">{fromRack ? '대기' : '완료'} {count}</span>
      </span>
    </div>
  );
}

export function LineFlowBoard({ nodes, transporters }: {
  nodes: NodeStatusRow[];
  transporters: TransporterRow[];
}) {
  const cols = buildColumns(nodes);
  if (cols.length === 0) return null;

  const byId = new Map(transporters.map((t) => [t.transporter_id, t]));
  // 다음 열이 반대쪽 단이면 가로로 겹쳐도 되니 좁게(PITCH), 같은 단이면 카드가 부딪히므로 넓게
  const widths = cols.map((c, i) =>
    i === cols.length - 1 ? CARD_W : (cols[i + 1].kind === c.kind ? CARD_W + 8 : PITCH));

  return (
    <div className={`${CARD} p-4 mb-6`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="font-semibold text-gray-900 text-sm">공정 흐름</span>
        <span className={HINT}>윗단 = 랙(버퍼) · 아랫단 = 설비 · 사이 = 반송</span>
      </div>
      <div className="overflow-x-auto pb-2">
        <div
          className="grid"
          style={{
            gridTemplateColumns: widths.map((w) => `${w}px`).join(' '),
            gridTemplateRows: `auto ${BAND}px auto`,
          }}
        >
          {cols.map((c, i) => {
            const row = c.kind === 'RACK' ? 1 : 3;
            const next = cols[i + 1];
            const tid = next?.nodes[0]?.transporter_id ?? null;
            const t = tid ? byId.get(tid) : undefined;
            return [
              <div
                key={`${c.key}-card`}
                style={{ gridColumn: i + 1, gridRow: row, width: CARD_W }}
                className={row === 1 ? 'self-end' : 'self-start'}
              >
                {c.kind === 'RACK' ? <RackCard n={c.nodes[0]} /> : <StationCard col={c} />}
              </div>,
              next ? (
                <div
                  key={`${c.key}-link`}
                  style={{ gridColumn: `${i + 1} / span 2`, gridRow: 2 }}
                  className="flex items-center justify-center"
                >
                  <Connector
                    from={c}
                    to={next}
                    pitch={widths[i]}
                    // ponytail: 수동 자원이 하나라 '작업자' 로 뭉뚱그린다. 둘 이상이 되면 이름을 살린다
                    owner={t ? (t.kind === 'OPERATOR' ? '작업자' : t.label) : '반송'}
                    manual={t?.kind === 'OPERATOR'}
                  />
                </div>
              ) : null,
            ];
          })}
        </div>
      </div>
    </div>
  );
}
