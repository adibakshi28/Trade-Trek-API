from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.routes import auth, users, stocks, realtime
from app.core.exceptions import register_exception_handlers
from app.core.startup import register_startup_events
from app.core.shutdown import register_shutdown_events
from app import __version__, __author__

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

register_exception_handlers(app)
register_startup_events(app)
register_shutdown_events(app)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/user", tags=["Users"])
app.include_router(stocks.router, prefix="/stock", tags=["Stocks"])
app.include_router(realtime.router, tags=["WebSocket"])

@app.get("/")
def root():
    return {
        "message": "Welcome to the Mock Trader API Production! 🚀" ,
        "version": __version__,
        "author": __author__,
    }
