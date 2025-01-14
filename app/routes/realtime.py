# app/routes/realtime.py

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.services.real_time_service import real_time_service
from app.middlewares.jwt_auth import require_jwt_wb_auth, require_active_session

router = APIRouter()

async def authenticate_websocket(token: str):
    """
    Validate JWT token passed as a query parameter during WebSocket connection.
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid token in query parameters"
        )
    try:
        payload = require_jwt_wb_auth(token)  # Validate JWT token
        payload = require_active_session(payload)  # Ensure active session in DB
        return payload
    except HTTPException as auth_error:
        print(f"❌ Authentication failed: {auth_error.detail}")
        raise auth_error


@router.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """
    WebSocket endpoint for real-time updates (Protected via JWT in Query Params)
    """
    try:
        # Authenticate WebSocket connection manually
        payload = await authenticate_websocket(token)
        user_id = int(payload.get("user_id"))
        # print(f"✅ WebSocket connection authenticated for user_id: {user_id}")
        
        await real_time_service.connect(websocket, user_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                print(f"📨 Received data from user_id {user_id}: {data}")
                
                try:
                    message_dict = json.loads(data)
                    await real_time_service.handle_incoming_message(user_id, message_dict)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON received from user_id {user_id}: {e}")

        except WebSocketDisconnect:
            # print(f"❌ WebSocket client disconnected (user_id: {user_id}).")
            await real_time_service.disconnect(user_id)
        except Exception as e:
            print(f"⚠️ Error in WebSocket communication: {e}")
            await real_time_service.disconnect(user_id)
    
    except HTTPException as auth_error:
        print(f"❌ Authentication failed: {auth_error.detail}")
        await websocket.close(code=1008)  # Policy Violation