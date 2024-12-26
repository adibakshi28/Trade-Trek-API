# app/services/user_service.py
from fastapi import HTTPException
import json
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from app.core.config import config
from app.models.database import supabase
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
        ticker = ticker.upper()
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
    

async def stock_transaction_service(user_id: int, ticker: str, direction: str, quantity: float):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    ALLOW_FRACTIONAL_SHARES = config.get("ALLOW_FRACTIONAL_SHARES")
    FRACTIONAL_SHARES_MIN_TRADE = config.get("FRACTIONAL_SHARES_MIN_TRADE")
    ALLOW_SHORT_SELLING = config.get("ALLOW_SHORT_SELLING")
    MAX_ASSETS_IN_PORTFOLIO = config.get("MAX_ASSETS_IN_PORTFOLIO")
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

        direction = direction.upper()
        if direction not in ["BUY", "SELL"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid direction. Must be 'BUY' or 'SELL'."
            )

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0."
            )

        if not ALLOW_FRACTIONAL_SHARES and quantity % 1 != 0:
            raise HTTPException(
                status_code=400,
                detail="Fractional shares are not allowed."
            )

        if ALLOW_FRACTIONAL_SHARES and quantity < FRACTIONAL_SHARES_MIN_TRADE:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum trade quantity is {FRACTIONAL_SHARES_MIN_TRADE}."
            )
        
        # !: Fetch users current portfolio
        portfolio = supabase.table("Holdings").select("stock_ticker", "direction", "quantity", "execution_price").eq("user_id", user_id).eq("is_active", True).execute()
        portfolio = portfolio.data if portfolio.data else []

        # !: if Short selling not allowed then check if stock is owned
        portfolioStocks = [stock['stock_ticker'] for stock in portfolio]

        if not ALLOW_SHORT_SELLING and direction == "SELL" and ticker not in portfolioStocks:
            raise HTTPException(
                status_code=400,
                detail="You do not own this stock. Short Selling is not allowed."
            )
        
        # !: if direction is sell and stock is owned then Check for sufficient quantity 
        if direction == "SELL" and ticker in portfolioStocks:
            stock = [stock for stock in portfolio if stock['stock_ticker'] == ticker][0]
            if stock['quantity'] < quantity:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient quantity to sell."
                )

        # !: Check for maximum assets in portfolio (by fetchaing the user's portfolio)
        if len(portfolio) >= MAX_ASSETS_IN_PORTFOLIO and ticker not in portfolioStocks:
            raise HTTPException(
                status_code=400,
                detail="You have reached the maximum number of assets in your portfolio."
            )

        # !: Fetch stock price
        import random
        price = int(random.uniform(1, 1000))

        # !: Check for sufficient cash balance (by calculating transaction value)
        cash = supabase.table("Cash").select("cash").eq("user_id", user_id).eq("is_active", True).execute()
        cash = cash.data[0]['cash'] if cash.data else 0
        transaction_value = price * quantity
        
        if direction == "BUY" and ticker not in portfolioStocks and cash < transaction_value:
            raise HTTPException(
                status_code=400,
                detail="Insufficient funds to buy the stock."
            )
        if direction == "BUY" and ticker in portfolioStocks:
            stock = [stock for stock in portfolio if stock['stock_ticker'] == ticker][0]
            if stock['direction'] == "BUY" and cash < transaction_value:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient funds to buy more of the stock."
                )
        
        # !: if Short selling is allowed and direction is sell then Check for sufficient cash balance
        if ALLOW_SHORT_SELLING and direction == "SELL" and ticker not in portfolioStocks:
            if cash < transaction_value:
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient funds to short sell."
                )

        # !: Update user's portfolio
    
        if ticker in portfolioStocks and direction == "BUY":
            stock = [stock for stock in portfolio if stock['stock_ticker'] == ticker][0]
            if stock['direction'] == "BUY":
                portfolioUpdate = {
                    "quantity": stock['quantity'] + quantity,
                    "execution_price": (stock['execution_price']*stock['quantity'] + price*quantity) / (stock['quantity'] + quantity)
                }
                portfolioUpdateResponse = supabase.table("Holdings").update(portfolioUpdate).eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True).execute()
                cashUpdate = {
                    "cash": cash - transaction_value
                }
                cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                transaction = {
                    "user_id": user_id,
                    "stock_ticker": ticker,
                    "direction": direction,
                    "quantity": quantity,
                    "execution_price": price,
                    "is_active": True
                }
                transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()
            else:
                # !: Stock buy back from short selling
                if stock['quantity'] < quantity:
                    raise HTTPException(
                        status_code=400,
                        detail="Insufficient quantity to buy back."
                    )
                elif stock['quantity'] == quantity:
                    portfolioUpdateResponse = supabase.table("Holdings").update({"quantity": 0, "is_active": False}).eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True).execute()
                    cashUpdate = {
                        "cash": (cash + (stock['execution_price']*quantity)) + (stock['execution_price']*quantity) - transaction_value 
                    }
                    cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                    transaction = {
                        "user_id": user_id,
                        "stock_ticker": ticker,
                        "direction": direction,
                        "quantity": quantity,
                        "execution_price": price,
                        "is_active": True
                    }
                    transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="You have to buy back the whole quantity. Partial buy back is not allowed."
                    )

        if ticker not in portfolioStocks and direction == "BUY":
            portfolioInsert = {
                "user_id": user_id,
                "stock_ticker": ticker,
                "direction": direction,
                "quantity": quantity,
                "execution_price": price,
                "is_active": True
            }
            portfolioInsertResponse = supabase.table("Holdings").insert(portfolioInsert).execute()
            cashUpdate = {
                "cash": cash - transaction_value
            }
            cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
            transaction = {
                "user_id": user_id,
                "stock_ticker": ticker,
                "direction": direction,
                "quantity": quantity,
                "execution_price": price,
                "is_active": True
            }
            transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()

        if ticker in portfolioStocks and direction == "SELL":
            stock = [stock for stock in portfolio if stock['stock_ticker'] == ticker][0]
            if stock['direction'] == "BUY":
                if stock['quantity'] < quantity:
                    raise HTTPException(
                        status_code=400,
                        detail="Insufficient quantity to sell."
                    )
                elif stock['quantity'] == quantity:
                    portfolioUpdateResponse = supabase.table("Holdings").update({"quantity": 0, "is_active": False}).eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True).execute()
                    cashUpdate = {
                        "cash": cash + transaction_value
                    }
                    cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                    transaction = {
                        "user_id": user_id,
                        "stock_ticker": ticker,
                        "direction": direction,
                        "quantity": quantity,
                        "execution_price": price,
                        "is_active": True
                    }
                    transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()
                else:
                    portfolioUpdate = {
                        "quantity": stock['quantity'] - quantity,
                    }
                    portfolioUpdateResponse = supabase.table("Holdings").update(portfolioUpdate).eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True).execute()
                    cashUpdate = {
                        "cash": cash + transaction_value
                    }
                    cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                    transaction = {
                        "user_id": user_id,
                        "stock_ticker": ticker,
                        "direction": direction,
                        "quantity": quantity,
                        "execution_price": price,
                        "is_active": True
                    }
                    transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()
            else:
                portfolioUpdate = {
                    "quantity": stock['quantity'] + quantity,
                    "execution_price": (stock['execution_price']*stock['quantity'] + price*quantity) / (stock['quantity'] + quantity)
                }
                portfolioUpdateResponse = supabase.table("Holdings").update(portfolioUpdate).eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True).execute()
                cashUpdate = {
                    "cash": cash - transaction_value
                }
                cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                transaction = {
                    "user_id": user_id,
                    "stock_ticker": ticker,
                    "direction": direction,
                    "quantity": quantity,
                    "execution_price": price,
                    "is_active": True
                }
                transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()

        if ticker not in portfolioStocks and direction == "SELL":
            if not ALLOW_SHORT_SELLING:
                raise HTTPException(
                    status_code=400,
                    detail="You do not own this stock. Short Selling is not allowed."
                )
            else:
                portfolioInsert = {
                    "user_id": user_id,
                    "stock_ticker": ticker,
                    "direction": direction,
                    "quantity": quantity,
                    "execution_price": price,
                    "is_active": True
                }
                portfolioInsertResponse = supabase.table("Holdings").insert(portfolioInsert).execute()
                cashUpdate = {
                    "cash": cash - transaction_value
                }
                cashUpdateResponse = supabase.table("Cash").update(cashUpdate).eq("user_id", user_id).eq("is_active", True).execute()
                transaction = {
                    "user_id": user_id,
                    "stock_ticker": ticker,
                    "direction": direction,
                    "quantity": quantity,
                    "execution_price": price,
                    "is_active": True
                }
                transactionInsertResponse = supabase.table("Transactions").insert(transaction).execute()

        
        # !: Return transaction details, updated portfolio, and cash balance
        currentCash = supabase.table("Cash").select("cash").eq("user_id", user_id).eq("is_active", True).execute()
        currentPortfolio = supabase.table("Holdings").select("stock_ticker", "direction", "quantity", "execution_price").eq("user_id", user_id).eq("is_active", True).execute()

        return {
            "success": True,
            "stockTicker": ticker,
            "executionPrice": price,
            "quantity": quantity,
            "direction": direction,
            "cashBalance": currentCash.data[0]['cash'],
            "currentPortfolio": currentPortfolio.data
        }


    except HTTPException as http_ex:
        return {
            "success": False,
            "message": http_ex.detail
        }
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )