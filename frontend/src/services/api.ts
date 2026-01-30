/**
 * API 서비스
 * 백엔드와 REST API 통신
 */

import type { DashboardData, Printer, PrintHistoryResponse } from '../types/printer';

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

// 특정 프린터 상태 조회
export async function getPrinter(serial: string): Promise<Printer> {
  return fetchApi<Printer>(`/printers/${serial}`);
}

// 프린트 이력 조회
export async function getPrintHistory(
  page: number = 1,
  pageSize: number = 20
): Promise<PrintHistoryResponse> {
  return fetchApi<PrintHistoryResponse>(`/prints?page=${page}&page_size=${pageSize}`);
}

// 서버 상태 확인
export async function getHealthCheck(): Promise<{ status: string; timestamp: string }> {
  return fetchApi<{ status: string; timestamp: string }>('/../health');
}

export { createApiError };
