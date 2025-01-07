import json
import asyncio
from collections import defaultdict
from postgrest import APIError
from app.core.config import config
from app.models.database import supabase
from app.utils.finnhub import get_stock_quote
from app.models.sqlite_cache import (
    drop_table,
    create_table,
    execute_sql,
    check_table_exists,
    get_from_table
)

from app.core.shared import (
    active_subscribed_symbols,
    active_subscription_lock,
    dormant_subscribed_symbols,
    dormant_subscription_lock
)

user_connection_locks = defaultdict(asyncio.Lock)


async def print_stock_subs_cache(log: str):
    log = '🤖  ' + log
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    res = await get_from_table(ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE)
    print(log, res)


async def create_stock_universe_cache():
    """
    Drop and recreate the STOCK_UNIVERSE_CACHE_TABLE table, then populate it with data from Supabase
    using only S&P 500 stocks and appropriate columns from both tables.
    """
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        # Drop the existing table
        await drop_table(STOCK_UNIVERSE_CACHE_TABLE)

        # Create the new cache table with selected columns
        await create_table(
            STOCK_UNIVERSE_CACHE_TABLE,
            """
            stock_ticker TEXT PRIMARY KEY,
            stock_name TEXT,
            sector TEXT,
            sub_sector TEXT,
            headquarters_location TEXT,
            date_added TEXT,
            year_founded TEXT,
            currency TEXT,
            exchange TEXT,
            asset_type TEXT,
            share_outstanding FLOAT,
            ipo_date TEXT,
            logo_url TEXT,
            website_url TEXT
            """
        )

        # Fetch S&P 500 data from SnP_500_Constituents
        snp_response = supabase.table("SnP_500_Constituents").select(
            "stock_ticker, stock_name, sector, sub_sector, headquarters_location, date_added, year_founded"
        ).execute()
        snp_data = {row['stock_ticker']: row for row in snp_response.data}

        if not snp_data:
            print("⚠️ No S&P 500 data fetched from Supabase while creating stock universe cache.")
            return None

        # Fetch additional data from Stock_Universe
        stock_universe_response = supabase.table("Stock_Universe").select(
            "stock_ticker, currency, exchange_2, asset_type, share_outstanding, ipo_date, logo_url, website_url"
        ).execute()
        stock_universe_data = {row['stock_ticker']: row for row in stock_universe_response.data}

        # Merge data from both tables
        merged_data = []
        for ticker, snp_row in snp_data.items():
            stock_row = stock_universe_data.get(ticker, {})

            merged_data.append((
                ticker,
                snp_row.get("stock_name"),
                snp_row.get("sector"),
                snp_row.get("sub_sector"),
                snp_row.get("headquarters_location"),
                snp_row.get("date_added"),
                snp_row.get("year_founded"),
                stock_row.get("currency"),
                stock_row.get("exchange_2"),
                stock_row.get("asset_type"),
                stock_row.get("share_outstanding"),
                stock_row.get("ipo_date"),
                stock_row.get("logo_url"),
                stock_row.get("website_url")
            ))

        # Insert merged data into the cache table
        query = f"""
            INSERT INTO {STOCK_UNIVERSE_CACHE_TABLE} (
                stock_ticker, stock_name, sector, sub_sector, headquarters_location, 
                date_added, year_founded, currency, exchange, asset_type, 
                share_outstanding, ipo_date, logo_url, website_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        await execute_sql(query, merged_data, bulk=True)

        print(f"✅ Stock universe cache successfully created and populated with S&P 500 stocks")
    except APIError as api_err:
        print(f"❌ Supabase API Error: {api_err}")
        raise api_err

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex


async def create_active_user_stock_subscription_cache():
    """
    Create the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE table.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    try:
        if not await check_table_exists(ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE):
            await create_table(
                ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE,
                """
                stock_ticker TEXT PRIMARY KEY,
                ltp FLOAT,
                user_subscribers TEXT DEFAULT '[]'
                """
            )

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
    
