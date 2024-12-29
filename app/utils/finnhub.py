import os
import httpx
from datetime import datetime
from dotenv import load_dotenv
from app.core.config import config, FINNHUB_API_KEY
from typing import Dict, Any, List
from httpx import RemoteProtocolError

load_dotenv()

FINNHUB_BASE_URL = config["FINNHUB_API_BASE_URL"]

# === UTILITY FUNCTION ===
async def make_request(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make an asynchronous HTTP GET request to the Finnhub API.
    """

    url = f"{FINNHUB_BASE_URL}{endpoint}"
    params["token"] = FINNHUB_API_KEY

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
        raise ConnectionError("❌ Finnhub API request timed out.")
    except httpx.HTTPStatusError as e:
        raise ConnectionError(f"❌ HTTP Error: {e}")
    except RemoteProtocolError:
        raise ConnectionError("❌ Remote Protocol Error: The server disconnected unexpectedly.")
    except httpx.RequestError as e:
        raise ConnectionError(f"❌ Error in API Request: {e}")


# === FINNHUB API FUNCTIONS ===

async def get_stock_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported stock symbols for an exchange."""
    return await make_request("stock/symbol", {"exchange": exchange})

async def get_crypto_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported crypto symbols for an exchange."""
    return await make_request("crypto/symbol", {"exchange": exchange})

async def get_forex_symbols(exchange: str) -> List[Dict[str, Any]]:
    """Get the list of supported forex symbols for an exchange."""
    return await make_request("forex/symbol", {"exchange": exchange})

async def get_market_status(exchange: str) -> Dict[str, Any]:
    """Get the current market status for an exchange."""
    return await make_request("stock/market-status", {"exchange": exchange})


async def get_market_holidays(exchange: str) -> List[Dict[str, Any]]:
    """Get a list of market holidays for an exchange."""
    return await make_request("stock/market-holiday", {"exchange": exchange})


async def get_company_profile(symbol: str) -> Dict[str, Any]:
    """Get the general profile of a company by its symbol."""
    return await make_request("stock/profile2", {"symbol": symbol})


async def get_company_news(symbol: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Get the latest company news."""
    return await make_request("company-news", {"symbol": symbol, "from": from_date, "to": to_date})


async def get_basic_financials(symbol: str, metric: str = "all") -> Dict[str, Any]:
    """Get basic financial metrics for a company."""
    return await make_request("stock/metric", {"symbol": symbol, "metric": metric})


async def get_stock_quote(symbol: str) -> Dict[str, Any]:
    """Get real-time stock quote data."""
    return await make_request("quote", {"symbol": symbol})


# TODO: This is giving forbidden error
async def get_historical_stock_data(symbol: str, start_date: str, end_date: str, resolution: str = "D") -> List[Dict[str, Any]]:
    """
    Fetch historical stock data for a given symbol, date range, and resolution.

    Args:
        symbol (str): The stock ticker symbol (e.g., AAPL).
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
        resolution (str): Time interval resolution. Valid options are '1', '5', '15', '30', '60', 'D', 'W', 'M'.
    """

    response = await make_request("stock/candle", {"symbol": symbol, "resolution": resolution, "from": int(datetime.strptime(start_date, "%Y-%m-%d").timestamp()), "to": int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())})

    historical_data = []
    for i in range(len(response.get("t", []))):
        historical_data.append({
            "date": datetime.utcfromtimestamp(response["t"][i]).strftime("%Y-%m-%d %H:%M:%S"),
            "open": response["o"][i],
            "high": response["h"][i],
            "low": response["l"][i],
            "close": response["c"][i],
            "volume": response["v"][i]
        })
    return historical_data