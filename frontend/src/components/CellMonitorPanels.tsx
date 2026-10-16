/**
 * 통합 모니터링 패널 2개 — 셀A 설비 상태(세척기·경화기) + 셀B 빈피킹 최근 결과 (10/16)
 * 데이터 = useCellMonitor (REST 초기 로드 + WebSocket 2채널 + 끊기면 15초 폴링)
 *
 * 왜 있나 = 운영 화면이 프린터만 보여 줬다. 시험기관이 "운영 화면엔 어디 뜨나요?" 를 물을 때 보여 줄 자리.
 * 🚨 빈피킹은 판정 없이 숫자만 보이면 잘못 찍힌 장면이 정상처럼 보인다 — 판정 배지를 숫자보다 앞에 둔다(8/7 설계원칙 3).
 */

import { useEffect, useState } from 'react';
import { useCellMonitor } from '../hooks/useCellMonitor';
import type { BinpickScene, VisionDevice } from '../types/cell';

// ── 표시 규칙 ─────────────────────────────────────────────────
const DEVICE_TYPE_LABEL: Record<string, string> = { wash: '세척기', cure: '경화기' };

function statusView(status: string): { label: string; cls: string; dot: string } {
  if (status.endsWith('_running')) return { label: '작동 중', cls: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500 animate-pulse' };
  if (status.endsWith('_complete')) return { label: '완료', cls: 'bg-green-100 text-green-700', dot: 'bg-green-500' };
  if (status.endsWith('_idle')) return { label: '대기', cls: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' };
  if (status === 'offline') return { label: '연결 끊김', cls: 'bg-red-50 text-red-600', dot: 'bg-red-400' };
  if (status === 'error') return { label: '오류', cls: 'bg-red-100 text-red-700', dot: 'bg-red-500' };
  return { label: status || '알 수 없음', cls: 'bg-gray-100 text-gray-500', dot: 'bg-gray-300' };
}

function verdictView(verdict: string): { label: string; cls: string; untrusted: boolean } {
  switch (verdict) {
    case 'in_distribution': return { label: '정상', cls: 'bg-green-100 text-green-700', untrusted: false };
    case 'borderline': return { label: '주의', cls: 'bg-yellow-100 text-yellow-700', untrusted: false };
    case 'out_of_distribution': return { label: '화면 이상 — 결과를 믿지 말 것', cls: 'bg-red-100 text-red-700', untrusted: true };
    case 'not_checked': return { label: '판정 없음', cls: 'bg-gray-100 text-gray-600', untrusted: true };
    default: return { label: verdict || '판정 없음', cls: 'bg-gray-100 text-gray-600', untrusted: true };
  }
}

function fmtElapsed(sec: number): string {
  if (sec < 60) return `${sec}초`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 ${sec % 60}초`;
  return `${Math.floor(sec / 3600)}시간 ${Math.floor((sec % 3600) / 60)}분`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString('ko-KR');
}

function deviceOrder(a: VisionDevice, b: VisionDevice): number {
  const rank = (t: string) => (t === 'wash' ? 0 : t === 'cure' ? 1 : 2);
  return rank(a.type) - rank(b.type) || a.id - b.id || a.name.localeCompare(b.name);
}

// 1초마다 다시 그려 "n초 전" 이 흐르게
function useNowTick(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

function LiveBadge({ connected }: { connected: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs ${
      connected ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-500' : 'bg-yellow-500 animate-pulse'}`}></span>
      {connected ? '실시간' : '폴링'}
    </span>
  );
}

