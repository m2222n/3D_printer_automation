/**
 * API 서비스
 * 백엔드와 REST API 통신
 */

import type { DashboardData, Printer, PrinterSummary, PrintHistoryResponse } from '../types/printer';

const API_BASE = '/api/v1';

// ApiError 클래스
function createApiError(status: number, message: string): Error {
  const error = new Error(message);
  error.name = 'ApiError';
  (error as Error & { status: number }).status = status;
  return error;
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw createApiError(response.status, `API Error: ${response.statusText}`);
  }

  return response.json();
}

// 대시보드 데이터 조회
export async function getDashboard(): Promise<DashboardData> {
  return fetchApi<DashboardData>('/dashboard');
}

// 프린터 목록 조회
export async function getPrinters(): Promise<Printer[]> {
  return fetchApi<Printer[]>('/printers');
}

// 특정 프린터 상태 조회 (raw)
export async function getPrinter(serial: string): Promise<Printer> {
  return fetchApi<Printer>(`/printers/${serial}`);
}

// 특정 프린터 요약 조회 (PrinterSummary)
export async function getPrinterSummary(serial: string): Promise<PrinterSummary> {
  return fetchApi<PrinterSummary>(`/printers/${serial}`);
}

// 프린트 이력 조회
export async function getPrintHistory(
  page: number = 1,
  pageSize: number = 20,
  filters?: {
    printer_serial?: string;
    status?: string;
    date_from?: string; // ISO 8601
    date_to?: string;   // ISO 8601
  }
): Promise<PrintHistoryResponse> {
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('page_size', String(pageSize));
  if (filters?.printer_serial) params.set('printer_serial', filters.printer_serial);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  return fetchApi<PrintHistoryResponse>(`/prints?${params.toString()}`);
}

// 통계 조회
export interface StatisticsData {
  total_prints: number;
  total_material_ml: number;
  material_usage: { code: string; name: string; total_ml: number; count: number }[];
  prints_over_time: { date: string; count: number }[];
  printer_stats: {
    serial: string;
    name: string;
    total_prints: number;
    completed: number;
    failed: number;
    total_duration_minutes: number;
    total_material_ml: number;
    days_printed: number;
    total_days: number;
    utilization_percent: number;
  }[];
}

export async function getStatistics(
  filters?: {
    printer_serial?: string;
    date_from?: string;
    date_to?: string;
  }
): Promise<StatisticsData> {
  const params = new URLSearchParams();
  if (filters?.printer_serial) params.set('printer_serial', filters.printer_serial);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  const query = params.toString();
  return fetchApi<StatisticsData>(`/statistics${query ? '?' + query : ''}`);
}

// 서버 상태 확인
export async function getHealthCheck(): Promise<{ status: string; timestamp: string }> {
  return fetchApi<{ status: string; timestamp: string }>('/../health');
}

export { createApiError };
