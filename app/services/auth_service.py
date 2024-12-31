# app/services/auth_service.py

from typing import Optional, List, Dict
from postgrest import APIError

from app.models.database import supabase
from app.core.config import config
from app.utils.helpers import hash_password, verify_password
from app.utils.token import create_access_token

def register_user(first_name: str, last_name: str, email: str, username: str, password: str) -> Optional[Dict]:
    """
    Register a new user after verifying that the email and username are unique.
    Returns the newly created user dict on success, or raises an APIError on failure.
    """
    hashed_pw = hash_password(password)
    
    try:
        # Check if email or username already exists
        email_check = supabase.table("Users").select("email").eq("email", email).execute()
        username_check = supabase.table("Users").select("username").eq("username", username).execute()
        
        if email_check.data:
            raise ValueError("Email already exists. Please use a different email address.")
        if username_check.data:
            raise ValueError("Username already exists. Please use a different username.")
        
        # Insert new user
        data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "username": username,
            "password": hashed_pw,
            "is_active": True,
        }
        response = supabase.table("Users").insert(data).execute()
        
        inserted = response.data or []
    
        if inserted:
            id = inserted[0].get("id")

            data = {
                "user_id": id,
                "cash": round(config['INITIAL_CASH'], 2),
                "is_active": True,
            }
            response = supabase.table("Cash").insert(data).execute()

            return inserted[0]
        else:
            return None
    
    except ValueError as ve:
        # Handle uniqueness errors
        # print(str(ve))
        raise ve  # Re-raise to let the caller handle it
    
    except APIError as e:
        # Handle Supabase API errors
        # print("APIError:", str(e))
        raise e
    
    except Exception as ex:
        # Catch any unexpected exceptions
        # print("An unexpected error occurred:", str(ex))
        raise ex
    
async def login_user(email_or_username: str, password: str, ip_address: Optional[str] = None) -> Optional[str]:
    """
    1. Find user by email or username
    2. Verify password
    3. Invalidate old sessions
    4. Insert new session with new token
    """
    try:
        # Attempt to find user by email
        resp_email = supabase.table("Users").select("*").eq("email", email_or_username).execute()
        user_data = resp_email.data

        if not user_data:
            # If none found, try username
            resp_user = supabase.table("Users").select("*").eq("username", email_or_username).execute()
            user_data = resp_user.data

        if not user_data:
            raise ValueError("User not found. Please register first.")

        user = user_data[0]
        if "password" not in user:
            raise ValueError("User password not found. Please try again later.")

        if not verify_password(password, user["password"]):
            raise ValueError("Incorrect password.")

        # Make old sessions inactive
        supabase.table("Sessions").update({"is_active": False}).eq("user_id", user["id"]).execute()

        # Create new JWT
        token_data = {
            "user_id": user["id"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "username": user["username"]
        }
        access_token = create_access_token(token_data)

        # Insert new session
        supabase.table("Sessions").insert({
            "user_id": user["id"],
            "token": access_token,
            "ip_address": ip_address,
            "is_active": True
        }).execute()

        return access_token
    except APIError as e:
        raise e

def logout_user(user_id: int) -> None:
    """
    Deactivate all sessions for the given user.
    """
    try:
        supabase.table("Sessions").update({"is_active": False}).eq("user_id", user_id).execute()
    except APIError as e:
        raise e