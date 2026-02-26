/**
 * Local API 타입 정의
 * Phase 2: 프리셋 관리, 파일 업로드, 프린트 작업
 */

// ===========================================
// 레진 종류
// ===========================================

export type MaterialCode =
  | 'FLGPGR05'  // Grey V5
  | 'FLGPCL05'  // Clear V5
  | 'FLGPWH05'  // White V5
  | 'FLGPBK05'  // Black V5
  | 'FLTO1500'  // Tough 1500
  | 'FLTOTL02'  // Tough 2000
  | 'FLDUCL01'  // Durable
  | 'FLFX8001'  // Flexible 80A
  | 'FLEL5001'; // Elastic 50A

export const MATERIAL_NAMES: Record<MaterialCode, string> = {
  'FLGPGR05': 'Grey V5',
  'FLGPCL05': 'Clear V5',
  'FLGPWH05': 'White V5',
  'FLGPBK05': 'Black V5',
  'FLTO1500': 'Tough 1500',
  'FLTOTL02': 'Tough 2000',
  'FLDUCL01': 'Durable',
  'FLFX8001': 'Flexible 80A',
  'FLEL5001': 'Elastic 50A',
};

export type SupportDensity = 'light' | 'normal' | 'heavy';

// ===========================================
// 프린트 설정
// ===========================================

export interface OrientationSettings {
  x_rotation: number;
  y_rotation: number;
  z_rotation: number;
}

export interface SupportSettings {
  density: SupportDensity;
  touchpoint_size: number;
  internal_supports: boolean;
}

export interface PrintSettings {
  machine_type: string;
  material_code: MaterialCode;
  layer_thickness_mm: number;
  orientation: OrientationSettings;
  support: SupportSettings;
}

// ===========================================
// 프리셋
// ===========================================

export interface Preset {
  id: string;
  name: string;
  part_type: string;
  description: string | null;
  settings: PrintSettings;
  stl_filename: string | null;
  created_at: string;
  updated_at: string;
  print_count: number;
}

export interface PresetCreate {
  name: string;
  part_type: string;
  description?: string;
  settings?: PrintSettings;
  stl_filename?: string;
}

export interface PresetUpdate {
  name?: string;
  part_type?: string;
  description?: string;
  settings?: PrintSettings;
  stl_filename?: string;
}

export interface PresetListResponse {
  items: Preset[];
  total: number;
}

// ===========================================
// 파일 업로드
// ===========================================

export interface UploadedFile {
  filename: string;
  size_bytes: number;
  path?: string;
  modified_at?: number;
}

export interface FileListResponse {
  files: UploadedFile[];
}

// ===========================================
// 프린트 작업
// ===========================================

export type PrintJobStatus =
  | 'pending'
  | 'preparing'
  | 'ready'
  | 'sending'
  | 'sent'
  | 'failed';

export interface PrintJob {
  id: string;
  preset_id: string | null;
  stl_filename: string;
  printer_serial: string;
  status: PrintJobStatus;
  settings: PrintSettings;
  scene_id: string | null;
  error_message: string | null;
  scheduled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PrintJobCreate {
  preset_id?: string;
  stl_file?: string;
  printer_serial: string;
  copies?: number;
  settings?: PrintSettings;
  scheduled_at?: string;
}

// ===========================================
// PreFormServer
// ===========================================

export interface DiscoveredPrinter {
  serial: string;
  name: string;
  ip_address: string;
  machine_type: string;
  is_online: boolean;
}

export interface LocalApiHealth {
  local_api: string;
  preform_server: 'connected' | 'disconnected';
  preform_server_url: string;
}

// ===========================================
// 슬라이스 예측
// ===========================================

export interface SceneEstimate {
  scene_id: string;
  estimated_print_time_ms: number | null;
  estimated_print_time_min: number | null;
  estimated_material_ml: number | null;
  layer_count: number | null;
  machine_type: string;
  material_code: string;
  model_count: number;
  validation?: Record<string, unknown> | null;
}

export interface ScenePrepareRequest {
  stl_file: string;
  machine_type?: string;
  material_code?: string;
  layer_thickness_mm?: number;
  support_density?: string;
  touchpoint_size?: number;
  hollow?: boolean;
  hollow_wall_thickness_mm?: number;
}

export interface DuplicateResult {
  success: boolean;
  model_count: number;
  estimated_print_time_ms: number | null;
  estimated_print_time_min: number | null;
  estimated_material_ml: number | null;
  validation: Record<string, unknown> | null;
}

// ===========================================
// 유틸리티 함수
// ===========================================

export function getJobStatusLabel(status: PrintJobStatus): string {
  switch (status) {
    case 'pending': return '대기 중';
    case 'preparing': return '준비 중';
    case 'ready': return '준비 완료';
    case 'sending': return '전송 중';
    case 'sent': return '전송 완료';
    case 'failed': return '실패';
    default: return '알 수 없음';
  }
}

export function getJobStatusColor(status: PrintJobStatus): string {
  switch (status) {
    case 'pending': return 'gray';
    case 'preparing': return 'yellow';
    case 'ready': return 'blue';
    case 'sending': return 'blue';
    case 'sent': return 'green';
    case 'failed': return 'red';
    default: return 'gray';
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
