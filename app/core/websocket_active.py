# app/core/websocket_active.py

import asyncio
import json
import time
from typing import Set, List

import websockets
from fastapi import APIRouter
from itertools import cycle

from app.core.config import config, FINNHUB_API_KEY
from app.core.cache import bulk_update_active_stock_ltp_in_cache
from app.core.shared import (
    active_subscribed_symbols,
    active_current_batch,
    active_batches,
    active_subscription_lock
)

router = APIRouter()

FINNHUB_WEBSOCKET_URL = config['FINNHUB_WEBSOCKET_URL']
FINNHUB_WS_URL = f"{FINNHUB_WEBSOCKET_URL}?token={FINNHUB_API_KEY}"

FINNHUB_WEBSOCKET_MSG_DELAY = config['FINNHUB_WEBSOCKET_MSG_DELAY']
ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY = config['ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY'] 
ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE = config['ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE']

finnhub_ws = None

last_update_time = 0
rotation_task = None

async def connect_to_finnhub_active():
    global finnhub_ws, active_batches, rotation_task
    while True:
        try:
            print("😣 Attempting to connect to Finnhub (Active)...")
            async with websockets.connect(FINNHUB_WS_URL) as ws:
                finnhub_ws = ws
                print("✅ Connected to Active Finnhub WebSocket.")

                # Initialize active_batches under lock
                async with active_subscription_lock:
                    active_batches = create_batches(active_subscribed_symbols, ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE)
                    # print(f"Initial active_batches: {active_batches}")

                # Subscribe to the initial batch
                await subscribe_next_batch()

                # Start rotation task
                rotation_task = asyncio.create_task(rotate_subscriptions())

                # Listen for incoming messages
                async for message in ws:
                    await handle_finnhub_message(message)

        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
            print(f"❌ Active WebSocket disconnected: {e}")
            finnhub_ws = None
            if rotation_task:
                rotation_task.cancel()
                try:
                    await rotation_task
                except asyncio.CancelledError:
                    pass
            await asyncio.sleep(10)  # Wait before reconnecting

        except Exception as e:
            print(f"❌ Unexpected error in Active Finnhub connection: {e}")
            finnhub_ws = None
            if rotation_task:
                rotation_task.cancel()
                try:
                    await rotation_task
                except asyncio.CancelledError:
                    pass
            await asyncio.sleep(10)  # Wait before reconnecting


def create_batches(symbols: Set[str], batch_size: int) -> List[List[str]]:
    """Divides symbols into active_batches of specified size."""
    symbols = sorted(symbols)  # Sort for consistency
    return [list(symbols)[i:i + batch_size] for i in range(0, len(symbols), batch_size)]


async def handle_finnhub_message(message: str):
    """
    Handles incoming messages from Finnhub.
    """
    global last_update_time
    current_time = time.time()

    # Always log the raw message to debug if nothing else is showing up
    # print("Message from Active Finnhub:", message)

    try:
        data = json.loads(message)

        # Some messages might not have 'type'
        msg_type = data.get("type", "UNKNOWN")
        
        # Enforce global time limit to avoid too many DB updates
        if current_time - last_update_time < FINNHUB_WEBSOCKET_MSG_DELAY:
            return

        if msg_type == "trade":
            updates = []
            for trade in data.get("data", []):
                symbol = trade.get("s")
                price = trade.get("p")
                if symbol and price is not None:
                    updates.append((round(price, 2), symbol))
            
            if updates:
                await bulk_update_active_stock_ltp_in_cache(updates)
                last_update_time = current_time

        # elif msg_type == "ping":
        #     # Finnhub might send ping messages, which we could handle if needed.
        #     print("💬 Received ping from Active Finnhub:", data)

        # elif msg_type == "info":
        #     # Sometimes Finnhub can send 'info' type messages with codes/warnings.
        #     print("💬 Info message from Active Finnhub:", data)

        # else:
        #     # If Finnhub sends something else, let's log it for debugging
        #     print(f"💬 Received a message with unknown type '{msg_type}':", data)

    except json.JSONDecodeError:
        print("❌ Received non-JSON message from Active Finnhub.")
    except Exception as ex:
        print(f"❌ Error handling Active Finnhub message: {ex}")