async def add_stock_to_active_stock_subscription_cache(stock_ticker: str, user_id: int):
    """
    Add a stock to the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE table and associate a user_id with it.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

    # Acquire user-specific lock
    async with user_connection_locks[user_id]:
        try:
            # Validate stock ticker
            stock_ticker = stock_ticker.upper()
            query = f"""
                SELECT stock_ticker, stock_name
                FROM {STOCK_UNIVERSE_CACHE_TABLE}
                WHERE stock_ticker = "{stock_ticker}";
            """
            results = await execute_sql(query, ())

            if not results:
                raise ValueError(f"{stock_ticker} Stock does not exist.")

            # Check if stock exists in subscription cache
            stock_check = await execute_sql(
                f"SELECT * FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                (stock_ticker,)
            )

            if not stock_check:
                # Fetch current price
                current_price = await fetch_price_from_dormant_user_stock_subscription_cache(stock_ticker)
                if current_price is None or current_price <= 0:
                    try:
                        company_quote = await get_stock_quote(stock_ticker)
                        current_price = round(company_quote["c"], 2) if company_quote else 0
                        print("Price fecthed by API: ", current_price)
                    except Exception:
                        current_price = 0

                # Insert new row
                await execute_sql(
                    f"INSERT INTO {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} (stock_ticker, ltp, user_subscribers) VALUES (?, ?, json('[]'))",
                    (stock_ticker, current_price)
                )

                await add_update_to_dormant_user_stock_subscription_cache([(stock_ticker, current_price)])

                # Add to active_subscribed_symbols under lock
                async with active_subscription_lock:
                    print("Adding to active_subscribed_symbols from add_stock_to_active_stock_subscription_cache(): ", stock_ticker)
                    active_subscribed_symbols.add(stock_ticker)

            # Add user_id to user_subscribers (if not already present)
            await execute_sql(
                f"""
                UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                SET user_subscribers = (
                    CASE
                        WHEN json_type(user_subscribers) = 'array'
                            AND NOT EXISTS (
                                SELECT 1 FROM json_each(user_subscribers)
                                WHERE value = ?
                            )
                    THEN json_insert(user_subscribers, '$[#]', ?)
                    ELSE user_subscribers
                    END
                )
                WHERE stock_ticker = ?
                """,
                (user_id, user_id, stock_ticker)
            )

        except Exception as ex:
            print(f"❌ Unexpected Error: {ex}")
            raise ex

async def remove_stock_from_active_stock_subscription_cache(stock_ticker: str, user_id: int):
    """
    Remove a user_id from the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE table for a specific stock.
    If no users remain subscribed to the stock, remove the stock entry entirely.
    """
    
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

    # Acquire user-specific lock
    async with user_connection_locks[user_id]:
        try:
            # Validate stock ticker
            stock_ticker = stock_ticker.upper()
            query = f"""
                SELECT stock_ticker, stock_name
                FROM {STOCK_UNIVERSE_CACHE_TABLE}
                WHERE stock_ticker = "{stock_ticker}";
            """
            results = await execute_sql(query, ())

            if not results:
                raise ValueError(f"{stock_ticker} Stock does not exist.")

            # Remove the user_id from user_subscribers array
            await execute_sql(
                f"""
                UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                SET user_subscribers = json_remove(
                    user_subscribers,
                    '$[' || (
                        SELECT key FROM json_each(user_subscribers)
                        WHERE value = ?
                    ) || ']'
                )
                WHERE stock_ticker = ?
                """,
                (user_id, stock_ticker)
            )

            # Check remaining subscribers
            remaining_subscribers = await execute_sql(
                f"""
                SELECT json_array_length(user_subscribers) 
                FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} 
                WHERE stock_ticker = ?
                """,
                (stock_ticker,)
            )

            if remaining_subscribers and remaining_subscribers[0][0] == 0:
                # Delete row if no subscribers remain
                await execute_sql(
                    f"DELETE FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                    (stock_ticker,)
                )

                # Remove from active_subscribed_symbols under lock
                async with active_subscription_lock:
                    if stock_ticker in active_subscribed_symbols:
                        active_subscribed_symbols.remove(stock_ticker)
                        print(f"Removed {stock_ticker} from active_subscribed_symbols as no subscribers remain.")

        except Exception as ex:
            print(f"❌ Unexpected Error: {ex}")
            raise ex



async def add_portfolio_n_watchlist_stocks_for_user_to_active_stock_subscription_cache(user_id: int):
    """
    Add all portfolio and watchlist stocks for a user to the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

    # Acquire lock
    async with user_connection_locks[user_id]:
        try:
            # Fetch user's active holdings
            user_portfolio_stocks = supabase.table("Holdings") \
                .select("stock_ticker") \
                .eq("user_id", user_id) \
                .eq("is_active", True) \
                .execute().data

            # Fetch user's active watchlist
            user_watchlist_stocks = supabase.table("Watchlist") \
                .select("stock_ticker") \
                .eq("user_id", user_id) \
                .eq("is_active", True) \
                .execute().data

            # Combine and get unique tickers using set
            portfolio_tickers = [stock['stock_ticker'] for stock in user_portfolio_stocks]
            watchlist_tickers = [stock['stock_ticker'] for stock in user_watchlist_stocks]

            user_stocks = set(portfolio_tickers) | set(watchlist_tickers)

            print(f"User {user_id} stocks to add: {user_stocks}")

            for stock_ticker in user_stocks:
                stock_ticker = stock_ticker.upper()

                # Validate stock ticker exists
                query = f"""
                    SELECT stock_ticker, stock_name
                    FROM {STOCK_UNIVERSE_CACHE_TABLE}
                    WHERE stock_ticker = "{stock_ticker}";
                """
                results = await execute_sql(query, ())

                if not results:
                    print(f"❌ Stock {stock_ticker} does not exist. Skipping.")
                    continue

                # Check if stock exists in subscription cache
                stock_check = await execute_sql(
                    f"SELECT * FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                    (stock_ticker,)
                )

                if not stock_check:
                    # Fetch current price
                    current_price = await fetch_price_from_dormant_user_stock_subscription_cache(stock_ticker)
                    if current_price is None or current_price <= 0:
                        try:
                            company_quote = await get_stock_quote(stock_ticker)
                            current_price = round(company_quote["c"], 2) if company_quote else 0
                            print(f"Price fetched by API for {stock_ticker}: {current_price}")
                        except Exception:
                            current_price = 0

                    # Insert new row
                    await execute_sql(
                        f"INSERT INTO {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} (stock_ticker, ltp, user_subscribers) VALUES (?, ?, json('[]'))",
                        (stock_ticker, current_price)
                    )

                    await add_update_to_dormant_user_stock_subscription_cache([(stock_ticker, current_price)])

                    # Add to active_subscribed_symbols under lock
                    async with active_subscription_lock:
                        print(f"Adding to active_subscribed_symbols from add_portfolio_n_watchlist_stocks_for_user_to_active_stock_subscription_cache(): {stock_ticker}")
                        active_subscribed_symbols.add(stock_ticker)

                # Add user_id to user_subscribers (if not already present)
                await execute_sql(
                    f"""
                    UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                    SET user_subscribers = (
                        CASE
                            WHEN json_type(user_subscribers) = 'array'
                                AND NOT EXISTS (
                                    SELECT 1 FROM json_each(user_subscribers)
                                    WHERE value = ?
                                )
                        THEN json_insert(user_subscribers, '$[#]', ?)
                        ELSE user_subscribers
                        END
                    )
                    WHERE stock_ticker = ?
                    """,
                    (user_id, user_id, stock_ticker)
                )

        except Exception as ex:
            print(f"❌ Unexpected Error in add_portfolio_n_watchlist_stocks_for_user_to_active_stock_subscription_cache: {ex}")
            raise ex
        
