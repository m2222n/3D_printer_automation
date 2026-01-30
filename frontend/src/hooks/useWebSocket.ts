/**
 * WebSocket 훅
 * 실시간 업데이트 수신
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { DashboardData, WebSocketMessage } from '../types/printer';

interface UseWebSocketOptions {
  onMessage?: (data: WebSocketMessage) => void;
  onDashboardUpdate?: (data: DashboardData) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  reconnect: () => void;
  connectionError: string | null;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    onMessage,
    onDashboardUpdate,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // 기존 연결 정리
    if (wsRef.current) {
      wsRef.current.close();
    }

    // WebSocket URL 생성 (개발/프로덕션 환경 자동 감지)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] 연결됨');
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);

          // 콜백 호출
          onMessage?.(message);

          // 대시보드 업데이트 콜백
          if (message.type === 'dashboard_update' && onDashboardUpdate) {
            onDashboardUpdate(message.data as DashboardData);
          }
        } catch (error) {
          console.error('[WebSocket] 메시지 파싱 오류:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] 오류:', error);
        setConnectionError('WebSocket 연결 오류');
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] 연결 종료:', event.code, event.reason);
        setIsConnected(false);
        wsRef.current = null;

        // 재연결 시도
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1;
          console.log(
            `[WebSocket] ${reconnectInterval}ms 후 재연결 시도 (${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
          );
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        } else {
          setConnectionError('WebSocket 재연결 실패. 페이지를 새로고침하세요.');
        }
      };
    } catch (error) {
      console.error('[WebSocket] 연결 생성 오류:', error);
      setConnectionError('WebSocket 연결 생성 실패');
    }
  }, [onMessage, onDashboardUpdate, reconnectInterval, maxReconnectAttempts]);

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    setConnectionError(null);
    connect();
  }, [connect]);

  // 컴포넌트 마운트 시 연결
  useEffect(() => {
    connect();

    return () => {
      // 정리
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    isConnected,
    lastMessage,
    reconnect,
    connectionError,
  };
}
