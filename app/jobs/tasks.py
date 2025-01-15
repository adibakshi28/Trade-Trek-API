import asyncio
import json
import random
import pandas as pd
from datetime import datetime, timedelta
from app.models.database import supabase
from app.core.cache import create_stock_universe_cache, remove_stock_from_dormant_user_stock_subscription_cache, add_update_to_dormant_user_stock_subscription_cache, initialize_refresh_dormant_user_stock_subscription_cache
from app.core.config import config
from app.models.sqlite_cache import get_from_table, execute_sql
from app.services.real_time_service import real_time_service
from app.utils.finnhub import get_stock_quote, get_market_status


async def print_dormant():
    try:
        print("..............................................................................................")
        ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
        result = await get_from_table(ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE)
        print(f"🔄 [SCHEDULED JOB] ACTIVE User Stock Subscription Cache: {result}")
        print("..............................................................................................")
        DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
        result = await get_from_table(DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE)
        print(f"🔄 [SCHEDULED JOB] DORMANT User Stock Subscription Cache: {result}")
        print("..............................................................................................")
    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in print_ACTIVE: {e}")
    

def sync_snp500_constituents():
    try:
        print(f"🔄 [SCHEDULED JOB] Starting sync S&P 500 constituents from static csv job ...")
        
        csv_file = "app/static/snp500_constituents.csv"
        df = pd.read_csv(csv_file)
        
        df = df.rename(columns={
            'Symbol': 'stock_ticker',
            'Security': 'stock_name',
            'GICS Sector': 'sector',
            'GICS Sub-Industry': 'sub_sector',
            'Headquarters Location': 'headquarters_location',
            'Date added': 'date_added',
            'Founded': 'year_founded'
        })

        df = df[['stock_ticker', 'stock_name', 'sector', 'sub_sector',
                 'headquarters_location', 'date_added', 'year_founded']]

        df = df.where(pd.notnull(df), None)
        
        existing_data = supabase.table("SnP_500_Constituents").select("stock_ticker").execute()
        existing_tickers = set(row['stock_ticker'] for row in existing_data.data)
        new_tickers = set(df['stock_ticker'].tolist())

        # Find tickers to delete
        tickers_to_delete = existing_tickers - new_tickers

        # Delete removed tickers
        if tickers_to_delete:
            supabase.table("SnP_500_Constituents").delete().in_("stock_ticker", list(tickers_to_delete)).execute()

        # Upsert new/updated rows
        data = df.to_dict(orient='records')
        supabase.table("SnP_500_Constituents").upsert(data).execute()
        
        print(f"✅ [SCHEDULED JOB] Completed sync S&P 500 constituents from static csv job! (deleted: {len(tickers_to_delete)}, upserted: {len(data)})")
    
    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in sync S&P 500 constituents from static csv: {e}")


async def refresh_dormant_cache_at_market_start():
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Refresh Dormant Cache at market start sync job ...")
        DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
        update_query = f"""
            UPDATE {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} 
            SET previous_close = ltp
        """
        await execute_sql(update_query)
        print(f"✅ [SCHEDULED JOB] Refresh Dormant Cache at market start updated Successfully!")
    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in Refresh Dormant Cache at market start: {e}")

async def fe_be_websocket_msg_broadcast():
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    result = await get_from_table(ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE)
    # Broadcast msg to frontend
    message = []
    for stock in result:
        msg = {
            "stock_ticker": stock[0],
            "ltp": stock[1],
            "day_change": stock[1] - stock[2],
        }
        message.append(msg)
    await real_time_service.broadcast(json.dumps(message))

async def update_stock_universe_cache():
    print(f"🔄 [SCHEDULED JOB] Starting Update Stock Universe sync job ...")
    await create_stock_universe_cache()
    print(f"✅ [SCHEDULED JOB] Stock Universe Cache updated Successfully!")


