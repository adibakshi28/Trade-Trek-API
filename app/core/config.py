import os
from pytz import timezone
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

config = {
    "FINNHUB_API_BASE_URL": "https://finnhub.io/api/v1/",
    "FINNHUB_WEBSOCKET_URL": "wss://ws.finnhub.io",
    "PASSWORD_ENCRYPTION_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": 90,
    "EXCHANGE": "US",
    "TIMEZONE": timezone("America/New_York"),
    'STOCK_UNIVERSE_CACHE_TABLE': 'Stock_Universe_Cache',
}
