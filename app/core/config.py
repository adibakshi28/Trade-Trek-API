import os
from pytz import timezone
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
FINNHUB_API_KEY_2 = os.getenv("FINNHUB_API_KEY_2")       # Dormant stock sub ltp updates 
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")   # For Historical Data 

config = {
    "FINNHUB_API_BASE_URL": "https://finnhub.io/api/v1/",
    "FINNHUB_WEBSOCKET_URL": "wss://ws.finnhub.io",
    "PASSWORD_ENCRYPTION_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": 99999999,
    "FINNHUB_STOCK_EXCHANGE": "US",
    "FINNHUB_CRYPTO_EXCHANGE": "Binance",
    "FINNHUB_FOREX_EXCHANGE": "fxcm",
    "TIMEZONE": timezone("America/New_York"),
    'STOCK_UNIVERSE_CACHE_TABLE': 'Stock_Universe_Cache',
    "ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE": "Active_User_Stock_Subscription_Cache",
    "DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE": "Dormant_User_Stock_Subscription_Cache",
    "INITIAL_CASH": 100000,
    "ALLOW_FRACTIONAL_SHARES": True,
    "FRACTIONAL_SHARES_MIN_TRADE": 0.1,
    "ALLOW_SHORT_SELLING": True,
    "MAX_ASSETS_IN_PORTFOLIO": 10,
    "TRANSACTION_FEE": 0.0,
    "FE_BE_WEBSOCKET_MSG_DELAY": 1,        # Msg to FE every x seconds
    "FINNHUB_WEBSOCKET_MSG_DELAY": 0.5,   # LTP update from Finnhub every x seconds
    "NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY": "Number_Of_Active_Websockets_Cache",
    "TWELVE_DATA_BASE_URL": "https://api.twelvedata.com/",
    "PORTFOLIO_SNAPSHOT_DELAY": 12,        # Portfolio snapshot every x minutes
    "MAX_STOCK_IN_WATCHLIST": 10,
    "STOCK_INDEX_TICKER": "SPY",
    "INITIAL_LTP_IN_CACHE": -1,     # Initial LTP in (Active/Dormant) subscription cache indicating LTP not available yet (Keep it negative)
    "ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY": 1,  # One batch of stock remains subscribed for x seconds (Should be more than FINNHUB_WEBSOCKET_MSG_DELAY)
    "ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE": 48,       # Number of stocks to subscribe in one batch
    "DORMANT_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY": 3,  # One batch of stock remains subscribed for x seconds (Should be more than FINNHUB_WEBSOCKET_MSG_DELAY)
    "DORMANT_FINNHUB_WEBSOCKET_BATCH_SIZE": 48,       # Number of stocks to subscribe in one batch
    "REGISTER_USER_WATCHLIST": ['AAPL', "MSFT", "NVDA", "TSLA", "GS"],  # list of stock symbols to be added to watchlist of new users 
}
