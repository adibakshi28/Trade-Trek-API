import os
import sys
import requests
from fastapi import FastAPI
from app.jobs.scheduler import start_scheduler
from app.models.database import check_connection
from app.models.sqlite_cache import init_db, check_db_mode
from app.core.config import config


def validate_env_variables():
    """
    Validate critical environment variables.
    """
    required_env_vars = [
        "SECRET_KEY",
        "FINNHUB_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing_vars)}")
    print("✅ All required environment variables are set.")



def validate_configuration(config: dict):
    """
    Validate configurations.
    """
    required_config_vars = [
        "FINNHUB_API_BASE_URL",
        "FINNHUB_WEBSOCKET_URL",
        "PASSWORD_ENCRYPTION_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "EXCHANGE",
        "TIMEZONE",
    ]

    missing_vars = [
        var for var in required_config_vars 
        if var not in config or not config.get(var)
    ]

    if missing_vars:
        raise EnvironmentError(f"Missing or empty configuration values: {', '.join(missing_vars)}")
    
    print("✅ All required configurations are set and valid.")



def check_third_party_services(config: dict):
    """
    Check connectivity with a third-party service synchronously and print the API response.
    """
    finnhub_api_key = os.getenv("FINNHUB_API_KEY")
    if not finnhub_api_key:
        raise ValueError("FINNHUB_API_KEY is missing in environment variables.")
    
    finnhub_base_url = config.get("FINNHUB_API_BASE_URL")
    if not finnhub_base_url:
        raise ValueError("FINNHUB_API_BASE_URL is missing in config.")
    
    try:
        response = requests.get(
            f"{finnhub_base_url}quote?symbol=AAPL&token={finnhub_api_key}",
            timeout=10
        )
        
        try:
            api_response = response.json()
        except requests.JSONDecodeError:
            print("⚠️ Failed to parse JSON from Finnhub API response.")
        
        if response.status_code != 200:
            raise ConnectionError(f"API returned status code {response.status_code}: {response.text}")
        print("✅ Finnhub API is reachable.")
    
    except requests.Timeout:
        raise ConnectionError("Finnhub API connection timed out.")
    
    except requests.ConnectionError as e:
        raise ConnectionError(f"Error connecting to Finnhub API: {e}")
    
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")

    
    # TODO -> Check for finnhub websocket connection
    

def validate_db_connection():
    """
    Check DB connection
    """

    if check_connection():
        print("✅ Connected to Supabase DB.")
    else:
        raise ConnectionError("Could NOT connect to Supabase DB. Check your SUPABASE_URL / SERVICE_KEY.")
    

async def initlize_in_memory_cache():
    """
    Initialize the SQLite in-memory cache.
    """
    try:
        await init_db()

        inMemoryDBConfig = await check_db_mode()

        if (
            inMemoryDBConfig['journal_mode'] != 'memory' or
            len(inMemoryDBConfig['database_list']) == 0 or
            inMemoryDBConfig['database_list'][0][0] != 0 or
            inMemoryDBConfig['database_list'][0][1] != 'main' or
            inMemoryDBConfig['database_list'][0][2] != ''
        ):
            print("⚠️  SQLite DB is not configured correctly - Not in-memory mode.")

        print("✅ SQLite cache initiated.")
    except Exception as e:
        print(f"❌ Failed to initialize SQLite cache: {e}")
     

def register_startup_events(app: FastAPI):
    """
    Register all startup-related events to the app.
    """

    @app.on_event("startup")
    async def startup_events():

        print("🚀 Running Startup Checks...")
        try:
            validate_env_variables()
            validate_configuration(config=config)
            check_third_party_services(config=config)
            validate_db_connection()
            await initlize_in_memory_cache()
            print("🚀 All Startup Checks Passed Successfully!")
        except Exception as e:
            print(f"❌ Startup Check Failed: {e}")
            os._exit(1)

        try:
            start_scheduler()
            print("✅ Scheduled jobs setup complete.")
        except Exception as e:
            print(f"❌ Failed to setup scheduled jobs: {e}")