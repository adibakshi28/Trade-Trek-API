from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.jobs.tasks import update_stock_universe_cache, sync_stock_universe, another_task, print_stock_subscription_table, sync_stock_subscription
from app.core.config import config
import asyncio
import atexit

# Note: APScheduler operates in a separate thread from the FastAPI event loop

def run_async_job(async_func):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_func())
    finally:
        loop.close()


def start_scheduler():
    scheduler = BackgroundScheduler()

    # Add periodic jobs (non async functions)
    scheduler.add_job(another_task, IntervalTrigger(minutes=30), id="another_task", replace_existing=True)
    scheduler.add_job(sync_stock_universe, CronTrigger(hour=1, minute=0, timezone=config["TIMEZONE"]), id="sync_stock_universe", replace_existing=True)
    
    # For running async functions
    scheduler.add_job(run_async_job, IntervalTrigger(hours=24), id="update_stock_universe_cache", replace_existing=True, args=[update_stock_universe_cache])
    scheduler.add_job(run_async_job, IntervalTrigger(minutes=1), id="sync_stock_subscription", replace_existing=True, args=[sync_stock_subscription])

    # scheduler.add_job(run_async_job, IntervalTrigger(seconds=15), id="print_stock_subscription_table_task", replace_existing=True, args=[print_stock_subscription_table])

    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())
