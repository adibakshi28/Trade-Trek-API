# app/routes/realtime.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.services.real_time_service import real_time_service
from app.middlewares.jwt_auth import require_jwt_wb_auth, require_active_session

router = APIRouter()

async def authenticate_websocket(token: str):
    """
    Validate JWT token passed as a query parameter during WebSocket connection.
    """
    print("🔍 [authenticate_websocket] Token received:", token)
    
    if not token:
        print("❌ [authenticate_websocket] Missing or invalid token in query parameters")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid token in query parameters"
        )
    
    try:
        print("🔑 [authenticate_websocket] Validating JWT token...")
        payload = require_jwt_wb_auth(token)  # Validate JWT token
        print("✅ [authenticate_websocket] JWT token validated. Payload:", payload)
        
        print("🛡️ [authenticate_websocket] Checking active session in DB...")
        payload = require_active_session(payload)  # Ensure active session in DB
        print("✅ [authenticate_websocket] Active session verified. Payload:", payload)
        
        return payload
    
    except HTTPException as auth_error:
        print(f"❌ [authenticate_websocket] Authentication failed: {auth_error.detail}")
        raise auth_error
    
    except Exception as e:
        print(f"⚠️ [authenticate_websocket] Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during authentication"
        )


@router.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """
    WebSocket endpoint for real-time updates (Protected via JWT in Query Params)
    """
    print("🔗 [websocket_endpoint] WebSocket connection initiated")
    print("🔑 [websocket_endpoint] Token received:", token)
    
    try:
        # Authenticate WebSocket connection manually
        payload = await authenticate_websocket(token)
        print("✅ [websocket_endpoint] User authenticated. Payload:", payload)
        
        user_id = int(payload.get("user_id"))
        print(f"👤 [websocket_endpoint] User ID: {user_id}")
        
        await real_time_service.connect(websocket, user_id)
        print(f"🔌 [websocket_endpoint] User {user_id} connected to real-time service.")
        
        try:
            while True:
                data = await websocket.receive_text()
                print(f"📨 [websocket_endpoint] Received data from user_id {user_id}: {data}")
        except WebSocketDisconnect:
            print(f"❌ [websocket_endpoint] User {user_id} disconnected.")
            await real_time_service.disconnect(user_id)
        except Exception as e:
            print(f"⚠️ [websocket_endpoint] Error in WebSocket communication: {e}")
            await real_time_service.disconnect(user_id)
    
    except HTTPException as auth_error:
        print(f"❌ [websocket_endpoint] Authentication failed: {auth_error.detail}")
        await websocket.close(code=1008)  # Policy Violation
    
    except Exception as e:
        print(f"⚠️ [websocket_endpoint] Unexpected error: {e}")
        await websocket.close(code=1011)  # Internal Error
