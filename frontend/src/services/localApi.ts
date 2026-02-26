/**
 * Local API 서비스
 * Phase 2: 프리셋 관리, 파일 업로드, 프린트 작업
 */

import type {
  Preset,
  PresetCreate,
  PresetUpdate,
  PresetListResponse,
  UploadedFile,
  FileListResponse,
  PrintJob,
  PrintJobCreate,
  DiscoveredPrinter,
  LocalApiHealth,
  SceneEstimate,
  ScenePrepareRequest,
  DuplicateResult,
} from '../types/local';

const LOCAL_API_BASE = '/api/v1/local';

// API 에러 생성
function createApiError(status: number, message: string): Error {
  const error = new Error(message);
  error.name = 'ApiError';
  (error as Error & { status: number }).status = status;
  return error;
}

// 공통 fetch 함수
async function fetchLocalApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${LOCAL_API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw createApiError(response.status, `Local API Error: ${errorText || response.statusText}`);
  }

  return response.json();
}

// ===========================================
// 헬스체크
// ===========================================

export async function getLocalApiHealth(): Promise<LocalApiHealth> {
  return fetchLocalApi<LocalApiHealth>('/health');
}

// ===========================================
// 프린터 검색
// ===========================================

export async function discoverPrinters(timeout: number = 10): Promise<DiscoveredPrinter[]> {
  return fetchLocalApi<DiscoveredPrinter[]>(`/printers/discover?timeout=${timeout}`, {
    method: 'POST',
  });
}

// ===========================================
// 프리셋 CRUD
// ===========================================

export async function getPresets(
  skip: number = 0,
  limit: number = 50,
  partType?: string
): Promise<PresetListResponse> {
  let url = `/presets?skip=${skip}&limit=${limit}`;
  if (partType) {
    url += `&part_type=${encodeURIComponent(partType)}`;
  }
  return fetchLocalApi<PresetListResponse>(url);
}

export async function getPreset(presetId: string): Promise<Preset> {
  return fetchLocalApi<Preset>(`/presets/${presetId}`);
}

