import os
import sys
import requests
import asyncio
from fastapi import FastAPI
from app.jobs.scheduler import start_scheduler
from app.models.database import check_connection
from app.models.sqlite_cache import init_db, check_db_mode, set_cache
from app.core.cache import create_stock_universe_cache, create_active_user_stock_subscription_cache, create_and_populate_dormant_user_stock_subscription_cache
from app.core.websocket_active import connect_to_finnhub_active
from app.core.websocket_dormant import connect_to_finnhub_dormant
from app.models.database import supabase
from app.core.config import config

def validate_env_variables():
    """
    Validate critical environment variables.
    """
    required_env_vars = [
        "SECRET_KEY",
        "FINNHUB_API_KEY",
        "FINNHUB_API_KEY_2",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "TWELVE_DATA_API_KEY",
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
        "FINNHUB_STOCK_EXCHANGE",
        "FINNHUB_CRYPTO_EXCHANGE",
        "FINNHUB_FOREX_EXCHANGE",
        "TIMEZONE",
        "STOCK_UNIVERSE_CACHE_TABLE",
        "ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE",
        "DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE",
        "INITIAL_CASH",
        "ALLOW_FRACTIONAL_SHARES",
        "FRACTIONAL_SHARES_MIN_TRADE",
        "ALLOW_SHORT_SELLING",
        "MAX_ASSETS_IN_PORTFOLIO",
        "TRANSACTION_FEE",
        "NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY",
        "FE_BE_WEBSOCKET_MSG_DELAY",
        "FINNHUB_WEBSOCKET_MSG_DELAY",
        "TWELVE_DATA_BASE_URL",
        "PORTFOLIO_SNAPSHOT_DELAY",
        "MAX_STOCK_IN_WATCHLIST",
        "STOCK_INDEX_TICKER",
        "INITIAL_LTP_IN_CACHE",
        "ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY",
        "ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE",
        "DORMANT_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY",
        "DORMANT_FINNHUB_WEBSOCKET_BATCH_SIZE",
    ]

    missing_vars = [
        var for var in required_config_vars 
        if var not in config or config[var] is None
    ]

    if missing_vars:
        raise EnvironmentError(f"Missing or empty configuration values: {', '.join(missing_vars)}")
    
    print("✅ All required configurations are set and valid.")



def check_third_party_services(config: dict):
    """
    Check connectivity with a third-party service synchronously and print the API response.
    """
    FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
    if not FINNHUB_API_KEY:
        raise ValueError("FINNHUB_API_KEY is missing in environment variables.")
    
    finnhub_base_url = config.get("FINNHUB_API_BASE_URL")
    if not finnhub_base_url:
        raise ValueError("FINNHUB_API_BASE_URL is missing in config.")
    
    try:
        response = requests.get(
            f"{finnhub_base_url}quote?symbol=AAPL&token={FINNHUB_API_KEY}",
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
        raise Exception(f"Unexpected error while checking Finnhub API connection: {e}")
    

def validate_db_connection():
    """
    Check DB connection
    """
    if check_connection():
        print("✅ Connected to Supabase DB.")
    else:
        raise ConnectionError("Could NOT connect to Supabase DB. Check your SUPABASE_URL / SERVICE_KEY.")
    

def invalidate_any_active_session():
    """
    Invalidate any active user session
    """
    try:
        supabase.table("Sessions").update({"is_active": False}).eq("is_active", True).execute()
        print("✅ All active user sessions invalidated.")
    except Exception as e:
        raise Exception(f"Unexpected error while invalidating sessions: {e}")
    

async def initlize_in_memory_cache():
    """
    Initialize the SQLite in-memory cache and create cached tables.
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

        await create_stock_universe_cache()
        await create_active_user_stock_subscription_cache()
        await create_and_populate_dormant_user_stock_subscription_cache()
        await set_cache(config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY'], 0)

        print("✅ SQLite cache initiated and created.")
    except Exception as e:
        print(f"❌ Failed to initialize SQLite cache: {e}")


async def startup_finnhub_websocket_connection():
    """
    Connect to the Finnhub WebSocket.
    """
    try:
        asyncio.create_task(connect_to_finnhub_active())    
        asyncio.create_task(connect_to_finnhub_dormant())
        print("✅ Finnhub websocket (Active & Dormant) connection initlized.")
    except Exception as e:
        print(f"❌ Failed to initialize Finnhub websocket connection: {e}")


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
            # invalidate_any_active_session()                   # Uncomment this line when pushing to production
            await initlize_in_memory_cache()
            await startup_finnhub_websocket_connection()
            print("🚀 All Startup Checks Passed Successfully!")
        except Exception as e:
            print(f"❌ Startup Check Failed: {e}")
            os._exit(1)
        try:
            start_scheduler()
            print("✅ Scheduled jobs setup complete.")
        except Exception as e:
            print(f"❌ Failed to setup scheduled jobs: {e}")