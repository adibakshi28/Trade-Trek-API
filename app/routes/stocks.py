# app/routes/stocks.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from app.middlewares.jwt_auth import require_active_session
from app.services.data_service import search_stock_service, stock_info_service, stock_historical_service, stock_transaction_service, stock_quote_service, stock_transaction_value_service, stock_universe_service

router = APIRouter()


@router.get("/")
async def get_stock_info(ticker: str, payload: dict = Depends(require_active_session)):
    """
    Get information for a stock.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock = await stock_info_service(ticker)
    return stock


@router.get("/historical")
async def get_stock_info(ticker: str, start_date: str, end_date: str, resolution: str, payload: dict = Depends(require_active_session)):
    """
    Get historical price info for a stock ticker.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock = await stock_historical_service(ticker, start_date, end_date, resolution)
    return stock


@router.get("/quote")
async def stock_quote(ticker: str,  payload: dict = Depends(require_active_session)):
    """
    Get current price quote for a stock ticker.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock_quote = await stock_quote_service(ticker)
    return stock_quote

@router.get("/search")
async def search_stock(
    ticker: str, asset_type: Optional[str] = Query(None, regex="^(STOCK|CRYPTO|FOREX)$"), payload: dict = Depends(require_active_session)):
    """
    Search for assets (STOCK, CRYPTO, FOREX) by a part of their ticker.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock = await search_stock_service(ticker, 10, asset_type)
    return stock

@router.post("/transaction")
async def make_stock_transaction(ticker: str, direction: str, quantity: float, payload: dict = Depends(require_active_session)):
    """
    Make a stock transaction.
    """
    user_id = payload.get("user_id")
    
    if not ticker or not direction or not quantity:
        raise HTTPException(
            status_code=400,
            detail="ticker, direction, and quantity are required"
        )
    
    transaction = await stock_transaction_service(user_id, ticker, direction, quantity)
    return transaction


@router.get("/transaction/value")
async def get_transaction_value(ticker: str, quantity: float, current_price: Optional[float] = None, payload: dict = Depends(require_active_session)):
    """
    Get stock transaction value.
    """
    user_id = payload.get("user_id")

    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    transaction_value = await stock_transaction_value_service(user_id, ticker, quantity, current_price)
    return transaction_value


@router.get("/universe")
async def get_stock_universe(payload: dict = Depends(require_active_session)):
    """
    Gets the entire stock universe.
    """
    stock_universe = await stock_universe_service()
    return stock_universe



