import { useCallback, useEffect, useRef, useState } from 'react';
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
  const onMessageRef = useRef<typeof onMessage>(onMessage);
  const onDashboardUpdateRef = useRef<typeof onDashboardUpdate>(onDashboardUpdate);
  const shouldReconnectRef = useRef(true);

  useEffect(() => {
    onMessageRef.current = onMessage;
    onDashboardUpdateRef.current = onDashboardUpdate;
  }, [onMessage, onDashboardUpdate]);

  const cleanupSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanupSocket();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);
          onMessageRef.current?.(message);
          if (message.type === 'dashboard_update') {
            onDashboardUpdateRef.current?.(message.data as DashboardData);
          }
        } catch (error) {
          console.error('[WebSocket] parse error:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] error:', error);
        setConnectionError('WebSocket connection error');
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        if (!shouldReconnectRef.current) {
          return;
        }

        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else {
          setConnectionError('WebSocket reconnect failed');
        }
      };
    } catch (error) {
      console.error('[WebSocket] create failed:', error);
      setConnectionError('WebSocket creation failed');
    }
  }, [cleanupSocket, maxReconnectAttempts, reconnectInterval]);

  const reconnect = useCallback(() => {
    shouldReconnectRef.current = true;
    reconnectAttemptsRef.current = 0;
    setConnectionError(null);
    connect();
  }, [connect]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      cleanupSocket();
    };
  }, [cleanupSocket, connect]);

  return {
    isConnected,
    lastMessage,
    reconnect,
    connectionError,
  };
}
