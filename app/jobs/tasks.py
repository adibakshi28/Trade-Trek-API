import asyncio
import json
from app.models.database import supabase
from app.utils.finnhub import get_stock_symbols, get_crypto_symbols, get_forex_symbols
from app.core.cache import create_stock_universe_cache, remove_stock_from_stock_subscription_cache, add_stock_to_stock_subscription_cache
from app.core.config import config
from datetime import datetime
from app.models.sqlite_cache import get_from_table, get_cache
from app.services.real_time_service import real_time_service


def another_task():
    print(f"[SCHEDULED JOB] Cron Job dummy {datetime.now()}")

async def print_stock_subscription_table():
    print(f"🔄 [SCHEDULED JOB] Starting Print Stock subscription cache table job ...")
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    result = await get_from_table(STOCK_SUBSCRIPTION_CACHE_TABLE)
    print(result)

    NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY = config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY']
    active_websockets = await get_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY)
    print(f"Active Websockets Connections: {active_websockets}")

    print(f"✅ [SCHEDULED JOB] Completed Print Stock subscription cache table job!")

async def fe_be_websocket_msg_broadcast():
    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    result = await get_from_table(STOCK_SUBSCRIPTION_CACHE_TABLE)
    # Broadcast msg to frontend
    message = []
    for stock in result:
        msg = {
            "stock_ticker": stock[0],
            "ltp": stock[1]
        }
        message.append(msg)
    await real_time_service.broadcast(json.dumps(message))

    # NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY = config['NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY']
    # active_websockets = await get_cache(NUMBER_OF_ACTIVE_WEBSOCKET_CACHE_KEY)
    # print(f"Active Websockets Connections: {active_websockets}")


async def sync_stock_subscription(log = "SCHEDULED JOB"):
    if log == "SCHEDULED JOB":
        print(f"🔄 [SCHEDULED JOB] Starting Stock Subscription sync job ...")

    STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("STOCK_SUBSCRIPTION_CACHE_TABLE")
    subscribed_stocks = await get_from_table(STOCK_SUBSCRIPTION_CACHE_TABLE)
    subscribed_stocks = [stock[0] for stock in subscribed_stocks]

    active_user_id = supabase.table("Sessions").select("user_id").eq("is_active", True).execute()
    active_user_id = [user["user_id"] for user in active_user_id.data]

    active_stocks = set()
    for user_id in active_user_id:
        user_portfolio = supabase.table("Holdings").select("stock_ticker").eq("user_id", user_id).eq("is_active", True).execute()
        user_portfolio = [stock["stock_ticker"] for stock in user_portfolio.data]
        active_stocks.update(user_portfolio)

    stocks_to_unsubscribe = set(subscribed_stocks) - active_stocks
    for stock in stocks_to_unsubscribe:
        await remove_stock_from_stock_subscription_cache(stock)

    stocks_to_subscribe = active_stocks - set(subscribed_stocks)
    for stock in stocks_to_subscribe:
        await add_stock_to_stock_subscription_cache(stock)

    if log == "SCHEDULED JOB":
        print(f"✅ [SCHEDULED JOB] Completed Stock Subscription sync job!")

async def update_stock_universe_cache():
    print(f"🔄 [SCHEDULED JOB] Starting Update Stock Universe sync job ...")
    await create_stock_universe_cache()
    print(f"✅ [SCHEDULED JOB] Stock Universe Cache updated Successfully!")

