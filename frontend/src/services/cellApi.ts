/**
 * 셀A 설비 상태 · 셀B 빈피킹 API — 10/16 통합 모니터링 패널
 *   GET /api/v1/vision/devices          설비 4대 현재 상태
 *   GET /api/v1/binpick/scenes/latest   최근 빈피킹 장면(없으면 null)
 *   GET /api/v1/binpick/scenes/{pk}     장면 상세(검출 목록)
 *   WS  /api/v1/vision/ws · /api/v1/binpick/ws  실시간
 *
 * 🚨 WebSocket 은 헤더를 못 실으므로 토큰을 `?token=` 으로 넘긴다(jwt_middleware._extract_websocket_token).
 *    안 넘기면 서버가 4401 로 닫고 화면은 영원히 "폴링" — 10/16 프린터 WS 가 실제로 그 상태였다.
 */

import { authFetch, getToken } from './auth';
import type { BinpickScene, VisionDevice, VisionDeviceListResponse } from '../types/cell';

const BASE = '/api/v1';

export async function getVisionDevices(): Promise<VisionDevice[]> {
  const res = await authFetch(`${BASE}/vision/devices`);
  if (!res.ok) throw new Error(`설비 상태 조회 실패 (${res.status})`);
  const body = (await res.json()) as VisionDeviceListResponse;
  return body.devices ?? [];
}

export async function getBinpickLatest(): Promise<BinpickScene | null> {
  const res = await authFetch(`${BASE}/binpick/scenes/latest`);
  if (!res.ok) throw new Error(`빈피킹 최근 장면 조회 실패 (${res.status})`);
  const body = (await res.json()) as BinpickScene | null;
  return body ?? null;   // 한 건도 없으면 서버가 null 을 준다(404 아님)
}

export async function getBinpickScene(scenePk: string): Promise<BinpickScene> {
  const res = await authFetch(`${BASE}/binpick/scenes/${encodeURIComponent(scenePk)}`);
  if (!res.ok) throw new Error(`빈피킹 장면 상세 조회 실패 (${res.status})`);
  return (await res.json()) as BinpickScene;
}

/** 같은 호스트의 WebSocket 주소 + 토큰. 토큰이 없으면(인증 OFF 로컬) 그대로. */
export function wsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const token = getToken();
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${protocol}//${window.location.host}${path}${q}`;
}
