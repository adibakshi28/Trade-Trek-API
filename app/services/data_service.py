# app/services/user_service.py

from app.core.config import config
from app.models.sqlite_cache import execute_sql, check_table_exists
from app.core.cache import create_stock_universe_cache


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