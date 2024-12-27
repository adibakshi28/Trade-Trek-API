# app/routes/stocks.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from app.middlewares.jwt_auth import require_active_session
from app.services.data_service import search_stock_service, stock_info_service, stock_historical_service, stock_transaction_service

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
async def get_stock_info(ticker: str, payload: dict = Depends(require_active_session)):
    """
    Get historical price info for a stock ticker.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock = await stock_historical_service(ticker)
    return stock


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

