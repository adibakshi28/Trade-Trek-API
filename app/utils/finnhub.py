import os
import httpx
from datetime import datetime
from dotenv import load_dotenv
from app.core.config import config, FINNHUB_API_KEY
from typing import Dict, Any, List
from httpx import RemoteProtocolError
from app.utils.helpers import make_request

load_dotenv()

FINNHUB_BASE_URL = config["FINNHUB_API_BASE_URL"]

# === FINNHUB API FUNCTIONS ===

async def get_stock_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported stock symbols for an exchange."""
    return await make_request(FINNHUB_BASE_URL, "stock/symbol", {"token": FINNHUB_API_KEY, "exchange": exchange})

async def get_crypto_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported crypto symbols for an exchange."""
    return await make_request(FINNHUB_BASE_URL, "crypto/symbol", {"token": FINNHUB_API_KEY,"exchange": exchange})

async def get_forex_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported forex symbols for an exchange."""
    return await make_request(FINNHUB_BASE_URL, "forex/symbol", {"token": FINNHUB_API_KEY,"exchange": exchange})

async def get_market_status(exchange: str) -> Dict[str, Any]:
    """Get the current market status for an exchange."""
    return await make_request(FINNHUB_BASE_URL, "stock/market-status", {"token": FINNHUB_API_KEY,"exchange": exchange})


async def get_market_holidays(exchange: str) -> List[Dict[str, Any]]:
    """Get a list of market holidays for an exchange."""
    return await make_request(FINNHUB_BASE_URL, "stock/market-holiday", {"token": FINNHUB_API_KEY,"exchange": exchange})


async def get_company_profile(symbol: str) -> Dict[str, Any]:
    """Get the general profile of a company by its symbol."""
    return await make_request(FINNHUB_BASE_URL, "stock/profile2", {"token": FINNHUB_API_KEY,"symbol": symbol})


async def get_company_news(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Get the latest company news."""
    return await make_request(FINNHUB_BASE_URL, "company-news", {"token": FINNHUB_API_KEY,"symbol": symbol, "from": from_date, "to": to_date})


async def get_basic_financials(symbol: str, metric: str = "all") -> Dict[str, Any]:
    """Get basic financial metrics for a company."""
    return await make_request(FINNHUB_BASE_URL, "stock/metric", {"token": FINNHUB_API_KEY,"symbol": symbol, "metric": metric})


async def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """Get real-time stock quote data."""
    return await make_request(FINNHUB_BASE_URL, "quote", {"token": FINNHUB_API_KEY,"symbol": symbol})