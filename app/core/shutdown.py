from fastapi import FastAPI
from app.models.sqlite_cache import close_db 
from app.core.websocket import close_finnhub_connection


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


def register_shutdown_events(app: FastAPI):
    """
    Register all shutdown-related events
    """
    @app.on_event("shutdown")
    async def shutdown_events():
        print("💤 Running Shutdown Events...")

        try:
            await close_finnhub_websocket_connection()
            await close_sqlite_connection()
            print("💤 All shutdown events completed successfully!")
        except Exception as e:
            print(f"❌ Shutdown events encountered an error: {e}")
