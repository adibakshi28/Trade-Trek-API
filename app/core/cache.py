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


user_connection_locks = defaultdict(asyncio.Lock)


async def print_stock_subs_cache(log: str):
    log = '🤖  ' + log
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    res = await get_from_table(STOCK_SUBSCRIPTION_CACHE_TABLE)
    print(log, res)


async def create_stock_universe_cache():
    """
    Drop and recreate the STOCK_UNIVERSE_CACHE_TABLE table, then populate it with data from Supabase.
    """
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        await drop_table(STOCK_UNIVERSE_CACHE_TABLE)

        await create_table(
            STOCK_UNIVERSE_CACHE_TABLE,
            """
            stock_ticker TEXT PRIMARY KEY,
            stock_name TEXT,
            currency TEXT,
            exchange TEXT,
            asset_type TEXT
            """
        )

        response = supabase.table("Stock_Universe").select("stock_ticker, stock_name, currency, exchange, asset_type").execute()
        stock_universe = response.data

        if not stock_universe:
            print("⚠️ No stock data fetched from Supabase while creating stock universe cache.")
            return None

        data = [
            (
                stock.get("stock_ticker"),
                stock.get("stock_name"),
                stock.get("currency"),
                stock.get("exchange"),
                stock.get("asset_type")
            )
            for stock in stock_universe
        ]

        query = f"""
            INSERT INTO {STOCK_UNIVERSE_CACHE_TABLE} (stock_ticker, stock_name, currency, exchange, asset_type)
            VALUES (?, ?, ?, ?, ?)
        """
        
        await execute_sql(query, data, bulk=True)

    except APIError as api_err:
        print(f"❌ Supabase API Error: {api_err}")
        raise api_err

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex


async def create_stock_subscription_cache():
    """
    Create the STOCK_SUBSCRIPTION_CACHE_TABLE table.
    """
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    try:
        if not await check_table_exists(STOCK_SUBSCRIPTION_CACHE_TABLE):
            await create_table(
                STOCK_SUBSCRIPTION_CACHE_TABLE,
                """
                stock_ticker TEXT PRIMARY KEY,
                ltp FLOAT,
                user_subscribers TEXT DEFAULT '[]'
                """
            )

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
    

async def add_stock_to_stock_subscription_cache(stock_ticker: str, user_id: int):
    """
    Add a stock to the STOCK_SUBSCRIPTION_CACHE_TABLE table and associate a user_id with it.
    """
    from app.core.websocket import subscribe_symbol  # Avoid circular import

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In add_stock_to_stock_subscription_cache for {stock_ticker} -> {user_id}; START:')

    await create_stock_subscription_cache()

    try:
        # Check if the stock exists in the table
        stock_check = await execute_sql(
            f"SELECT * FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?", 
            (stock_ticker,)
        )

        if not stock_check:
            try:
                company_quote = await get_stock_quote(stock_ticker)
                current_price = round(company_quote["c"], 2) if company_quote else 0
            except Exception:
                current_price = 0

            # Insert stock with an initial empty user_subscribers array
            await execute_sql(
                f"""
                INSERT INTO {STOCK_SUBSCRIPTION_CACHE_TABLE} 
                (stock_ticker, ltp, user_subscribers) 
                VALUES (?, ?, json('[]'))
                """,
                (stock_ticker, current_price)
            )

            # Subscribe to stock updates
            await subscribe_symbol(stock_ticker)

        # Add user_id to user_subscribers array (if not already present)
        await execute_sql(
            f"""
            UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE}
            SET user_subscribers = (
                CASE 
                    WHEN json_type(user_subscribers) = 'array' AND NOT EXISTS (
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


async def remove_stock_from_stock_subscription_cache(stock_ticker: str, user_id: int):
    """
    Remove a user_id from the STOCK_SUBSCRIPTION_CACHE_TABLE table for a specific stock.
    If no users remain subscribed to the stock, remove the stock entry entirely.
    """
    from app.core.websocket import unsubscribe_symbol

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In remove_stock_from_stock_subscription_cache for {stock_ticker} -> {user_id}; START:')

    try:
        # Remove the user_id from user_subscribers array
        await execute_sql(
            f"""
            UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE}
            SET user_subscribers = json_remove(user_subscribers, (
                SELECT key FROM json_each(user_subscribers)
                WHERE value = ?
            ))
            WHERE stock_ticker = ?
            """,
            (user_id, stock_ticker)
        )

        # Check if there are any remaining subscribers
        remaining_subscribers = await execute_sql(
            f"SELECT json_array_length(user_subscribers) FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
            (stock_ticker,)
        )

        if remaining_subscribers and remaining_subscribers[0][0] == 0:
            # Remove the stock if no subscribers remain
            await execute_sql(
                f"DELETE FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                (stock_ticker,)
            )

            # Unsubscribe stock_ticker from websocket
            await unsubscribe_symbol(stock_ticker)

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
    

async def add_all_stocks_for_user_to_stock_subscription_cache(user_id: int):
    from app.core.websocket import subscribe_symbol

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # Acquire lock
    async with user_connection_locks[user_id]:
        # await print_stock_subs_cache(f"In add_all_stocks_for_user_to_stock_subscription_cache for {user_id} ; START:")
        try:
            # Example: fetch user's active holdings from Supabase
            user_portfolio_stocks = supabase.table("Holdings") \
                .select("stock_ticker") \
                .eq("user_id", user_id) \
                .eq("is_active", True) \
                .execute().data

            for stock in user_portfolio_stocks:
                stock_ticker = stock['stock_ticker']

                # Check if stock already exists
                stock_check = await execute_sql(
                    f"SELECT * FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                    (stock_ticker,)
                )

                if not stock_check:
                    # Insert new row
                    try:
                        company_quote = await get_stock_quote(stock_ticker)
                        current_price = round(company_quote["c"], 2) if company_quote else 0
                    except Exception:
                        current_price = 0

                    await execute_sql(
                        f"INSERT INTO {STOCK_SUBSCRIPTION_CACHE_TABLE} (stock_ticker, ltp, user_subscribers) VALUES (?, ?, json('[]'))",
                        (stock_ticker, current_price)
                    )

                    # Subscribe to real-time data
                    await subscribe_symbol(stock_ticker)

                # Add user_id to user_subscribers (if not already present)
                await execute_sql(
                    f"""
                    UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE}
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