export async function createPreset(data: PresetCreate): Promise<Preset> {
  return fetchLocalApi<Preset>('/presets', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updatePreset(presetId: string, data: PresetUpdate): Promise<Preset> {
  return fetchLocalApi<Preset>(`/presets/${presetId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deletePreset(presetId: string): Promise<void> {
  await fetchLocalApi<{ message: string }>(`/presets/${presetId}`, {
    method: 'DELETE',
  });
}

// ===========================================
// 파일 업로드
// ===========================================

export async function uploadFile(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${LOCAL_API_BASE}/upload`, {
    method: 'POST',
    body: formData,
    // Content-Type은 자동 설정됨 (multipart/form-data)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw createApiError(response.status, `Upload Error: ${errorText || response.statusText}`);
  }

  return response.json();
}

export async function getFiles(): Promise<FileListResponse> {
  return fetchLocalApi<FileListResponse>('/files');
}

export async function deleteFile(filename: string): Promise<void> {
  await fetchLocalApi<{ message: string }>(`/files/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
}

// ===========================================
// 프린트 작업
// ===========================================

export async function startPrintJob(data: PrintJobCreate): Promise<PrintJob> {
  return fetchLocalApi<PrintJob>('/print', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getPrintJob(jobId: string): Promise<PrintJob> {
  return fetchLocalApi<PrintJob>(`/print/${jobId}`);
}

export async function getPrintJobs(skip: number = 0, limit: number = 20): Promise<PrintJob[]> {
  return fetchLocalApi<PrintJob[]>(`/print?skip=${skip}&limit=${limit}`);
}

export async function printWithPreset(
  presetId: string,
  printerSerial: string
): Promise<PrintJob> {
  return fetchLocalApi<PrintJob>(`/presets/${presetId}/print?printer_serial=${printerSerial}`, {
    method: 'POST',
  });
}

// ===========================================
// 슬라이스 준비 + 예측
// ===========================================

export async function prepareScene(data: ScenePrepareRequest): Promise<SceneEstimate> {
  return fetchLocalApi<SceneEstimate>('/scene/prepare', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function printPreparedScene(
  sceneId: string,
  printerSerial: string,
  jobName?: string
): Promise<{ success: boolean; message: string }> {
  let url = `/scene/${sceneId}/print?printer_serial=${printerSerial}`;
  if (jobName) {
    url += `&job_name=${encodeURIComponent(jobName)}`;
  }
  return fetchLocalApi<{ success: boolean; message: string }>(url, {
    method: 'POST',
  });
}

export async function deleteScene(sceneId: string): Promise<void> {
  await fetchLocalApi<{ success: boolean }>(`/scene/${sceneId}`, {
    method: 'DELETE',
  });
}

// ===========================================
// Scene 유효성 검사 / 모델 복제 / 재료 목록
// ===========================================

export async function validateScene(sceneId: string): Promise<Record<string, unknown>> {
  return fetchLocalApi<Record<string, unknown>>(`/scene/${sceneId}/validate`);
}

export async function getSceneModels(sceneId: string): Promise<{ models: Array<{ id: string; name?: string }> }> {
  return fetchLocalApi<{ models: Array<{ id: string; name?: string }> }>(`/scene/${sceneId}/models`);
}

export async function duplicateModel(
  sceneId: string,
  modelId: string,
  count: number
): Promise<DuplicateResult> {
  return fetchLocalApi<DuplicateResult>(`/scene/${sceneId}/models/${modelId}/duplicate`, {
    method: 'POST',
    body: JSON.stringify({ count }),
  });
}

export async function listMaterials(): Promise<{ materials: Array<{ code?: string; name?: string; [key: string]: unknown }> }> {
  return fetchLocalApi<{ materials: Array<{ code?: string; name?: string; [key: string]: unknown }> }>('/materials');
}

// ===========================================
// 스크린샷 / 정밀 시간 예측 / 간섭 검사
// ===========================================

export interface PrecisePrintTime {
  total_print_time_s: number;
  total_print_time_min: number;
  preprint_time_s: number;
  printing_time_s: number;
}

export interface InterferencesResult {
  interferences: string[][];
  count: number;
  has_interferences: boolean;
}

export async function estimatePrintTime(sceneId: string): Promise<PrecisePrintTime> {
  return fetchLocalApi<PrecisePrintTime>(`/scene/${sceneId}/estimate-time`, {
    method: 'POST',
  });
}

export async function getInterferences(
  sceneId: string,
  collisionOffsetMm?: number
): Promise<InterferencesResult> {
  let url = `/scene/${sceneId}/interferences`;
  if (collisionOffsetMm !== undefined) {
    url += `?collision_offset_mm=${collisionOffsetMm}`;
  }
  return fetchLocalApi<InterferencesResult>(url, {
    method: 'POST',
  });
}

export async function saveScreenshot(
  sceneId: string,
  viewType: string = 'ZOOM_ON_MODELS',
  imageSizePx: number = 820
): Promise<{ success: boolean; screenshot_url: string }> {
  return fetchLocalApi<{ success: boolean; screenshot_url: string }>(
    `/scene/${sceneId}/screenshot?view_type=${viewType}&image_size_px=${imageSizePx}`,
    { method: 'POST' }
  );
}

// ===========================================
// 메모 (Notes) API
// ===========================================

export interface PrintNoteItem {
  id: string;
  print_guid?: string;
  content: string;
  created_at: string | null;
  updated_at: string | null;
}

export async function getNotes(printGuid: string): Promise<PrintNoteItem[]> {
  return fetchLocalApi<PrintNoteItem[]>(`/notes/${printGuid}`);
}

export async function getNotesBulk(guids: string[]): Promise<Record<string, PrintNoteItem[]>> {
  if (guids.length === 0) return {};
  return fetchLocalApi<Record<string, PrintNoteItem[]>>(`/notes?guids=${guids.join(',')}`);
}

export async function createNote(printGuid: string, content: string): Promise<PrintNoteItem> {
  return fetchLocalApi<PrintNoteItem>(`/notes/${printGuid}`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  });
}

export async function updateNote(noteId: string, content: string): Promise<PrintNoteItem> {
  return fetchLocalApi<PrintNoteItem>(`/notes/${noteId}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export async function deleteNote(noteId: string): Promise<void> {
  await fetchLocalApi<{ detail: string }>(`/notes/${noteId}`, {
    method: 'DELETE',
  });
}

// ===========================================
// 알림 (Notifications) API
// ===========================================

export interface NotificationEventItem {
  id: string;
  event_type: string;
  printer_serial: string;
  printer_name: string | null;
  job_name: string | null;
  message: string | null;
  is_read: boolean;
  created_at: string | null;
}

export interface NotificationsResponse {
  events: NotificationEventItem[];
  unread_count: number;
}

export async function getNotifications(limit: number = 50, unreadOnly: boolean = false): Promise<NotificationsResponse> {
  return fetchLocalApi<NotificationsResponse>(`/notifications?limit=${limit}&unread_only=${unreadOnly}`);
}

export async function markNotificationsRead(ids?: string[]): Promise<{ unread_count: number }> {
  return fetchLocalApi<{ detail: string; unread_count: number }>('/notifications/mark-read', {
    method: 'POST',
    body: JSON.stringify(ids ? { ids } : {}),
  });
}
