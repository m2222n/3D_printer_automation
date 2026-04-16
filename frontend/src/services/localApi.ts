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
  partType?: string,
  printerSerial?: string
): Promise<PresetListResponse> {
  let url = `/presets?skip=${skip}&limit=${limit}`;
  if (partType) {
    url += `&part_type=${encodeURIComponent(partType)}`;
  }
  if (printerSerial) {
    url += `&printer_serial=${encodeURIComponent(printerSerial)}`;
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

// ===========================================
// Automation API
// ===========================================

export interface AutomationCommandCreate {
  file_path?: string;
  file_name?: string;
  preset_id?: string;
  washing_time: number;
  curing_time: number;
  target_printer?: number; // 260410 추가
}

export interface AutomationCommandItem {
  cmd_id: string;
  file_path: string;
  file_name: string;
  cmd_status: number;
  post_proc_stage: number;
  wash_minutes?: number;
  washing_time?: number;
  curing_time?: number;
  use_yn?: string;
  target_printer: number | null;
  allocated_data?: Record<string, unknown> | string | null;
  progress: number;
  message: string | null;
  claimed_by?: string | null;
  locked_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationState {
  running: boolean;
  paused: boolean;
}

export interface AutomationQueues {
  running?: boolean;
  paused?: boolean;
  runtime_ctx?: {
    active_job_count?: number;
    robot_ack_count?: number;
  };
  printer_queues?: Record<string, string[]>;
  printer_active_cmd?: Record<string, string | null>;
  printer_has_plate?: Record<string, boolean>;
  printer_use?: Record<string, string>;
  wash_waiting?: string[];
  wash_active_cmd?: Record<string, string | null>;
  cure_waiting?: string[];
  cure_active_cmd?: Record<string, string | null>;
  robot_active_cmd?: string | null;
  robot_queue?: Array<{
    cmd_id: string;
    task_type: string;
    from_unit: string;
    to_unit: string;
    requested_by: string;
    status: string;
  }>;
  active_jobs?: Record<string, {
    cmd_id?: string;
    file_path?: string;
    file_name?: string;
    cmd_status: number;
    post_proc_stage: number;
    washing_time?: number;
    curing_time?: number;
    target_printer?: number | null;
    allocated_data?: Record<string, unknown>;
    progress?: number;
    message?: string;
  }>;
}

export interface AutomationLogItem {
  id: number;
  log_type: number;
  source: string;
  cmd_id?: string | null;
  message: string;
  created_at: string;
}

export async function createAutomationCommand(body: AutomationCommandCreate): Promise<{ ok: boolean; cmd_id: string }> {
  return fetchLocalApi<{ ok: boolean; cmd_id: string }>('/automation/commands', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function getAutomationCommands(limit: number = 100): Promise<{ items: AutomationCommandItem[] }> {
  return fetchLocalApi<{ items: AutomationCommandItem[] }>(`/automation/commands?limit=${limit}`);
}

export async function updateAutomationCommandsUseYn(
  cmdIds: string[],
  useYn: 'Y' | 'N'
): Promise<{ ok: boolean; updated: number }> {
  return fetchLocalApi<{ ok: boolean; updated: number }>('/automation/commands/use', {
    method: 'POST',
    body: JSON.stringify({ cmd_ids: cmdIds, use_yn: useYn }),
  });
}

export async function getAutomationState(): Promise<AutomationState> {
  return fetchLocalApi<AutomationState>('/automation/state');
}

export async function controlAutomation(action: 'start' | 'stop' | 'pause' | 'resume'): Promise<{ ok: boolean; state: AutomationState }> {
  return fetchLocalApi<{ ok: boolean; state: AutomationState }>(`/automation/control/${action}`, {
    method: 'POST',
  });
}

export async function getAutomationQueues(): Promise<{ items: AutomationQueues }> {
  return fetchLocalApi<{ items: AutomationQueues }>('/automation/queues');
}

export async function getAutomationLogs(limit: number = 200): Promise<{ items: AutomationLogItem[] }> {
  return fetchLocalApi<{ items: AutomationLogItem[] }>(`/automation/logs?limit=${limit}`);
}

export async function manualRobotSend(payload: string): Promise<{ ok: boolean; sent: string; response?: string }> {
  return fetchLocalApi<{ ok: boolean; sent: string; response?: string }>('/automation/manual/robot-send', {
    method: 'POST',
    body: JSON.stringify({ payload }),
  });
}

export async function manualVisionSend(payload: string): Promise<{ ok: boolean; sent: string; response?: string }> {
  return fetchLocalApi<{ ok: boolean; sent: string; response?: string }>('/automation/manual/vision-send', {
    method: 'POST',
    body: JSON.stringify({ payload }),
  });
}

export interface ManualCommStatus {
  ok: boolean;
  connected: boolean;
  host: string;
  port: number;
  error?: string;
  timestamp?: string;
}

export interface ManualCommConfig {
  ok: boolean;
  robot_host: string;
  robot_port: number;
  vision_host: string;
  vision_port: number;
  updated_at?: string;
}

export interface ModbusRegisterItem {
  address: number;
  value: number;
}

export interface ModbusRegistersResponse {
  ok: boolean;
  host: string;
  port: number;
  start_addr: number;
  end_addr: number;
  count: number;
  items: ModbusRegisterItem[];
  timestamp?: string;
}

export interface ModbusWriteResponse {
  ok: boolean;
  host: string;
  port: number;
  address: number;
  value: number;
  read_back?: number | null;
  timestamp?: string;
}

export async function getManualRobotStatus(): Promise<ManualCommStatus> {
  return fetchLocalApi<ManualCommStatus>('/automation/manual/robot-status');
}

export async function getManualVisionStatus(): Promise<ManualCommStatus> {
  return fetchLocalApi<ManualCommStatus>('/automation/manual/vision-status');
}

export async function getManualCommConfig(): Promise<ManualCommConfig> {
  return fetchLocalApi<ManualCommConfig>('/automation/manual/comm-config');
}

export async function updateManualCommConfig(
  robotHost: string,
  robotPort: number,
  visionHost: string,
  visionPort: number
): Promise<ManualCommConfig> {
  return fetchLocalApi<ManualCommConfig>('/automation/manual/comm-config', {
    method: 'POST',
    body: JSON.stringify({
      robot_host: robotHost,
      robot_port: robotPort,
      vision_host: visionHost,
      vision_port: visionPort,
    }),
  });
}

export async function getManualModbusRegisters(startAddr: number, endAddr: number): Promise<ModbusRegistersResponse> {
  return fetchLocalApi<ModbusRegistersResponse>(
    `/automation/manual/modbus/registers?start_addr=${startAddr}&end_addr=${endAddr}`
  );
}

export async function writeManualModbusRegister(address: number, value: number): Promise<ModbusWriteResponse> {
  return fetchLocalApi<ModbusWriteResponse>('/automation/manual/modbus/write', {
    method: 'POST',
    body: JSON.stringify({ address, value }),
  });
}

export interface AutomationIoState {
  ok: boolean;
  board_no: number;
  available_boards?: number[];
  available_input_boards?: number[];
  available_output_boards?: number[];
  io_type?: string;
  count: number;
  simulation: boolean;
  inputs: boolean[];
  outputs: boolean[];
  input_labels?: string[];
  output_labels?: string[];
  timestamp?: string;
}

export async function getAutomationIoState(boardNo: number = 0, count: number = 32, ioType: 'all' | 'input' | 'output' = 'all'): Promise<AutomationIoState> {
  return fetchLocalApi<AutomationIoState>(
    `/automation/manual/io/state?board_no=${boardNo}&count=${count}&io_type=${ioType}`
  );
}

export async function writeAutomationIoOutput(boardNo: number, offset: number, value: boolean): Promise<{ ok: boolean; value?: boolean; timestamp?: string }> {
  return fetchLocalApi<{ ok: boolean; value?: boolean; timestamp?: string }>('/automation/manual/io/output', {
    method: 'POST',
    body: JSON.stringify({ board_no: boardNo, offset, value }),
  });
}
