/**
 * 셀A 설비 상태(vision) · 셀B 빈피킹(binpick) 타입 — 10/16 통합 모니터링 패널
 * 서버 정본 = web-api/app/vision/schemas.py · web-api/app/binpick/schemas.py
 * 🚨 필드 이름은 서버와 1:1 — 여기서 이름을 바꾸면 조용히 undefined 가 된다(8/7 valid_pct 사고).
 */

// ── 셀A 설비 (세척기 · 경화기) ───────────────────────────────
export type VisionDeviceStatus =
  | 'wash_idle' | 'wash_running' | 'wash_complete'
  | 'cure_idle' | 'cure_running' | 'cure_complete'
  | 'offline' | 'error'
  | string;  // 서버 enum 이 늘어도 화면이 죽지 않게

export interface VisionDevice {
  type: string;                       // 'wash' | 'cure'
  id: number;
  name: string;
  status: VisionDeviceStatus;
  camera_id: string;
  is_online: boolean;
  last_status_change: string | null;  // ISO
  elapsed_since_change_s: number | null;
}

export interface VisionDeviceListResponse {
  devices: VisionDevice[];
}

export interface VisionWsMessage {
  type: 'vision_status_change' | 'vision_camera_online' | string;
  data: {
    camera_id: string;
    device_type?: string;
    device_id?: number;
    status?: VisionDeviceStatus;
    confidence?: number;
    timestamp?: string;
  };
}

// ── 셀B 빈피킹 ───────────────────────────────────────────────
export type BinpickVerdict = 'in_distribution' | 'borderline' | 'out_of_distribution' | 'not_checked' | string;

export interface BinpickDetection {
  idx: number;
  label: string | null;
  x: number | null;
  y: number | null;
  z: number | null;
  angle: number | null;
  confidence: number | null;
  gripper_width_mm: number | null;
}

export interface BinpickSceneGate {
  verdict: BinpickVerdict;
  trusted: boolean | null;
  valid_ratio_pct: number | null;
  note: string | null;
  n_dropped_by_size_gate: number;
}

export interface BinpickScene {
  scene_pk: string;
  scene_id: string | null;
  schema_version: string;
  module: string;
  n_detections: number;
  n_unique_labels: number;
  recognition_track: string | null;
  latency_ms: number | null;
  scene_gate: BinpickSceneGate;
  reported_at: string | null;
  received_at: string | null;
  detections: BinpickDetection[];
}

export interface BinpickWsMessage {
  type: 'binpick_scene' | string;
  scene_pk: string;
  scene_id: string | null;
  n_detections: number;
  gate_verdict: BinpickVerdict;
  latency_ms: number | null;
  received_at: string;
}
