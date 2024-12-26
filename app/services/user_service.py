# app/services/user_service.py

from typing import Optional, List, Dict
from postgrest import APIError

from app.models.database import supabase

def user_funds_service(user_id: int):
    try:
        response = supabase.table("Cash").select("user_id", "cash").eq("user_id", user_id).eq("is_active", True).execute()        
        return response.data[0] if response.data else {"user_id": user_id, "cash": 0}
    except APIError as e:
        raise e
    
def user_info_service(user_id: int):
    try:
        response = supabase.table("Users").select("id", "first_name", "last_name", "username", "email").eq("id", user_id).eq("is_active", True).execute()        
        return response.data[0] or {}
    except APIError as e:
        raise e
    
def user_transactions_service(user_id: int):
    try:
        response = supabase.table("Transactions").select("id", "user_id", "stock_ticker", "direction", "quantity", "execution_price", "created_at").eq("user_id", user_id).eq("is_active", True).execute()
        return response.data or []
    except APIError as e:
        raise e
    
def user_portfolio_service(user_id: int):
    try:
        response = supabase.table("Holdings").select("id", "user_id", "stock_ticker", "direction", "quantity", "execution_price", "created_at").eq("user_id", user_id).eq("is_active", True).execute()
        return response.data or []
    except APIError as e:
        raise e

