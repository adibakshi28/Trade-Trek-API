# app/routes/stocks.py

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.middlewares.jwt_auth import require_active_session
from app.services.data_service import search_stock_service

router = APIRouter()


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


