/**
 * Formlabs 프린터 타입 정의
 * 백엔드 스키마와 동기화
 */

// ===========================================
// 열거형 정의
// ===========================================

export type PrintStatus =
  | 'QUEUED'
  | 'PREPRINT'
  | 'PREHEAT'
  | 'PRECOAT'
  | 'PRINTING'
  | 'POSTCOAT'
  | 'PAUSING'
  | 'PAUSED'
  | 'ABORTING'
  | 'FINISHED'
  | 'ABORTED'
  | 'ERROR'
  | 'WAITING_FOR_RESOLUTION';

export type PrinterReadyState =
  | 'READY'
  | 'NOT_READY'
  | 'READY_TO_PRINT_READY'
  | 'READY_TO_PRINT_NOT_READY';

export type BuildPlatformState =
  | 'EMPTY'
  | 'HAS_PARTS'
  | 'BUILD_PLATFORM_CONTENTS_EMPTY'
  | 'BUILD_PLATFORM_CONTENTS_HAS_PARTS'
  | 'BUILD_PLATFORM_CONTENTS_MISSING';

export type NotificationType =
  | 'PRINT_COMPLETE'
  | 'PRINT_ERROR'
  | 'LOW_RESIN'
  | 'PRINTER_OFFLINE';

// 대시보드 표시용 상태
export type PrinterDisplayStatus =
  | 'IDLE'
  | 'PRINTING'
  | 'PREHEAT'
  | 'PAUSING'
  | 'PAUSED'
  | 'ABORTING'
  | 'FINISHED'
  | 'ERROR'
  | 'OFFLINE';

// ===========================================
// 프린트 작업
// ===========================================

export interface CurrentPrintRun {
  guid: string | null;
  name: string | null;
  status: PrintStatus | null;
  currently_printing_layer: number;
  layer_count: number;
  estimated_duration_ms: number;
  elapsed_duration_ms: number;
  estimated_time_remaining_ms: number;
  print_started_at: string | null;
  print_finished_at: string | null;
}

// ===========================================
// 소모품
// ===========================================

export interface CartridgeStatus {
  serial: string | null;
  material_code: string | null;
  material_name: string | null;
  initial_ml: number;
  remaining_ml: number;
}

export interface TankStatus {
  serial: string | null;
  material_code: string | null;
  print_count: number;
  days_since_first_print: number;
}

// ===========================================
// 프린터 상태
// ===========================================

export interface PrinterStatus {
  status: string | null;
  last_pinged_at: string | null;
  current_print_run: CurrentPrintRun | null;
  ready_to_print: PrinterReadyState | null;
  build_platform_contents: BuildPlatformState | null;
}

export interface Printer {
  serial: string;
  alias: string | null;
  machine_type: string | null;
  printer_status: PrinterStatus | null;
  cartridge_status: CartridgeStatus | null;
  tank_status: TankStatus | null;
  firmware_version: string | null;
  created_at: string | null;
}

// ===========================================
// 대시보드용 요약
// ===========================================

export interface PrinterSummary {
  serial: string;
  name: string;
  status: PrinterDisplayStatus;
  current_job_name: string | null;
  progress_percent: number | null;
  remaining_minutes: number | null;
  elapsed_minutes: number | null;
  estimated_total_minutes: number | null;
  current_layer: number | null;
  total_layers: number | null;
  print_started_at: string | null;
  print_phase: string | null;
  temperature: number | null;
  resin_remaining_ml: number | null;
  resin_remaining_percent: number | null;
  is_resin_low: boolean;
  cartridge_material_code: string | null;
  cartridge_material_name: string | null;
  machine_type: string | null;
  firmware_version: string | null;
  tank_serial: string | null;
  tank_material_code: string | null;
  tank_print_count: number | null;
  is_online: boolean;
  is_ready: boolean;
  ready_to_print: string | null;
  build_platform_contents: string | null;
  has_error: boolean;
  last_update: string;
}

export interface DashboardData {
  printers: PrinterSummary[];
  total_printers: number;
  printers_printing: number;
  printers_idle: number;
  printers_error: number;
  printers_offline: number;
  last_update: string;
}

// ===========================================
// 알림
// ===========================================

export interface Notification {
  type: NotificationType;
  printer_serial: string;
  printer_name: string;
  title: string;
  message: string;
  timestamp: string;
  job_name: string | null;
  error_details: string | null;
}

// ===========================================
// 프린트 이력
// ===========================================

export interface PrintHistoryPart {
  display_name: string;
  volume_ml: number | null;
  stl_path: string | null;
}

export interface PrintHistoryItem {
  guid: string;
  name: string;
  printer_serial: string;
  printer_name: string | null;
  status: PrintStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_minutes: number | null;
  layer_count: number;
  material_code: string | null;
  material_name: string | null;
  estimated_ml_used: number | null;
  // 상세 정보 (확장)
  message: string | null;
  print_run_success: string | null;
  thumbnail_url: string | null;
  volume_ml: number | null;
  parts: PrintHistoryPart[];
}

export interface PrintHistoryResponse {
  items: PrintHistoryItem[];
  total_count: number;
  page: number;
  page_size: number;
}

// ===========================================
// WebSocket 메시지
// ===========================================

export interface WebSocketMessage {
  type: 'dashboard_update' | 'notification' | 'printer_update';
  data: DashboardData | Notification | PrinterSummary;
  timestamp: string;
}

// ===========================================
// 유틸리티 함수
// ===========================================

export function getStatusColor(status: PrinterDisplayStatus): string {
  switch (status) {
    case 'PRINTING':
      return 'blue';
    case 'PREHEAT':
      return 'orange';
    case 'PAUSING':
    case 'PAUSED':
      return 'yellow';
    case 'ABORTING':
      return 'red';
    case 'FINISHED':
      return 'green';
    case 'IDLE':
      return 'gray';
    case 'ERROR':
      return 'red';
    case 'OFFLINE':
      return 'gray';
    default:
      return 'gray';
  }
}

export function getStatusLabel(status: PrinterDisplayStatus): string {
  switch (status) {
    case 'PRINTING':
      return '출력 중';
    case 'PREHEAT':
      return '예열 중';
    case 'PAUSING':
      return '일시정지 중';
    case 'PAUSED':
      return '일시정지됨';
    case 'ABORTING':
      return '중단 중';
    case 'FINISHED':
      return '완료';
    case 'IDLE':
      return '대기 중';
    case 'ERROR':
      return '오류';
    case 'OFFLINE':
      return '오프라인';
    default:
      return '알 수 없음';
  }
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${minutes}분`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}시간 ${mins}분` : `${hours}시간`;
}

export function formatResinAmount(ml: number | null): string {
  if (ml === null) return '-';
  return `${ml.toFixed(0)}ml`;
}
