import { useEffect, useRef, useState, useCallback } from 'react';

const websocketUrl = () => {
  if (process.env.REACT_APP_WS_URL) return process.env.REACT_APP_WS_URL;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.hostname}:8000/ws`;
};

const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_TIMEOUT_MS = 5000;

export const useWebSocket = (onMessage) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const ws = useRef(null);
  const reconnectTimeout = useRef(null);
  const heartbeatInterval = useRef(null);
  const heartbeatTimeout = useRef(null);
  const shouldReconnect = useRef(true);

  const clearTimers = useCallback(() => {
    clearTimeout(reconnectTimeout.current);
    clearInterval(heartbeatInterval.current);
    clearTimeout(heartbeatTimeout.current);
    reconnectTimeout.current = null;
    heartbeatInterval.current = null;
    heartbeatTimeout.current = null;
  }, []);

  const connect = useCallback(() => {
    const url = websocketUrl();
    try {
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        setIsConnected(true);
        // eslint-disable-next-line no-console
        console.log('[WS] connected', { url, time: new Date().toISOString() });

        const heartbeat = () => {
          if (ws.current?.readyState !== WebSocket.OPEN) return;
          ws.current.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
          clearTimeout(heartbeatTimeout.current);
          heartbeatTimeout.current = setTimeout(() => {
            console.warn('[WS] heartbeat timeout');
            setIsConnected(false);
            ws.current?.close();
          }, HEARTBEAT_TIMEOUT_MS);
        };
        heartbeat();
        heartbeatInterval.current = setInterval(heartbeat, HEARTBEAT_INTERVAL_MS);
      };

      ws.current.onmessage = (event) => {
        clearTimeout(heartbeatTimeout.current);
        heartbeatTimeout.current = null;
        setIsConnected(true);
        let message = null;
        try {
          message = JSON.parse(event.data);
        } catch (e) {
          // eslint-disable-next-line no-console
          console.warn('[WS] failed to parse message', e);
          return;
        }
        setLastMessage(message);
        if (message?.type === 'pcba_event') {
          // eslint-disable-next-line no-console
          console.log('[WS] pcba_event received', {
            serial: message?.data?.serial,
            stage: message?.data?.stage,
            status: message?.data?.status,
            timestamp: message?.timestamp,
          });
        }
        if (onMessage) {
          onMessage(message);
        }
      };

      ws.current.onerror = (error) => {
        setIsConnected(false);
        // eslint-disable-next-line no-console
        console.warn('[WS] error', error);
        ws.current?.close();
      };

      ws.current.onclose = () => {
        setIsConnected(false);
        clearInterval(heartbeatInterval.current);
        clearTimeout(heartbeatTimeout.current);
        heartbeatInterval.current = null;
        heartbeatTimeout.current = null;
        // eslint-disable-next-line no-console
        console.log('[WS] disconnected');
        if (shouldReconnect.current) {
          reconnectTimeout.current = setTimeout(() => connect(), 3000);
        }
      };
    } catch (error) {
      setIsConnected(false);
      console.error('WebSocket connection error:', error);
      if (shouldReconnect.current) {
        reconnectTimeout.current = setTimeout(() => connect(), 3000);
      }
    }
  }, [onMessage]);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    clearTimers();
    if (ws.current) {
      ws.current.onclose = null;
      ws.current.close();
      ws.current = null;
    }
    setIsConnected(false);
  }, [clearTimers]);

  const sendMessage = useCallback((message) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  useEffect(() => {
    shouldReconnect.current = true;
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return { isConnected, lastMessage, sendMessage };
};
