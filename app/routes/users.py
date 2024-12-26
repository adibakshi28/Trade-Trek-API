# app/routes/users.py

from fastapi import APIRouter, Depends
from typing import List, Dict

from app.middlewares.jwt_auth import require_active_session
from app.services.user_service import user_transactions_service, user_funds_service, user_info_service

router = APIRouter()

@router.get("/")
def get_user_info(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns information about a specific user
    """
    user_id = payload.get("user_id")
    user = user_info_service(user_id)
    return user

@router.get("/transactions")
def get_user_transactions(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Return all user transactions
    """
    user_id = payload.get("user_id")
    transactions = user_transactions_service(user_id)
    return transactions

@router.get("/portfolio")
def get_user_portfolio(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Return all user transactions
    """
    user_id = payload.get("user_id")
    transactions = user_transactions_service(user_id)
    return transactions

@router.get("/funds")
def get_user_funds(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Return available funds for the user
    """
    user_id = payload.get("user_id")
    funds = user_funds_service(user_id)
    return funds