async def remove_all_stocks_for_user_from_active_stock_subscription_cache(user_id: int):
    """
    Remove all stock subscriptions for a user from the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    Unsubscribe from symbols if no other users are subscribed.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

    # Acquire user-specific lock
    async with user_connection_locks[user_id]:
        try:
            # Get all stock tickers associated with user_id
            stock_tickers = await execute_sql(
                f"""
                SELECT stock_ticker FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                WHERE EXISTS (
                    SELECT 1 FROM json_each(user_subscribers)
                    WHERE value = ?
                )
                """,
                (user_id,)
            )

            if not stock_tickers:
                print(f"No stocks found for user {user_id} to remove.")
                return

            print(f"User {user_id} stocks to remove: {[stock[0] for stock in stock_tickers]}")

            for stock in stock_tickers:
                stock_ticker = stock[0]

                # Remove the user_id from user_subscribers array
                await execute_sql(
                    f"""
                    UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                    SET user_subscribers = json_remove(
                        user_subscribers,
                        '$[' || (
                            SELECT key FROM json_each(user_subscribers)
                            WHERE value = ?
                        ) || ']'
                    )
                    WHERE stock_ticker = ?
                    """,
                    (user_id, stock_ticker)
                )

                # Check remaining subscribers
                remaining_subscribers = await execute_sql(
                    f"""
                    SELECT json_array_length(user_subscribers) 
                    FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} 
                    WHERE stock_ticker = ?
                    """,
                    (stock_ticker,)
                )

                if remaining_subscribers and remaining_subscribers[0][0] == 0:
                    # Delete row if no subscribers remain
                    await execute_sql(
                        f"DELETE FROM {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                        (stock_ticker,)
                    )

                    # Remove from active_subscribed_symbols under lock
                    async with active_subscription_lock:
                        if stock_ticker in active_subscribed_symbols:
                            active_subscribed_symbols.remove(stock_ticker)
                            print(f"Removed {stock_ticker} from active_subscribed_symbols as no subscribers remain.")

                    # Unsubscribe from real-time updates will be handled by the rotation task
                    # No need to call unsubscribe_symbol directly

        except Exception as ex:
            print(f"❌ Unexpected Error in remove_all_stocks_for_user_from_active_stock_subscription_cache: {ex}")
            raise ex
        


async def initialize_stock_prices():
    """
    Continuously initialize the price of stocks in the dormant cache by fetching their current prices
    and updating the cache accordingly. This function respects API rate limits by
    introducing a 5-second cooldown between API calls and runs asynchronously to
    avoid blocking other tasks. It loops until no stocks have the initial price
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    INITIAL_LTP_IN_CACHE = config["INITIAL_LTP_IN_CACHE"]

    try:
        while True:
            # Fetch all stock_tickers with ltp equal to INITIAL_LTP_IN_CACHE
            query = f"""
                SELECT stock_ticker 
                FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                WHERE ltp = ?
            """
            stocks_to_initialize = await execute_sql(query, [INITIAL_LTP_IN_CACHE])

            if not stocks_to_initialize:
                print("✅ No stocks require price initialization. Initialization process completed.")
                break  # Exit the loop when there are no more stocks to initialize

            print(f"🔄 Initializing prices for {len(stocks_to_initialize)} stocks.")

            stock_ticker = stocks_to_initialize[0][0]
            try:
                # Fetch current stock price
                company_quote = await get_stock_quote(stock_ticker)
                current_price = round(company_quote["c"], 2) if company_quote and "c" in company_quote else 0

                # Update the dormant cache with the current price
                await add_update_to_dormant_user_stock_subscription_cache([(stock_ticker, current_price)])
                print(f"✅ Updated {stock_ticker} with price {current_price}")

            except Exception as stock_err:
                print(f"❌ Error updating {stock_ticker}: {stock_err}")

            # Respect API rate limits
            await asyncio.sleep(1.75)


        print("✅ Completed initializing all stock prices.")

    except Exception as ex:
        print(f"❌ Unexpected Error during price initialization: {ex}")


               
