# app/services/user_service.py
from fastapi import HTTPException
import json
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from app.core.config import config
from app.models.sqlite_cache import execute_sql, check_table_exists
from app.core.cache import create_stock_universe_cache
from app.utils.finnhub import get_company_profile, get_company_news, get_basic_financials, get_stock_quote, get_historical_stock_data


async def search_stock_service(ticker: str, top: int):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        if not await check_table_exists(STOCK_UNIVERSE_CACHE_TABLE):
            await create_stock_universe_cache()
        
        query = f"""
            SELECT stock_ticker, stock_name
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker LIKE ?
            LIMIT {top};
        """
        params = (f"%{ticker}%",)
        results = await execute_sql(query, params)

        stock_results = [
            {"stock_ticker": row[0], "stock_name": row[1]} for row in results
        ]
                
        return stock_results

    except Exception as ex:
        raise ex
    
# TODO: Search for other historical price source other than yfinance
async def stock_historical_service(ticker: str):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        if not await check_table_exists(STOCK_UNIVERSE_CACHE_TABLE):
            await create_stock_universe_cache()

        ticker = ticker.upper()
        query = f"""
            SELECT stock_ticker, stock_name
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker = "{ticker}";
        """
        params = ()
        results = await execute_sql(query, params)

        if not results:
            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )

        # TODO: Correctly parse the historical price data
        current_date = datetime.now().strftime('%Y-%m-%d')
        date_1_years_ago = (datetime.now() - relativedelta(years=1)).strftime('%Y-%m-%d')
        company_historical_price = yf.download(ticker, start=date_1_years_ago, end=current_date)
        company_historical_price = company_historical_price.to_json(orient='records', indent=4)
        company_historical_price = json.loads(company_historical_price)

        stock_data = {
            "historical_price": company_historical_price
        }

        return stock_data

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )
    

async def stock_info_service(ticker: str):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        if not await check_table_exists(STOCK_UNIVERSE_CACHE_TABLE):
            await create_stock_universe_cache()

        ticker = ticker.upper()
        query = f"""
            SELECT stock_ticker, stock_name
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker = "{ticker}";
        """
        params = ()
        results = await execute_sql(query, params)

        if not results:
            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )
        
        company_profile = await get_company_profile(ticker)

        current_date = datetime.now().strftime('%Y-%m-%d')
        date_15_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        company_news = await get_company_news(ticker, date_15_days_ago, current_date)

        company_financials = await get_basic_financials(ticker, "all")

        company_quote = await get_stock_quote(ticker)

        stock_data = {
            "quote": company_quote,
            "profile": company_profile,
            "financials": company_financials.get('metric', {}),
            "news": company_news,
        }

        return stock_data

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )