import os
import httpx
from datetime import datetime
from dotenv import load_dotenv
from app.core.config import config, TWELVE_DATA_API_KEY
from typing import Dict, Any, List
from httpx import RemoteProtocolError
from app.utils.helpers import make_request

load_dotenv()

TWELVE_DATA_BASE_URL = config["TWELVE_DATA_BASE_URL"]

# === TWELEV DATA API FUNCTIONS ===

async def get_historical_stock_data(symbol: str, start_date: str, end_date: str, resolution: str = "1day") -> Dict[str, Any]:
    """
    Fetch historical stock data for a given symbol, date range, and resolution.

    Args:
        symbol (str): The stock ticker symbol (e.g., AAPL, BTC/USD).
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
        resolution (str): Time interval resolution. Valid options are '1min', '5min', '15min', '30min', '45min', '1h', '2h', '4h', '1day', '1week', '1month'.
    """
    try:
        if resolution not in ["1min", "5min", "15min", "30min", "45min", "1h", "2h", "4h", "1day", "1week", "1month"]:
            raise ValueError("Invalid resolution in passed to Twelve Data API")
        if not symbol and not start_date and not end_date:
            raise ValueError("Symbol, Start date and end date are required to fetch historical stock data from Twelve Data API")
        if start_date > end_date:
            raise ValueError("Start date cannot be greater than end date.")
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Please use 'YYYY-MM-DD' format.")

        response = await make_request(TWELVE_DATA_BASE_URL, "time_series", {
            "apikey": TWELVE_DATA_API_KEY,
            "symbol": symbol,
            "interval": resolution,
            "start_date": start_date,
            "end_date": end_date
        })

        if "status" in response and response["status"] == "ok" and "values" in response:
            response = response["values"]
            historical_data = [{
                "datetime": record["datetime"],
                "close": round(record["close"],2),
                "volume": record["volume"] if "volume" in record else 0
            } for record in response]
            return historical_data
        else:
            raise ValueError(f"Error fetching historical stock data from Twelve Data: {response}")
    except Exception as e:
        raise Exception(f"Error fetching historical stock data from Twelve Data: {e}")


async def get_stock_symbols() -> List[Dict[str, Any]]:
    """
    Retrieve a list of supported stock symbols.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "stocks", {"apikey": TWELVE_DATA_API_KEY})
    return response.get("data", [])


async def get_forex_pairs() -> List[Dict[str, Any]]:
    """
    Retrieve a list of supported forex pairs.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "forex_pairs", {"apikey": TWELVE_DATA_API_KEY})
    return response.get("data", [])


async def get_crypto_symbols() -> List[Dict[str, Any]]:
    """
    Retrieve a list of supported cryptocurrency symbols.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "cryptocurrencies", {"apikey": TWELVE_DATA_API_KEY})
    return response.get("data", [])


async def get_technical_indicator(symbol: str, interval: str, indicator: str) -> Dict[str, Any]:
    """
    Retrieve technical indicators for a given symbol.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, indicator, {
        "apikey": TWELVE_DATA_API_KEY,
        "symbol": symbol,
        "interval": interval
    })
    return response


async def get_quote(symbol: str) -> Dict[str, Any]:
    """
    Retrieve the latest quote for a given symbol.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "quote", {
        "apikey": TWELVE_DATA_API_KEY,
        "symbol": symbol
    })
    return response


async def get_exchange_rate(symbol: str) -> Dict[str, Any]:
    """
    Retrieve exchange rates between currencies.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "exchange_rate", {
        "apikey": TWELVE_DATA_API_KEY,
        "symbol": symbol
    })
    return response


async def get_earnings_calendar() -> List[Dict[str, Any]]:
    """
    Retrieve the earnings calendar.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "earnings_calendar", {
        "apikey": TWELVE_DATA_API_KEY
    })
    return response.get("data", [])


async def get_ipo_calendar() -> List[Dict[str, Any]]:
    """
    Retrieve the IPO calendar.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "ipo_calendar", {
        "apikey": TWELVE_DATA_API_KEY
    })
    return response.get("data", [])


async def get_splits(symbol: str) -> List[Dict[str, Any]]:
    """
    Retrieve stock split information.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "splits", {
        "apikey": TWELVE_DATA_API_KEY,
        "symbol": symbol
    })
    return response.get("data", [])


async def get_dividends(symbol: str) -> List[Dict[str, Any]]:
    """
    Retrieve dividend information.
    """
    response = await make_request(TWELVE_DATA_BASE_URL, "dividends", {
        "apikey": TWELVE_DATA_API_KEY,
        "symbol": symbol
    })
    return response.get("data", [])