async def create_and_populate_dormant_user_stock_subscription_cache():
    """
    Create and populate the DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE table.
    Fetch distinct active stock_tickers from Holdings and Watchlist tables
    and insert valid tickers into DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE with ltp set to 0.
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")

    try:
        if not await check_table_exists(DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE):
            await create_table(
                DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE,
                """
                stock_ticker TEXT PRIMARY KEY,
                ltp FLOAT
                """
            )

        # Fetch active tickers from Holdings
        holdings_response = supabase.table("Holdings").select("stock_ticker").eq("is_active", True).execute()
        active_tickers_portfolio = {row['stock_ticker'] for row in holdings_response.data if row.get('stock_ticker')}

        # Fetch active tickers from Watchlist
        watchlist_response = supabase.table("Watchlist").select("stock_ticker").eq("is_active", True).execute()
        active_tickers_watchlist = {row['stock_ticker'] for row in watchlist_response.data if row.get('stock_ticker')}

        # Combine active tickers
        active_tickers = active_tickers_portfolio.union(active_tickers_watchlist)

        # Check if the tickers are valid
        placeholders = ', '.join(['?'] * len(active_tickers))
        universe_query = f"""
            SELECT stock_ticker 
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker IN ({placeholders})
        """
        valid_tickers_result = await execute_sql(universe_query, list(active_tickers))
        valid_tickers = {row[0] for row in valid_tickers_result} if valid_tickers_result else set()
        
        insert_data = [(ticker, config['INITIAL_LTP_IN_CACHE']) for ticker in valid_tickers]

        if insert_data:
            await add_update_to_dormant_user_stock_subscription_cache(insert_data)

        # Initialize stock prices asynchronously without blocking
        asyncio.create_task(initialize_stock_prices())

        print(f"✅ Dormant user stock subscription cache successfully created and populated with {len(insert_data)} stocks")
    except APIError as api_err:
        print(f"❌ Supabase API Error: {api_err}")
        raise api_err

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex

async def add_update_to_dormant_user_stock_subscription_cache(insert_data: list[tuple[str, float]]):
    """
    Add the stock (if dosent exist) or update ltp of stock (if exists) to the DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE 
    It expects a list of tuple [(ticker, ltp), ...]
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")

    try:
        insert_query = f"""
            INSERT INTO {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} (stock_ticker, ltp)
            VALUES (?, ?)
            ON CONFLICT (stock_ticker) DO UPDATE SET ltp = EXCLUDED.ltp;
        """

        await execute_sql(insert_query, insert_data, bulk=True)


        for stock_ticker, _ in insert_data:
            # Add to dormant_subscribed_symbols under lock
            async with dormant_subscription_lock:
                if stock_ticker not in dormant_subscribed_symbols:
                    print("Adding to dormant_subscribed_symbols from add_update_to_dormant_user_stock_subscription_cache(): ", stock_ticker)
                    dormant_subscribed_symbols.add(stock_ticker)

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex

