import asyncio
from app.models.database import supabase
from app.utils.finnhub import get_stock_symbols
from app.core.cache import create_stock_universe_cache
from app.core.config import config
from datetime import datetime

def another_task():
    print(f"[SCHEDULED JOB] Cron Job dummy {datetime.now()}")

async def update_stock_universe_cache():
    print(f"🔄 [SCHEDULED JOB] Starting Update Stock Universe sync job ...")
    await create_stock_universe_cache()
    print(f"✅ [SCHEDULED JOB] Stock Universe Cache updated Successfully!")

async def sync_stock_universe():
    """
    Fetch stock symbols from Finnhub and update the Stock_Universe table efficiently in batches.
    Only update records if there are changes.
    """
    BATCH_SIZE = 100
    try:
        print(f"🔄 [SCHEDULED JOB] Starting Stock Universe Sync Job...")

        # Fetch data from API
        stock_data = asyncio.run(get_stock_symbols(config["EXCHANGE"]))

        if not stock_data:
            raise ValueError(f"❌ [SCHEDULED JOB] No stock data fetched from Finnhub.")

        stock_ticker_list = [stock.get("symbol") for stock in stock_data if stock.get("symbol")]

        existing_tickers = set()
        existing_stock_data = {}

        # Batch fetch existing stock records to avoid query size limits
        for i in range(0, len(stock_ticker_list), BATCH_SIZE):
            batch = stock_ticker_list[i:i + BATCH_SIZE]
            existing_stocks_response = (
                supabase.table("Stock_Universe")
                .select("stock_ticker", "stock_name", "currency", "exchange", "is_active")
                .in_("stock_ticker", batch)
                .execute()
            )

            for item in existing_stocks_response.data or []:
                existing_tickers.add(item["stock_ticker"])
                existing_stock_data[item["stock_ticker"]] = item

        new_records = []
        updated_records = []
        current_time = datetime.utcnow().isoformat()

        # Compare API data with DB data
        for stock in stock_data:
            ticker = stock.get("symbol")
            if not ticker:
                continue

            api_data = {
                "stock_ticker": ticker,
                "stock_name": stock.get("description"),
                "currency": stock.get("currency"),
                "exchange": config["EXCHANGE"],
                "is_active": True,
                "updated_at": current_time
            }

            if ticker in existing_tickers:
                db_data = existing_stock_data[ticker]
                
                # Compare fields to detect changes
                if (
                    db_data["stock_name"] != api_data["stock_name"] or
                    db_data["currency"] != api_data["currency"] or
                    db_data["exchange"] != api_data["exchange"] or
                    db_data["is_active"] != api_data["is_active"]
                ):
                    updated_records.append(api_data)
            else:
                api_data["created_at"] = current_time
                new_records.append(api_data)

        # Batch update existing records with changes
        if updated_records:
            for i in range(0, len(updated_records), BATCH_SIZE):
                batch = updated_records[i:i + BATCH_SIZE]
                supabase.table("Stock_Universe") \
                    .upsert(batch, on_conflict=["stock_ticker"]) \
                    .execute()
            print(f"✅ [SCHEDULED JOB] Updated {len(updated_records)} stock records with changes.")

        # Batch insert new records
        if new_records:
            for i in range(0, len(new_records), BATCH_SIZE):
                batch = new_records[i:i + BATCH_SIZE]
                supabase.table("Stock_Universe") \
                    .insert(batch) \
                    .execute()
            print(f"✅ [SCHEDULED JOB] Added {len(new_records)} new stock records.")

        print(f"✅ [SCHEDULED JOB] Stock Universe Sync Job Completed Successfully!")

    except Exception as e:
        print(f"❌ [SCHEDULED JOB] Stock Universe Sync Job Failed: {e}")