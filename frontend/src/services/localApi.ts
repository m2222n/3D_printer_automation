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
