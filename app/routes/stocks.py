# app/routes/stocks.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.middlewares.jwt_auth import require_active_session
from app.services.data_service import search_stock_service, stock_info_service, stock_historical_service

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
async def search_stock(ticker: str, payload: dict = Depends(require_active_session)):
    """
    Search for stocks by a part of their ticker.
    """
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker parameter is required"
        )

    stock = await search_stock_service(ticker, 5)
    return stock
