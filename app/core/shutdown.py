from fastapi import FastAPI
from app.models.sqlite_cache import close_db 
from app.core.websocket import close_finnhub_connection
from app.services.real_time_service import real_time_service


async def close_sqlite_connection():
    """
    Close the shared SQLite database connection gracefully.
    """
    try:
        await close_db()
        print("✅ SQLite connection closed successfully.")
    except Exception as e:
        print(f"❌ Failed to close SQLite connection: {e}")


async def close_finnhub_websocket_connection():
    """
    Close Finnhub websocket connection gracefully.
    """
    try:
        await close_finnhub_connection()
        print("✅ Finnhub WebSocket closed successfully.")
    except Exception as e:
        print(f"❌ Failed to close Finnhub WebSocket: {e}")

async def close_all_BEFE_websocket_connections():
    """
    Close FE<->BE websocket connections gracefully.
    """
    try:
        await real_time_service.close_all_connections()
        print("✅ All FE<->BE websocket closed gracefully.")
    except Exception as e:
        print(f"❌ Failed to close FE<->BE WebSockets: {e}")


def register_shutdown_events(app: FastAPI):
    """
    Register all shutdown-related events
    """
    @app.on_event("shutdown")
    async def shutdown_events():
        print("💤 Running Shutdown Events...")

        try:
            await close_finnhub_websocket_connection()
            await close_all_BEFE_websocket_connections()
            await close_sqlite_connection()
            print("💤 All shutdown events completed successfully!")
        except Exception as e:
            print(f"❌ Shutdown events encountered an error: {e}")