async def remove_stock_from_dormant_user_stock_subscription_cache(tickers_to_remove: list[str]):
    """
    Remove stock from the DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE
    It expects a list of stock tickers [ticker, ...]
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")

    try:
        placeholders = ', '.join(['?'] * len(tickers_to_remove))
        delete_query = f"""
            DELETE FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
            WHERE stock_ticker IN ({placeholders})
        """
        await execute_sql(delete_query, tickers_to_remove)

        for stock_ticker in tickers_to_remove:
            # Remove from dormant_subscribed_symbols under lock
            async with dormant_subscription_lock:
                if stock_ticker in dormant_subscribed_symbols:
                    dormant_subscribed_symbols.remove(stock_ticker)
                    print(f"Removed {stock_ticker} from dormant_subscribed_symbols.")

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
    
async def fetch_price_from_dormant_user_stock_subscription_cache(ticker: str):
    """
    Fetch LTP for a given stock from the DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")

    try:
        query = f"SELECT ltp FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?"
        result = await execute_sql(query, (ticker,))

        return result[0][0] if result else None
    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex


async def update_stock_ltp_in_cache(stock_ticker: str, new_price: float):
    """
    Update the LTP (Last Traded Price) for a given stock in the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In update_stock_ltp_in_cache for {stock_ticker} ; START:')

    try:
        rows_updated = await execute_sql(
            f"UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE} SET ltp = ? WHERE stock_ticker = ?",
            (new_price, stock_ticker)
        )

        if rows_updated == 0:
            print(f"⚠️ No stock found with ticker: {stock_ticker}")
    except Exception as ex:
        print(f"❌ Unexpected Error (update_ltp): {ex}")
        raise ex


async def bulk_update_active_stock_ltp_in_cache(updates: list[tuple[float, str]]):
    """
    Perform a bulk update of LTP (Last Traded Price) for multiple stocks in the ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In bulk_update_active_stock_ltp_in_cache ; START:')

    try:
        query = f"""
        UPDATE {ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
        SET ltp = CASE stock_ticker
        {''.join([f"WHEN ? THEN ? " for _ in updates])}
        END
        WHERE stock_ticker IN ({', '.join(['?' for _ in updates])})
        """

        parameters = [param for update in updates for param in reversed(update)] + [update[1] for update in updates]

        await execute_sql(query, tuple(parameters))

    except Exception as ex:
        print(f"❌ Unexpected Error (bulk_update_ltp): {ex}")
        raise ex
    

async def bulk_update_dormant_stock_ltp_in_cache(updates: list[tuple[float, str]]):
    """
    Perform a bulk update of LTP (Last Traded Price) for multiple stocks in the DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
    INITIAL_LTP_IN_CACHE = config["INITIAL_LTP_IN_CACHE"]

    # await print_stock_subs_cache(f'In bulk_update_dormant_stock_ltp_in_cache ; START:')

    try:
        query = f"""
        UPDATE {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
        SET ltp = CASE stock_ticker
        {''.join([f"WHEN ? THEN ? " for _ in updates])}
        END
        WHERE stock_ticker IN ({', '.join(['?' for _ in updates])})
        """

        parameters = [param for update in updates for param in reversed(update)] + [update[1] for update in updates]

        await execute_sql(query, tuple(parameters))

    except Exception as ex:
        print(f"❌ Unexpected Error (bulk_update_ltp): {ex}")
        raise ex