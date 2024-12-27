# app/routes/auth.py

from fastapi import APIRouter, HTTPException, status, Request, Depends
from typing import Optional

from app.services.auth_service import register_user, login_user, logout_user
from app.middlewares.jwt_auth import require_active_session

router = APIRouter()

@router.post("/register")
def register(first_name: str, last_name: str, email: str, username: str, password: str):
    """
    Register user if not registered (Unique Email and Username)
    """
    user = register_user(first_name, last_name, email, username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to register user."
        )
    return {"message": "User registered successfully", "user_id": user["id"]}

@router.post("/login")
async def login(email_or_username: str, password: str, request: Request):
    """
    Login registered user (Create active session). Responds with JWT used for protected routes
    """
    ip_address: Optional[str] = request.client.host
    token = await login_user(email_or_username, password, ip_address=ip_address)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    return {"access_token": token}

@router.post("/logout")
def logout(payload: dict = Depends(require_active_session)):
    """
    Logs out the user (Require valid session)
    """
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    logout_user(user_id)
    return {"message": "Successfully logged out"}
