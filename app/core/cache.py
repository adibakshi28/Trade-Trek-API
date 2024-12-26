import json
from postgrest import APIError
from app.core.config import config
from app.models.database import supabase
from app.models.sqlite_cache import (
    drop_table,
    create_table,
    execute_sql,
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
            exchange TEXT
            """
        )

        response = supabase.table("Stock_Universe").select("stock_ticker, stock_name, currency, exchange").execute()
        stock_universe = response.data

        if not stock_universe:
            print("⚠️ No stock data fetched from Supabase while creating stock universe cache.")
            return None

        data = [
            (
                stock.get("stock_ticker"),
                stock.get("stock_name"),
                stock.get("currency"),
                stock.get("exchange")
            )
            for stock in stock_universe
        ]

        query = f"""
            INSERT INTO {STOCK_UNIVERSE_CACHE_TABLE} (stock_ticker, stock_name, currency, exchange)
            VALUES (?, ?, ?, ?)
        """
        
        await execute_sql(query, data, bulk=True)

    except APIError as api_err:
        print(f"❌ Supabase API Error: {api_err}")
        raise api_err

    except Exception as ex:
        print(f"❌ Unexpected Error: {ex}")
        raise ex
