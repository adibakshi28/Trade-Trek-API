# app/utils/helpers.py

import os
import httpx
import random
import string
from passlib.context import CryptContext
from typing import Dict, Any, List
from httpx import RemoteProtocolError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def generate_random_string(length=10):
    """Generate a random alphanumeric string of a given length."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def make_request(base_url: str, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make an asynchronous HTTP GET request to API.
    """

    url = f"{base_url}{endpoint}"

    # full_url = httpx.URL(url, params=params)
    # print(f"📤 Outgoing GET Request: {full_url}")

    try:
        async with httpx.AsyncClient(http2=False, timeout=30) as client:
            for attempt in range(3):
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, RemoteProtocolError) as e:
                    if attempt < 2:
                        print(f"Retrying request due to {e} (Attempt {attempt + 1}/3)")
                    else:
                        raise ConnectionError(f"❌ Max retries exceeded: {e}")
    except httpx.TimeoutException:
        raise ConnectionError("❌ API request timed out.")
    except httpx.HTTPStatusError as e:
        raise ConnectionError(f"❌ HTTP Error: {e}")
    except RemoteProtocolError:
        raise ConnectionError("❌ Remote Protocol Error: The server disconnected unexpectedly.")
    except httpx.RequestError as e:
        raise ConnectionError(f"❌ Error in API Request: {e}")
