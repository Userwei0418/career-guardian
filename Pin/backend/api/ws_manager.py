"""
WebSocket 连接管理器
"""
import asyncio
import json
from typing import List, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)

        # 清理断开的连接
        async with self._lock:
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)


manager = ConnectionManager()