async def rotate_subscriptions():
    """
    Periodically rotate through the active_batches of symbols.
    """
    global active_current_batch, active_batches
    batch_index = 0  # To keep track of which batch to send next
    while True:
        try:
            async with active_subscription_lock:
                if not active_subscribed_symbols:
                    # print("No symbols to subscribe to. (Active)")
                    await asyncio.sleep(ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY)
                    continue

                # Recreate active_batches to include any new symbols
                active_batches = create_batches(active_subscribed_symbols, ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE)
                if not active_batches:
                    # print("No active_batches available after creating. (Active)")
                    await asyncio.sleep(ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY)
                    continue

                # Reset batch_index if it exceeds the number of active_batches
                if batch_index >= len(active_batches):
                    batch_index = 0

                # Get the next batch
                next_batch = set(active_batches[batch_index])
                batch_index += 1

                # print(f"🔄 Rotating to batch (Active): {next_batch}")
                symbols_to_subscribe = next_batch - active_current_batch
                symbols_to_unsubscribe = active_current_batch - next_batch

            # Unsubscribe outside the lock
            for symbol in symbols_to_unsubscribe:
                await send_unsubscription_message(symbol)

            # Subscribe to new symbols
            for symbol in symbols_to_subscribe:
                await send_subscription_message(symbol)

            # Update active_current_batch under lock
            async with active_subscription_lock:
                active_current_batch = next_batch
                # print(f"🔄 Current batch updated to (Active): {active_current_batch}")

            await asyncio.sleep(ACTIVE_FINNHUB_WEBSOCKET_ROTATION_FREQUENCY)

        except asyncio.CancelledError:
            print("✖️  Rotation task cancelled (Active).")
            break
        except Exception as e:
            print(f"❌ Error during subscription rotation (Active): {e}")
            await asyncio.sleep(5)  # Wait before retrying


async def subscribe_next_batch():
    """
    Subscribes to the first batch of symbols upon connection.
    """
    global active_current_batch, active_batches
    async with active_subscription_lock:
        if not active_batches:
            active_batches = create_batches(active_subscribed_symbols, ACTIVE_FINNHUB_WEBSOCKET_BATCH_SIZE)
            # print(f"🔄 Recreated active_batches in subscribe_next_batch: {active_batches}")

        if not active_batches:
            # print("No symbols to subscribe to initially. (Active)")
            return

        initial_batch = set(active_batches[0])  # Start with the first batch
        symbols_to_subscribe = initial_batch - active_current_batch
        active_current_batch = initial_batch
        # print(f"🔄 Initial batch (Active): {initial_batch}")

    # Subscribe outside the lock
    for symbol in symbols_to_subscribe:
        await send_subscription_message(symbol)


async def send_subscription_message(symbol: str):
    """
    Sends a subscription message for a symbol, if the WebSocket is open.
    """
    if finnhub_ws and finnhub_ws.open:
        try:
            await finnhub_ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
            print(f"🔔 Subscribed to (Active) {symbol}")
        except Exception as e:
            print(f"❌ Error subscribing to (Active) {symbol}: {e}")


async def send_unsubscription_message(symbol: str):
    """
    Sends an unsubscription message for a symbol, if the WebSocket is open.
    """
    if finnhub_ws and finnhub_ws.open:
        try:
            await finnhub_ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
            print(f"🔕 Unsubscribed from (Active) {symbol}")
        except Exception as e:
            print(f"❌ Error unsubscribing from (Active) {symbol}: {e}")


async def close_finnhub_active_connection():
    """
    Gracefully close the Finnhub WS connection, if open.
    """
    global finnhub_ws, rotation_task
    try:
        if finnhub_ws and finnhub_ws.open:
            print("Closing Active Finnhub WebSocket connection gracefully...")
            await finnhub_ws.close()
        finnhub_ws = None
        if rotation_task:
            rotation_task.cancel()
            try:
                await rotation_task
            except asyncio.CancelledError:
                pass
    except Exception as ex:
        print(f"❌ Error while closing Active Finnhub WebSocket: {ex}")