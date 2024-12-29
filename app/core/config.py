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
    "STOCK_EXCHANGE": "US",
    "CRYPTO_EXCHANGE": "Binance",
    "FOREX_EXCHANGE": "fxcm",
    "TIMEZONE": timezone("America/New_York"),
    'STOCK_UNIVERSE_CACHE_TABLE': 'Stock_Universe_Cache',
    "STOCK_SUBSCRIPTION_CACHE_TABLE": "Stock_Subscription_Cache",
    "INITIAL_CASH": 100000,
    "ALLOW_FRACTIONAL_SHARES": True,
    "FRACTIONAL_SHARES_MIN_TRADE": 0.1,
    "ALLOW_SHORT_SELLING": True,
    "MAX_ASSETS_IN_PORTFOLIO": 10,
    "TRANSACTION_FEE": 0.0,
}
