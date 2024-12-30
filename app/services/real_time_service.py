# app/services/real_time_service.py

import time
from collections import defaultdict
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import config
from app.models.sqlite_cache import set_cache, get_cache

NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY = config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY']


class RealTimeService:
    def __init__(self):
        # Track active connections by user_id (int → WebSocket)
        self.active_connections: Dict[int, WebSocket] = {}
        self.message_count: defaultdict = defaultdict(int)
        self.last_message_time: defaultdict = defaultdict(float)

    async def connect(self, websocket: WebSocket, user_id: int):
        """Allow only one active WebSocket connection per user ID."""
        if user_id in self.active_connections:
            old_connection = self.active_connections[user_id]
            # print(f"🔄 Replacing existing connection for user_id: {user_id}")
            try:
                await old_connection.close(code=1000, reason="New connection established")
            except Exception as e:
                print(f"⚠️ Failed to close previous WebSocket connection for user_id {user_id}: {e}")
            finally:
                await self.disconnect(user_id)

        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"🔗 User {user_id} connected. Total active connections: {len(self.active_connections)}")
        await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))

    async def disconnect(self, user_id: int):
        """Remove a WebSocket connection by user ID."""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            try:
                # Check if the connection is still open before attempting to close
                if websocket.client_state == "CONNECTED":
                    await websocket.close(code=1001, reason="Connection closed by server")
            except Exception as e:
                print(f"⚠️ Failed to close WebSocket connection for user_id {user_id}: {e}")
            finally:
                del self.active_connections[user_id]
                self.message_count.pop(user_id, None)
                self.last_message_time.pop(user_id, None)
                print(f"🔨 User {user_id} disconnected. Total active connections: {len(self.active_connections)}")
                await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))


    async def broadcast(self, message: str):
        """Broadcast a message to all connected clients with rate limiting."""
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            try:
                now = time.time()
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected_users.append(user_id)
        
        for user_id in disconnected_users:
            await self.disconnect(user_id)

    async def close_all_connections(self):
        """Gracefully close all active WebSocket connections."""
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            try:
                await connection.close(code=1001, reason="Server Shutdown")
            except Exception as e:
                print(f"⚠️ Failed to close WebSocket connection for user_id {user_id}: {e}")
            finally:
                disconnected_users.append(user_id)
        
        for user_id in disconnected_users:
            await self.disconnect(user_id)


# Singleton instance
real_time_service = RealTimeService()