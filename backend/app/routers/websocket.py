from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json
from datetime import datetime

router = APIRouter()


class ConnectionManager:
    """WebSocket 連線管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """廣播訊息給所有連線的客戶端"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending message: {e}")
                disconnected.append(connection)
        
        # 移除斷線的連線
        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端點"""
    await manager.connect(websocket)
    try:
        while True:
            # 接收客戶端訊息
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 回應客戶端
            await websocket.send_json({
                "type": "echo",
                "data": message,
                "timestamp": datetime.now().isoformat()
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_test_result(test_record: dict):
    """廣播測試結果到所有連線的客戶端"""
    message = {
        "type": "test_result",
        "data": test_record,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(message)


async def broadcast_system_status(status: dict):
    """廣播系統狀態"""
    message = {
        "type": "system_status",
        "data": status,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(message)
