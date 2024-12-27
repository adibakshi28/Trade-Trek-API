import json
from postgrest import APIError
from app.core.config import config
from app.models.database import supabase
from app.utils.finnhub import get_stock_quote
from app.models.sqlite_cache import (
    drop_table,
    create_table,
    execute_sql,
    check_table_exists
)


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
                ltp FLOAT
                """
            )

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
    

async def add_stock_to_stock_subscription_cache(stock_ticker: str):
    """
    Add a stock to the STOCK_SUBSCRIPTION_CACHE_TABLE table.
    """
    from app.core.websocket import subscribe_symbol  # Avoid circular import

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    await create_stock_subscription_cache()

    try:
        stock_check = await execute_sql(f"SELECT * FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?", (stock_ticker,))
        if not stock_check:
            try:
                company_quote = await get_stock_quote(stock_ticker)
                current_price = company_quote["c"] if company_quote else 0
            except:
                current_price = 0

            await execute_sql(f"INSERT INTO {STOCK_SUBSCRIPTION_CACHE_TABLE} (stock_ticker, ltp) VALUES (?, ?)", (stock_ticker, current_price))

            # !: Subscribe stock_ticker from websocket
            await subscribe_symbol(stock_ticker)

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex


async def remove_stock_from_stock_subscription_cache(stock_ticker: str):
    """
    Remove a stock from the STOCK_SUBSCRIPTION_CACHE_TABLE table.
    """
    from app.core.websocket import unsubscribe_symbol

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    try:
        await execute_sql(f"DELETE FROM {STOCK_SUBSCRIPTION_CACHE_TABLE} WHERE stock_ticker = ?", (stock_ticker,))

        # !: Unsubscribe stock_ticker from websocket
        await unsubscribe_symbol(stock_ticker)

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex


async def update_stock_ltp_in_cache(stock_ticker: str, new_price: float):
    """
    Update the LTP for a given stock in the STOCK_SUBSCRIPTION_CACHE_TABLE.
    """
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")

    try:
        await execute_sql(
            f"UPDATE {STOCK_SUBSCRIPTION_CACHE_TABLE} SET ltp = ? WHERE stock_ticker = ?",
            (new_price, stock_ticker)
        )
    except Exception as ex:
        print(f"❌ Unexpected Error (update_ltp): {ex}")
        raise