def sync_stock_universe():
    """
    Fetch stock, crypto, and forex symbols from Finnhub and update the Stock_Universe 
    table efficiently in batches. Only update records if there are changes.
    """
    BATCH_SIZE = 100
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Stock Universe Sync Job...")

        # 1) Fetch data from API (can be done sequentially or concurrently)
        #    Here, we'll just do sequential for clarity, but you could also run them concurrently with asyncio.gather
        stock_data = asyncio.run(get_stock_symbols(config["STOCK_EXCHANGE"]))   # asset_type = STOCK
        crypto_data = asyncio.run(get_crypto_symbols(config["CRYPTO_EXCHANGE"]))  # asset_type = CRYPTO
        forex_data = asyncio.run(get_forex_symbols(config["FOREX_EXCHANGE"]))   # asset_type = FOREX

        # 2) If any call fails or returns None/empty, you may decide how to handle it
        if not stock_data and not crypto_data and not forex_data:
            raise ValueError(f"❌ [SCHEDULED JOB] No data fetched from Finnhub for stock/crypto/forex.")

        # 3) Tag each record with asset_type and the correct exchange
        #    (If the Finnhub API already returns the exchange field, you can override or leave it.)
        #    This depends on your use case. For demonstration, we'll just set them from config.
        for item in stock_data:
            item["asset_type"] = "STOCK"
            item["exchange"]   = config["STOCK_EXCHANGE"]
        for item in crypto_data:
            item["asset_type"] = "CRYPTO"
            item["exchange"]   = config["CRYPTO_EXCHANGE"]
        for item in forex_data:
            item["asset_type"] = "FOREX"
            item["exchange"]   = config["FOREX_EXCHANGE"]

        # Combine all into a single universe_data list
        universe_data = stock_data + crypto_data + forex_data

        # 4) Prepare the final list of tickers we care about
        universe_ticker_list = [x.get("symbol") for x in universe_data if x.get("symbol")]

        # If still no data, bail out
        if not universe_ticker_list:
            raise ValueError("❌ [SCHEDULED JOB] No symbol entries found after combining stock/crypto/forex.")

        # 5) For existing records, fetch them in batches to avoid query size limits
        existing_tickers = set()
        existing_stock_data = {}
        for i in range(0, len(universe_ticker_list), BATCH_SIZE):
            batch = universe_ticker_list[i : i + BATCH_SIZE]
            existing_stocks_response = (
                supabase.table("Stock_Universe")
                .select("stock_ticker, stock_name, currency, exchange, asset_type, is_active")
                .in_("stock_ticker", batch)
                .execute()
            )
            for item in existing_stocks_response.data or []:
                ticker = item["stock_ticker"]
                existing_tickers.add(ticker)
                existing_stock_data[ticker] = item

        # 6) Process each fetched symbol and figure out which ones need to be inserted or updated
        new_records = []
        updated_records = []
        current_time = datetime.utcnow().isoformat()

        for item in universe_data:
            ticker = item.get("symbol")
            if not ticker:
                continue

            # Prepare the record for our DB
            api_data = {
                "stock_ticker": ticker,
                "stock_name":    item.get("description"),
                "currency":      item.get("currency"),
                "exchange":      item.get("exchange"),
                "asset_type":    item.get("asset_type"),
                "is_active":     True,  # or some logic if you want to mark inactive
                "updated_at":    current_time
            }

            if ticker in existing_tickers:
                # Already in DB, check if we need to update any fields
                db_data = existing_stock_data[ticker]
                if (
                    db_data["stock_name"] != api_data["stock_name"]
                    or db_data["currency"] != api_data["currency"]
                    or db_data["exchange"] != api_data["exchange"]
                    or db_data["asset_type"] != api_data["asset_type"]
                    or db_data["is_active"] != api_data["is_active"]
                ):
                    updated_records.append(api_data)
            else:
                # Brand new record
                api_data["created_at"] = current_time
                new_records.append(api_data)

        # 7) Batch update existing records that have changes
        if updated_records:
            for i in range(0, len(updated_records), BATCH_SIZE):
                batch = updated_records[i : i + BATCH_SIZE]
                supabase.table("Stock_Universe") \
                    .upsert(batch, on_conflict=["stock_ticker"]) \
                    .execute()
            print(f"✅ [SCHEDULED JOB] Updated {len(updated_records)} records (STOCK/CRYPTO/FOREX) with changes.")

        # 8) Batch insert new records
        if new_records:
            for i in range(0, len(new_records), BATCH_SIZE):
                batch = new_records[i : i + BATCH_SIZE]
                supabase.table("Stock_Universe") \
                    .insert(batch) \
                    .execute()
            print(f"✅ [SCHEDULED JOB] Added {len(new_records)} new records (STOCK/CRYPTO/FOREX).")

        print(f"✅ [SCHEDULED JOB] Stock/Crypto/Forex Universe Sync Job Completed Successfully!")

    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Stock Universe Sync Job Failed: {e}")