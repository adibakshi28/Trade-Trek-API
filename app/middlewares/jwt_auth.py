# app/middlewares/jwt_auth.py

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from postgrest import APIError

from app.utils.token import decode_access_token
from app.models.database import supabase

auth_scheme = HTTPBearer()

def require_jwt_wb_auth(token: str) -> dict:
    """
    Verifies the JWT. Returns the decoded payload if valid. (This function is for WebSocket authentication ,requires a token as a string in arg)
    """
    try:
        payload = decode_access_token(token)
        if payload.get("user_id") is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload

def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)) -> dict:
    """
    Verifies the JWT. Returns the decoded payload if valid.
    """
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload

def require_active_session(payload: dict = Depends(require_jwt)) -> dict:
    """
    Ensures the user from the JWT has an ACTIVE session in the DB.
    Raises 401 if there's no active session for that user_id.
    """
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    try:
        # Query Sessions table to see if there's an active session
        resp = supabase.table("Sessions") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .limit(1) \
            .execute()

        active_sessions = resp.data if resp.data else []
        if len(active_sessions) == 0:
            # No active session found, raise 401
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No active session found for this user."
            )
    except APIError as e:
        # If supabase call fails
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking session: {str(e)}"
        )

    # If we get here, there's an active session
    return payload  # we can return the same JWT payload for further usage