// ── 패널 A: 셀A 설비 ─────────────────────────────────────────
function DeviceCard({ device, now }: { device: VisionDevice; now: number }) {
  const sv = statusView(device.status);
  const changed = device.last_status_change ? new Date(device.last_status_change).getTime() : NaN;
  const elapsed = Number.isNaN(changed) ? device.elapsed_since_change_s : Math.max(0, Math.floor((now - changed) / 1000));
  const typeLabel = DEVICE_TYPE_LABEL[device.type] ?? device.type;
  return (
    <div
      data-testid={`device-${device.type}-${device.id}`}
      data-status={device.status}
      className={`bg-white rounded-lg border p-4 ${device.is_online ? 'border-gray-200' : 'border-red-300'}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-xs text-gray-500">{typeLabel} {device.id}</div>
          <div className="font-medium text-gray-900">{device.name}</div>
        </div>
        <span className={`w-2.5 h-2.5 rounded-full ${sv.dot}`} title={device.status}></span>
      </div>
      <span className={`inline-block px-2.5 py-1 rounded-full text-sm font-medium ${sv.cls}`}>{sv.label}</span>
      <div className="mt-2 text-xs text-gray-500">
        {elapsed != null ? `${fmtElapsed(elapsed)} 전 변경` : '변경 기록 없음'}
        {!device.is_online && <span className="ml-2 text-red-500">카메라 오프라인</span>}
      </div>
    </div>
  );
}

// ── 패널 B: 셀B 빈피킹 ────────────────────────────────────────
function SceneView({ scene }: { scene: BinpickScene }) {
  const vv = verdictView(scene.scene_gate?.verdict ?? 'not_checked');
  const latencyS = scene.latency_ms != null ? (scene.latency_ms / 1000).toFixed(2) : null;
  return (
    <div data-testid="binpick-scene" data-scene-pk={scene.scene_pk} data-verdict={scene.scene_gate?.verdict}>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className={`inline-block px-2.5 py-1 rounded-full text-sm font-medium ${vv.cls}`}>{vv.label}</span>
        <span className="text-sm text-gray-700">
          찾은 부품 <b data-testid="binpick-count">{scene.n_detections}</b>개
        </span>
        {latencyS && <span className="text-sm text-gray-500">인식 {latencyS}초</span>}
        <span className="text-xs text-gray-400 ml-auto">수신 {fmtTime(scene.received_at)}</span>
      </div>
      {scene.scene_gate?.note && (
        <div className="text-xs text-gray-500 mb-2">{scene.scene_gate.note}</div>
      )}
      {scene.detections.length > 0 ? (
        <table className={`w-full text-sm ${vv.untrusted ? 'opacity-40' : ''}`}>
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b">
              <th className="py-1 pr-2">#</th>
              <th className="py-1 pr-2">부품</th>
              <th className="py-1 pr-2">신뢰도</th>
              <th className="py-1">벌림(mm)</th>
            </tr>
          </thead>
          <tbody>
            {scene.detections.map((d) => (
              <tr key={d.idx} className="border-b border-gray-100">
                <td className="py-1 pr-2 text-gray-400">{d.idx}</td>
                <td className="py-1 pr-2 font-mono text-gray-900">{d.label ?? '—'}</td>
                <td className="py-1 pr-2 text-gray-700">{d.confidence != null ? `${Math.round(d.confidence * 100)}%` : '—'}</td>
                <td className="py-1 text-gray-700">{d.gripper_width_mm != null ? d.gripper_width_mm.toFixed(1) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="text-sm text-gray-400">
          {scene.n_detections > 0 ? '부품 목록을 불러오는 중…' : '이 장면에서 찾은 부품이 없습니다.'}
        </div>
      )}
      {vv.untrusted && scene.detections.length > 0 && (
        <div className="mt-2 text-xs text-red-500">판정이 "{vv.label}" 인 장면입니다. 위 목록은 참고용입니다.</div>
      )}
    </div>
  );
}

// ── 패널 묶음 ─────────────────────────────────────────────────
export default function CellMonitorPanels() {
  const { devices, devicesError, visionConnected, scene, sceneError, binpickConnected } = useCellMonitor();
  const now = useNowTick();
  const sorted = devices.slice().sort(deviceOrder);

  return (
    <section data-testid="cell-monitor" className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* 패널 A */}
      <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900">셀A 설비 상태 <span className="text-sm text-gray-500 font-normal">세척기 · 경화기</span></h3>
          <LiveBadge connected={visionConnected} />
        </div>
        {devicesError && <div className="text-sm text-red-600 mb-2">{devicesError}</div>}
        {sorted.length > 0 ? (
          <div className="grid grid-cols-2 gap-3">
            {sorted.map((d) => <DeviceCard key={`${d.type}-${d.id}-${d.camera_id}`} device={d} now={now} />)}
          </div>
        ) : (
          <div className="text-sm text-gray-400 py-6 text-center">
            등록된 설비가 없습니다. 카메라가 처음 상태를 보고하면 여기에 나타납니다.
          </div>
        )}
      </div>

      {/* 패널 B */}
      <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900">셀B 빈피킹 <span className="text-sm text-gray-500 font-normal">최근 인식 결과</span></h3>
          <LiveBadge connected={binpickConnected} />
        </div>
        {sceneError && <div className="text-sm text-red-600 mb-2">{sceneError}</div>}
        {scene ? (
          <SceneView scene={scene} />
        ) : (
          <div className="text-sm text-gray-400 py-6 text-center">아직 인식 결과가 없습니다. 빈피킹이 한 번 돌면 여기에 나타납니다.</div>
        )}
      </div>
    </section>
  );
}
