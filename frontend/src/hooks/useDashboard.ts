/**
 * 대시보드 데이터 훅
 * REST API + WebSocket 실시간 업데이트 통합
 */

import { useState, useEffect, useCallback } from 'react';
import type { DashboardData } from '../types/printer';
import { getDashboard } from '../services/api';
import { useWebSocket } from './useWebSocket';

interface UseDashboardReturn {
  dashboard: DashboardData | null;
  isLoading: boolean;
  error: string | null;
  isConnected: boolean;
  refresh: () => Promise<void>;
}

export function useDashboard(): UseDashboardReturn {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 초기 데이터 로드
  const loadDashboard = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getDashboard();
      setDashboard(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : '데이터 로드 실패';
      setError(message);
      console.error('[Dashboard] 로드 오류:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // WebSocket 연결 (실시간 업데이트)
  const { isConnected } = useWebSocket({
    onDashboardUpdate: (data) => {
      setDashboard(data);
      setError(null);
    },
  });

  // 컴포넌트 마운트 시 초기 로드
  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // WebSocket 연결이 끊어지면 폴링으로 폴백
  useEffect(() => {
    if (!isConnected && !isLoading) {
      const interval = setInterval(() => {
        loadDashboard();
      }, 15000); // 15초마다 폴링

      return () => clearInterval(interval);
    }
  }, [isConnected, isLoading, loadDashboard]);

  return {
    dashboard,
    isLoading,
    error,
    isConnected,
    refresh: loadDashboard,
  };
}
