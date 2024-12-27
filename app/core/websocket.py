# app/core/websocket.py

import asyncio
import json
from typing import Set

import websockets
from fastapi import APIRouter
from app.core.config import config, FINNHUB_API_KEY
from app.core.cache import update_stock_ltp_in_cache

router = APIRouter()

FINNHUB_WEBSOCKET_URL = config['FINNHUB_WEBSOCKET_URL']
FINNHUB_WS_URL = f"{FINNHUB_WEBSOCKET_URL}?token={FINNHUB_API_KEY}"

subscribed_symbols: Set[str] = set()
finnhub_ws = None

async def connect_to_finnhub():
    global finnhub_ws
    while True:
        try:
            print("Attempting to connect to Finnhub...")
            async with websockets.connect(FINNHUB_WS_URL) as ws:
                finnhub_ws = ws
                await subscribe_existing_symbols()
                async for message in ws:
                    await handle_finnhub_message(message)

        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
            print(f"WebSocket disconnected: {e}")
            finnhub_ws = None
            await asyncio.sleep(10)

        except Exception as e:
            print(f"Unexpected error in Finnhub connection: {e}")
            finnhub_ws = None
            await asyncio.sleep(10)

async def handle_finnhub_message(message: str):
    try:
        data = json.loads(message)
        if data.get("type") == "trade":
            for trade in data.get("data", []):
                symbol = trade.get("s")
                price = trade.get("p")
                if symbol and price is not None:
                    await update_stock_ltp_in_cache(symbol, price)
    except json.JSONDecodeError:
        print("Received non-JSON message from Finnhub.")
    except Exception as ex:
        print(f"Error handling Finnhub message: {ex}")

async def subscribe_existing_symbols():
    for symbol in subscribed_symbols:
        await subscribe_symbol(symbol)

async def subscribe_symbol(symbol: str):
    if symbol not in subscribed_symbols:
        subscribed_symbols.add(symbol)
    if finnhub_ws and finnhub_ws.open:
        await finnhub_ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
        print(f"🔔 Subscribed to {symbol}")

async def unsubscribe_symbol(symbol: str):
    if symbol in subscribed_symbols:
        subscribed_symbols.remove(symbol)
    if finnhub_ws and finnhub_ws.open:
        await finnhub_ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
        print(f"🔕 Unsubscribed from {symbol}")

async def close_finnhub_connection():
    """
    Gracefully close the Finnhub WS connection, if open.
    """
    global finnhub_ws
    try:
        if finnhub_ws and finnhub_ws.open:
            print("Closing Finnhub WebSocket connection gracefully...")
            await finnhub_ws.close()
        finnhub_ws = None
    except Exception as ex:
        print(f"Error while closing Finnhub WebSocket: {ex}")
