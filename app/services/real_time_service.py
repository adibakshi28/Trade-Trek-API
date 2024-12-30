# app/services/real_time_service.py

from typing import Dict
from collections import defaultdict
from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import config
from app.models.sqlite_cache import execute_sql
from app.core.cache import (
    add_all_stocks_for_user_to_stock_subscription_cache,
    remove_all_stocks_for_user_from_stock_subscription_cache,
)
from app.models.sqlite_cache import set_cache

NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY = config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY']


class RealTimeService:
    def __init__(self):
        # Track active connections by user_id: user_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}

        # Optional counters
        self.message_count: defaultdict = defaultdict(int)
        self.last_message_time: defaultdict = defaultdict(float)

    async def connect(self, websocket: WebSocket, user_id: int):
        """Allow only one active WebSocket connection per user ID."""
        # If user already has an active connection, close it
        if user_id in self.active_connections:
            old_connection = self.active_connections[user_id]
            try:
                await old_connection.close(code=1000, reason="New connection established")
            except Exception as e:
                print(f"⚠️ Failed to close previous WebSocket for user_id {user_id}: {e}")
            finally:
                await self.disconnect(user_id)

        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"🔗 User {user_id} connected. Total active connections: {len(self.active_connections)}")

        # Update cached count
        await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))

        # Add all user stocks in the subscription cache
        await add_all_stocks_for_user_to_stock_subscription_cache(user_id)

    async def disconnect(self, user_id: int):
        """Remove WebSocket connection by user_id."""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            try:
                if websocket.client_state == "CONNECTED":
                    await websocket.close(code=1001, reason="Connection closed by server")
            except Exception as e:
                print(f"⚠️ Failed to close WebSocket for user_id {user_id}: {e}")
            finally:
                del self.active_connections[user_id]

                # Clean up counters
                self.message_count.pop(user_id, None)
                self.last_message_time.pop(user_id, None)

                print(f"🔨 User {user_id} disconnected. Total active connections: {len(self.active_connections)}")

                # Update cached count
                await set_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY, len(self.active_connections))

                # Remove all user stocks from the subscription cache
                await remove_all_stocks_for_user_from_stock_subscription_cache(user_id)

    async def broadcast(self, message: str):
        """Broadcast a message to all connected clients."""
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected_users.append(user_id)
        
        # Cleanup any closed connections
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