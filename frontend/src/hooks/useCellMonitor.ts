/**
 * 셀A 설비 상태 + 셀B 빈피킹 실시간 훅 — 10/16 통합 모니터링 패널
 *
 * 구조 = 처음 REST 로 채우고 → WebSocket 두 채널로 갱신 → 채널이 끊기면 15초 폴링(프린터 훅과 같은 방식)
 * ⭐ 측정 페이지(/test/latency)와 **같은 메시지**를 받는다 — 둘을 나란히 두면 같은 순간에 바뀌어야 한다.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getBinpickLatest, getBinpickScene, getVisionDevices, wsUrl } from '../services/cellApi';
import type { BinpickScene, BinpickWsMessage, VisionDevice, VisionWsMessage } from '../types/cell';

const POLL_MS = 15000;
const RECONNECT_MS = 3000;
const RECONNECT_MAX = 10;

// ── 재접속하는 WebSocket 하나 ──────────────────────────────────
function useReconnectingSocket(path: string, onMessage: (msg: unknown) => void): boolean {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const aliveRef = useRef(true);
  const onMessageRef = useRef(onMessage);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const cleanup = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null; }
  }, []);

  const connect = useCallback(() => {
    cleanup();
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl(path));
    } catch (e) {
      console.error(`[WS ${path}] 생성 실패`, e);
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => { setConnected(true); attemptsRef.current = 0; };
    ws.onmessage = (ev) => {
      try { onMessageRef.current(JSON.parse(ev.data)); }
      catch (e) { console.error(`[WS ${path}] 파싱 실패`, e); }
    };
    ws.onerror = () => { /* onclose 가 뒤따른다 */ };
    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (!aliveRef.current) return;
      if (attemptsRef.current < RECONNECT_MAX) {
        attemptsRef.current += 1;
        timerRef.current = setTimeout(connect, RECONNECT_MS);
      }
      // 한도를 넘으면 폴링으로만 간다(15초) — 새로고침하면 다시 시도
    };
  }, [cleanup, path]);

  useEffect(() => {
    aliveRef.current = true;
    connect();
    return () => { aliveRef.current = false; cleanup(); };
  }, [connect, cleanup]);

  return connected;
}

// ── 훅 본체 ───────────────────────────────────────────────────
export interface UseCellMonitorReturn {
  devices: VisionDevice[];
  devicesError: string | null;
  visionConnected: boolean;
  scene: BinpickScene | null;
  sceneError: string | null;
  binpickConnected: boolean;
  reload: () => Promise<void>;
}

export function useCellMonitor(): UseCellMonitorReturn {
  const [devices, setDevices] = useState<VisionDevice[]>([]);
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [scene, setScene] = useState<BinpickScene | null>(null);
  const [sceneError, setSceneError] = useState<string | null>(null);

  const loadDevices = useCallback(async () => {
    try { setDevices(await getVisionDevices()); setDevicesError(null); }
    catch (e) { setDevicesError(e instanceof Error ? e.message : '설비 상태 로드 실패'); }
  }, []);

  const loadScene = useCallback(async () => {
    try { setScene(await getBinpickLatest()); setSceneError(null); }
    catch (e) { setSceneError(e instanceof Error ? e.message : '빈피킹 장면 로드 실패'); }
  }, []);

  const reload = useCallback(async () => { await Promise.all([loadDevices(), loadScene()]); }, [loadDevices, loadScene]);

  // 셀A — 상태 변경 메시지를 카드에 반영. 모르는 설비면 카드를 새로 만든다(목록보다 메시지가 먼저 올 수 있다).
  const onVision = useCallback((raw: unknown) => {
    const msg = raw as VisionWsMessage;
    if (!msg || typeof msg !== 'object' || !msg.data) return;
    const d = msg.data;
    if (msg.type === 'vision_status_change' && d.status) {
      const ts = d.timestamp ?? new Date().toISOString();
      setDevices((prev) => {
        const i = prev.findIndex((x) =>
          (d.device_type != null && d.device_id != null && x.type === d.device_type && x.id === d.device_id)
          || x.camera_id === d.camera_id);
        const patch = {
          status: d.status as string,
          is_online: d.status !== 'offline',
          last_status_change: ts,
          elapsed_since_change_s: 0,
        };
        if (i >= 0) {
          const next = prev.slice();
          next[i] = { ...prev[i], ...patch };
          return next;
        }
        return [...prev, {
          type: d.device_type ?? 'unknown',
          id: d.device_id ?? 0,
          name: `${d.device_type ?? '설비'} ${d.device_id ?? ''}`.trim(),
          camera_id: d.camera_id,
          ...patch,
        }];
      });
    } else if (msg.type === 'vision_camera_online') {
      setDevices((prev) => prev.map((x) => (x.camera_id === d.camera_id ? { ...x, is_online: true } : x)));
    }
  }, []);

  // 셀B — 실시간 메시지엔 검출 목록이 없으므로 상세를 한 번 더 불러온다.
  //       상세 조회가 실패해도 요약(개수·판정)은 바로 보여 준다 — 숫자보다 판정이 먼저 보여야 한다.
  const onBinpick = useCallback((raw: unknown) => {
    const msg = raw as BinpickWsMessage;
    if (!msg || typeof msg !== 'object' || msg.type !== 'binpick_scene' || !msg.scene_pk) return;
    setScene((prev) => ({
      scene_pk: msg.scene_pk,
      scene_id: msg.scene_id,
      schema_version: prev?.schema_version ?? '',
      module: prev?.module ?? 'bin_picking',
      n_detections: msg.n_detections,
      n_unique_labels: 0,
      recognition_track: null,
      latency_ms: msg.latency_ms,
      scene_gate: { verdict: msg.gate_verdict, trusted: null, valid_ratio_pct: null, note: null, n_dropped_by_size_gate: 0 },
      reported_at: null,
      received_at: msg.received_at,
      detections: [],
    }));
    getBinpickScene(msg.scene_pk)
      .then((full) => { setScene(full); setSceneError(null); })
      .catch((e) => setSceneError(e instanceof Error ? e.message : '장면 상세 로드 실패'));
  }, []);

  const visionConnected = useReconnectingSocket('/api/v1/vision/ws', onVision);
  const binpickConnected = useReconnectingSocket('/api/v1/binpick/ws', onBinpick);

  useEffect(() => { reload(); }, [reload]);

  // 채널이 끊긴 쪽만 15초 폴링
  useEffect(() => {
    if (visionConnected) return;
    const t = setInterval(loadDevices, POLL_MS);
    return () => clearInterval(t);
  }, [visionConnected, loadDevices]);
  useEffect(() => {
    if (binpickConnected) return;
    const t = setInterval(loadScene, POLL_MS);
    return () => clearInterval(t);
  }, [binpickConnected, loadScene]);

  return { devices, devicesError, visionConnected, scene, sceneError, binpickConnected, reload };
}
