from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.jobs.tasks import update_stock_universe_cache, fe_be_websocket_msg_broadcast, sync_snp500_constituents, sync_dormant_stock_subscription_cache, calculate_portfolio_value, delete_stock_history, print_dormant
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
    scheduler.add_job(sync_snp500_constituents, CronTrigger(hour=2, minute=0, second=0, timezone=config["TIMEZONE"]), id="sync_snp500_constituents", replace_existing=True)

    # For running async functions
    scheduler.add_job(run_async_job, IntervalTrigger(hours=24), id="update_stock_universe_cache", replace_existing=True, args=[update_stock_universe_cache], max_instances=3)
    scheduler.add_job(run_async_job, IntervalTrigger(seconds=config['FE_BE_WEBSOCKET_MSG_DELAY']), id="fe_be_websocket_msg_broadcast", replace_existing=True, args=[fe_be_websocket_msg_broadcast], max_instances=3)
    scheduler.add_job(run_async_job, IntervalTrigger(minutes=13), id="sync_dormant_stock_subscription_cache", replace_existing=True, args=[sync_dormant_stock_subscription_cache], max_instances=3)
    scheduler.add_job(run_async_job, IntervalTrigger(minutes=config["PORTFOLIO_SNAPSHOT_DELAY"]), id="calculate_portfolio_value", replace_existing=True, args=[calculate_portfolio_value], max_instances=3)
    scheduler.add_job(run_async_job, IntervalTrigger(hours=24), id="delete_stock_history", replace_existing=True, args=[delete_stock_history], max_instances=3)

    # scheduler.add_job(run_async_job, IntervalTrigger(seconds=30), id="print_dormant", replace_existing=True, args=[print_dormant])


    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())
