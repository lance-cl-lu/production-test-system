import { useEffect, useRef, useState, useCallback } from 'react';

const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';

export const useWebSocket = (onMessage) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);
  const onMessageRef = useRef(onMessage);

  // 更新 onMessageRef，但不觸發重新連接
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(WS_URL);

      ws.current.onopen = () => {
        setIsConnected(true);
        // Lifecycle log
        // eslint-disable-next-line no-console
        console.log('[WS] connected', { url: WS_URL, time: new Date().toISOString() });
      };

      ws.current.onmessage = (event) => {
        let message = null;
        try {
          message = JSON.parse(event.data);
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn('[WS] failed to parse message', e);
          return;
        }
        setLastMessage(message);
        // Message log (only key fields)
        if (message?.type === 'pcba_event') {
          // eslint-disable-next-line no-console
          console.log('[WS] pcba_event received', {
            serial: message?.data?.serial,
            stage: message?.data?.stage,
            status: message?.data?.status,
            timestamp: message?.timestamp,
          });
        }
        if (onMessageRef.current) onMessageRef.current(message);
      };

      ws.current.onerror = (err) => {
        // eslint-disable-next-line no-console
        console.warn('[WS] error', err);
      };

      ws.current.onclose = () => {
        setIsConnected(false);
        // eslint-disable-next-line no-console
        console.log('[WS] disconnected, will retry in 3s');
        reconnectTimeout.current = setTimeout(() => connect(), 3000);
      };
    } catch (error) {
      console.error('WebSocket connection error:', error);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
    if (ws.current) ws.current.close();
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { isConnected, lastMessage };
};
