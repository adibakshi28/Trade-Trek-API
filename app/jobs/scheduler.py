from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.jobs.tasks import update_stock_universe_cache, sync_stock_universe, another_task, print_stock_subscription_table, fe_be_websocket_msg_broadcast, populate_stock_universe
from app.core.config import config
import asyncio
import atexit

number = 0

def run_async_job(async_func):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_func())
    finally:
        loop.close()


def start_scheduler():
    scheduler = BackgroundScheduler()

    scheduler.add_job(run_async_job, IntervalTrigger(seconds=1.15), id="populate_stock_universe", replace_existing=True, args=[populate_stock_universe])

    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())