async def sync_dormant_stock_subscription_cache():
    """
    Synchronize the Dormant User Stock Subscription Cache.
    Remove stock tickers from the dormant cache that are no longer active in the Holdings table or Watchlist table.
    Add stock tickers to the dormant cache that are active in the Holdings table or Watchlist table but not in the dormant cache.
    """
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Sync Dormant Stock Subscription Cache job ...")
        
        DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
        STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

        # Fetch active tickers from Holdings
        holdings_response = supabase.table("Holdings").select("stock_ticker").eq("is_active", True).execute()
        active_tickers_portfolio = {row['stock_ticker'] for row in holdings_response.data if row.get('stock_ticker')}

        # Fetch active tickers from Watchlist
        watchlist_response = supabase.table("Watchlist").select("stock_ticker").eq("is_active", True).execute()
        active_tickers_watchlist = {row['stock_ticker'] for row in watchlist_response.data if row.get('stock_ticker')}

        # Combine active tickers
        active_tickers = active_tickers_portfolio.union(active_tickers_watchlist)

        # Fetch current dormant tickers
        dormant_query = f"SELECT stock_ticker FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE};"
        dormant_result = await execute_sql(dormant_query)
        dormant_tickers = {row[0] for row in dormant_result} if dormant_result else set()

        # Determine tickers to remove and add
        tickers_to_remove = dormant_tickers - active_tickers
        tickers_to_add = active_tickers - dormant_tickers

        # Remove inactive tickers
        if tickers_to_remove:
            await remove_stock_from_dormant_user_stock_subscription_cache(list(tickers_to_remove))

        if tickers_to_add:
            # Check if the tickers are valid                  
            placeholders = ', '.join(['?'] * len(tickers_to_add))
            universe_query = f"""
                SELECT stock_ticker 
                FROM {STOCK_UNIVERSE_CACHE_TABLE}
                WHERE stock_ticker IN ({placeholders})
            """
            valid_tickers_result = await execute_sql(universe_query, list(tickers_to_add))
            valid_tickers = {row[0] for row in valid_tickers_result} if valid_tickers_result else set()
            
            # Add new active tickers
            insert_data = [(ticker, config["INITIAL_PRICE_IN_CACHE"]) for ticker in valid_tickers]

            if insert_data:
                await add_update_to_dormant_user_stock_subscription_cache(insert_data)

        # print("[SCHEDULED JOB] Added: ", insert_data)
        # print("[SCHEDULED JOB] Removed: ", tickers_to_remove)

        print(f"✅ [SCHEDULED JOB] Dormant Stock Subscription Cache synchronized successfully! (deleted: {len(tickers_to_remove)}, added: {len(insert_data)})")
    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in Sync Dormant Stock Subscription Cache: {e}")
        raise e

