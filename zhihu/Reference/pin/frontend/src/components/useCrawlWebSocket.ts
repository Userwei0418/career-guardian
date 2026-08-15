"use client";

import { useEffect, useRef, useCallback, useState } from "react";

interface WSMessage {
  type: string;
  data?: any;
  message?: string;
}

export function useCrawlWebSocket(
  onTasksUpdate?: (data: any) => void,
  onMetricsUpdate?: (data: any) => void,
  onTaskUpdate?: (data: any) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const refreshInterval = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/crawl-status`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      ws.send(JSON.stringify({ action: "subscribe" }));
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        if (msg.type === "tasks_update" && onTasksUpdate) {
          onTasksUpdate(msg.data);
        } else if (msg.type === "metrics_update" && onMetricsUpdate) {
          onMetricsUpdate(msg.data);
        } else if (msg.type === "task_update" && onTaskUpdate) {
          onTaskUpdate(msg.data);
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // 5秒后重连
      setTimeout(() => connect(), 5000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [onTasksUpdate, onMetricsUpdate, onTaskUpdate]);

  const disconnect = useCallback(() => {
    if (refreshInterval.current) {
      clearInterval(refreshInterval.current);
    }
    wsRef.current?.close();
  }, []);

  const requestTasks = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "get_tasks" }));
    }
  }, []);

  const requestMetrics = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "get_metrics" }));
    }
  }, []);

  useEffect(() => {
    connect();
    return disconnect;
  }, [connect, disconnect]);

  // 定期请求更新
  useEffect(() => {
    if (connected) {
      requestTasks();
      requestMetrics();
      refreshInterval.current = setInterval(() => {
        requestTasks();
        requestMetrics();
      }, 3000);
    }
    return () => {
      if (refreshInterval.current) clearInterval(refreshInterval.current);
    };
  }, [connected, requestTasks, requestMetrics]);

  return { connected, requestTasks, requestMetrics };
}
