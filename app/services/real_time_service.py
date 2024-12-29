# app/services/real_time_service.py

import time
from collections import defaultdict
from typing import List
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import config
from app.models.sqlite_cache import set_cache, get_cache

NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY = config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY']


class RealTimeService:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.message_count: defaultdict = defaultdict(int)
        self.last_message_time: defaultdict = defaultdict(float)

    async def connect(self, websocket: WebSocket):
        """Accept and add a WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"✅ New client connected. Total connections: {len(self.active_connections)}")
        await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.message_count.pop(websocket, None)
            self.last_message_time.pop(websocket, None)
            print(f"❌ Client disconnected. Total connections: {len(self.active_connections)}")
            await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))

    async def broadcast(self, message: str):
        """Broadcast a message to all connected clients with rate limiting."""
        disconnected_clients = []
        for connection in self.active_connections:
            try:
                now = time.time()
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected_clients.append(connection)
        
        for client in disconnected_clients:
            await self.disconnect(client)


    async def close_all_connections(self):
        """Gracefully close all active WebSocket connections."""
        disconnected_clients = []
        for connection in self.active_connections:
            try:
                await connection.close(code=1001, reason="Server Shutdown")
            except Exception as e:
                print(f"⚠️ Failed to close WebSocket connection: {e}")
            finally:
                disconnected_clients.append(connection)
        
        for client in disconnected_clients:
            await self.disconnect(client)

real_time_service = RealTimeService()