async def calculate_portfolio_value():
    """
    Works only if the market is open.
    Calculate portfolio value, unrealised PNL, and cash for all users.
    Updates Portfolio_History with the calculated values and Stock_History with the latest stock prices. 
    (using dormant stock subscription cache)
    """
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Calculate Portfolio Value job ...")

        DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config["DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE"]
        STOCK_INDEX_TICKER = config["STOCK_INDEX_TICKER"]
        TIMEZONE = config["TIMEZONE"]
        FINNHUB_STOCK_EXCHANGE = config["FINNHUB_STOCK_EXCHANGE"]

        # Check if the market is open
        market_status = await get_market_status(FINNHUB_STOCK_EXCHANGE)

        if not market_status['isOpen']:
            print(f"✅ [SCHEDULED JOB] {FINNHUB_STOCK_EXCHANGE} Market is closed. Skipping Calculate Portfolio Value job.")
            return

        users_response = supabase.table("Users").select(
            "id"
        ).eq("is_active", True).execute()

        active_users = [row['id'] for row in users_response.data]

        # Fetch all stock tickers and their ltp from the dormant cache
        stock_prices_query = f"""
            SELECT stock_ticker, ltp
            FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
        """
        stock_prices_result = await execute_sql(stock_prices_query)
        stock_prices = {row[0]: row[1] for row in stock_prices_result} if stock_prices_result else {}

        # Fetch user holdings and calculate portfolio value and unrealised PNL
        holdings_response = supabase.table("Holdings").select(
            "user_id, stock_ticker, quantity, execution_price, direction"
        ).eq("is_active", True).execute()

        user_portfolio = {}
        user_unrealised_pnl = {}

        # Initialize all users with 0 in case they have no holdings
        for user_id in active_users:
            user_portfolio[user_id] = 0
            user_unrealised_pnl[user_id] = 0

        if holdings_response.data:
            for holding in holdings_response.data:
                user_id = holding['user_id']
                stock_ticker = holding['stock_ticker']
                quantity = holding.get('quantity', 0)
                execution_price = holding.get('execution_price', 0)
                direction = holding.get('direction', 'BUY')

                # If ltp is INITIAL_PRICE_IN_CACHE (ie -ev) or stock_ticker not in dormant cache, set ltp to 0
                ltp = stock_prices.get(stock_ticker, 0) if stock_prices.get(stock_ticker, 0) > 0 else 0

                if quantity == 0 or ltp == 0:
                    continue

                # Calculate holding value
                holding_value = ltp * quantity
                user_portfolio[user_id] += holding_value

                # Calculate Unrealised PNL
                if direction == 'BUY':
                    unrealised_pnl = (ltp - execution_price) * quantity
                elif direction == 'SELL':
                    unrealised_pnl = (execution_price - ltp) * quantity
                else:
                    unrealised_pnl = 0

                user_unrealised_pnl[user_id] += unrealised_pnl

        # Fetch user cash balances from Cash table
        cash_response = supabase.table("Cash").select(
            "user_id, cash"
        ).eq("is_active", True).execute()

        user_cash = {row['user_id']: row['cash'] for row in cash_response.data} if cash_response.data else {}

        for user_id in active_users:
            if user_id not in user_cash:
                user_cash[user_id] = 0

        # Insert into Portfolio_History table with calculated values
        portfolio_data = [
            {
                "user_id": user_id,
                "holding_value": user_portfolio[user_id],
                "unrealised_pnl": user_unrealised_pnl[user_id],
                "cash": user_cash[user_id],
                "timestamp": datetime.now(TIMEZONE).isoformat()
            }
            for user_id in active_users
        ]

        if portfolio_data:
            supabase.table("Portfolio_History").insert(portfolio_data).execute()


        # Get the price of STOCK_INDEX_TICKER
        index_price = await get_stock_quote(STOCK_INDEX_TICKER)
        index_price = index_price['c'] if index_price else 0
        stock_prices[STOCK_INDEX_TICKER] = index_price

        # Insert into Stock_History with the latest stock prices
        stock_history_data = [
            {
                "stock_ticker": ticker,
                "price": price,
                "timestamp": datetime.now(TIMEZONE).isoformat()
            }
            for ticker, price in stock_prices.items()
        ]

        if stock_history_data:
            supabase.table("Stock_History").insert(stock_history_data).execute()

        print(f"✅ [SCHEDULED JOB] Calculate Portfolio Value job Completed Successfully! Inserted {len(portfolio_data)} portfolio snapshots and {len(stock_history_data)} stock prices.")

    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in Calculate Portfolio Value job: {e}")
        raise e


async def delete_stock_history():
    """
    Delete all stock LTP records older than 30 days from the Stock_History.
    """
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Delete Stock History older than 30 days job ...")
        
        TIMEZONE = config["TIMEZONE"]
        thirty_days_ago = (datetime.now(TIMEZONE) - timedelta(days=30)).isoformat()
        
        response_stock = supabase.table("Stock_History") \
            .delete() \
            .filter("timestamp", "lt", thirty_days_ago) \
            .execute()
                
        print(f"✅ [SCHEDULED JOB] Delete Stock History older than 30 days job Completed Successfully! Deleted {len(response_stock.data)} records.")
    
    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Error in Delete Stock History job: {e}")
        raise e