async def remove_all_stocks_for_user_from_stock_subscription_cache(user_id: int):
    from app.core.websocket import unsubscribe_symbol

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # Acquire lock
    async with user_connection_locks[user_id]:
        # await print_stock_subs_cache(f"In remove_all_stocks_for_user_from_stock_subscription_cache for {user_id} ; START:")
        try:
            # Get all stock tickers associated with user_id
            stock_tickers = await execute_sql(
                f"""
                SELECT stock_ticker FROM {STOCK_SUBSCRIPTION_CACHE_TABLE}
                WHERE EXISTS (
                    SELECT 1 FROM json_each(user_subscribers)
                    WHERE value = ?
                )
                """,
                (user_id,)
            )

            for stock in stock_tickers:
                stock_ticker = stock[0]

                # Remove the user_id from user_subscribers
                # IMPORTANT: build a JSON path with '$[...]'
                await execute_sql(
                    f"""
                    UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE}
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
                    FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} 
                    WHERE stock_ticker = ?
                    """,
                    (stock_ticker,)
                )

                if remaining_subscribers and remaining_subscribers[0][0] == 0:
                    # Delete row if no subscribers remain
                    await execute_sql(
                        f"DELETE FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?",
                        (stock_ticker,)
                    )

                    # Unsubscribe from real-time updates
                    await unsubscribe_symbol(stock_ticker)

        except Exception as ex:
            print(f"❌ Unexpected Error: {ex}")
            raise ex


async def update_stock_ltp_in_cache(stock_ticker: str, new_price: float):
    """
    Update the LTP (Last Traded Price) for a given stock in the STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In update_stock_ltp_in_cache for {stock_ticker} ; START:')

    try:
        rows_updated = await execute_sql(
            f"UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE} SET ltp = ? WHERE stock_ticker = ?",
            (new_price, stock_ticker)
        )

        if rows_updated == 0:
            print(f"⚠️ No stock found with ticker: {stock_ticker}")
    except Exception as ex:
        print(f"❌ Unexpected Error (update_ltp): {ex}")
        raise ex


async def bulk_update_stock_ltp_in_cache(updates: list[tuple[float, str]]):
    """
    Perform a bulk update of LTP (Last Traded Price) for multiple stocks in the STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    # await print_stock_subs_cache(f'In bulk_update_stock_ltp_in_cache ; START:')

    try:
        query = f"""
        UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE}
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