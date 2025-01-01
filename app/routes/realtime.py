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
    try:
        print("🔑 Received token:", token)
        
        # Authenticate WebSocket connection manually
        payload = await authenticate_websocket(token)
        user_id = int(payload.get("user_id"))
        print(f"✅ WebSocket connection authenticated for user_id: {user_id}")
        
        # Connect the user
        await real_time_service.connect(websocket, user_id)
        print(f"🔗 User {user_id} connected to real-time service.")
        
        try:
            while True:
                data = await websocket.receive_text()
                print(f"📨 Received data from user_id {user_id}: {data}")
        
        except WebSocketDisconnect:
            print(f"❌ WebSocket client disconnected (user_id: {user_id}).")
            await real_time_service.disconnect(user_id)
        
        except Exception as e:
            print(f"⚠️ Unexpected error during WebSocket communication (user_id: {user_id}): {e}")
            await real_time_service.disconnect(user_id)
    
    except HTTPException as auth_error:
        print(f"❌ Authentication failed: {auth_error.detail}")
        await websocket.close(code=1008)  # Policy Violation
    
    except Exception as e:
        print(f"🛑 Critical WebSocket error: {e}")
        await websocket.close(code=1011)  # Internal Error

    finally:
        print(f"🔒 Connection cleanup complete for user_id: {user_id if 'user_id' in locals() else 'unknown'}")