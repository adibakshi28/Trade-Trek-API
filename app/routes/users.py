# app/routes/users.py

from fastapi import APIRouter, Depends
from typing import List, Dict

from app.middlewares.jwt_auth import require_active_session
from app.services.user_service import user_transactions_service, user_funds_service, user_info_service, user_portfolio_service, user_trade_summary_service

router = APIRouter()

@router.get("/")
def get_user_info(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns information about a specific user
    """
    user_id = payload.get("user_id")
    user = user_info_service(user_id)
    return user

@router.get("/transactions")
def get_user_transactions(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Return all user transactions
    """
    user_id = payload.get("user_id")
    transactions = user_transactions_service(user_id)
    return transactions

@router.get("/portfolio")
def get_user_portfolio(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Return all user transactions
    """
    user_id = payload.get("user_id")
    transactions = user_portfolio_service(user_id)
    return transactions

@router.get("/funds")
def get_user_funds(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Return available funds for the user
    """
    user_id = payload.get("user_id")
    funds = user_funds_service(user_id)
    return funds


@router.get("/summary")
async def get_user_trade_summary(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns the users trade summary with statistics

    Stats:

    cash_balance: The user’s cash on hand (already correct from the DB).
    positions_market_value: Sum of (quantity * current_price) across all tickers.
    portfolio_value: cash_balance + positions_market_value.
    total_realized_pl: The net profit/loss from all fully or partially closed shares, including relevant fees.
    total_unrealized_pl: The net profit/loss on currently open positions (current_value - invested_cost_basis).
    total_invested_cost_basis: For open positions, (quantity * avg_cost). Negative if short.
    total_pl: total_realized_pl + total_unrealized_pl.
    ticker_summaries: A breakdown for each ticker:
        quantity: Current position size (>0 is long, <0 is short).
        avg_cost: The average (split-adjusted) cost basis of the open position (including fees from opening/adding).
        current_price: Latest market price fetched from get_stock_quote.
        current_value: quantity * current_price.
        invested_cost_basis: quantity * avg_cost.
        unrealized_pl: current_value - invested_cost_basis for open shares.
        realized_pl: Total gains/losses closed out so far, net of fees from both opening and closing.
    """
    user_id = payload.get("user_id")
    summary = await user_trade_summary_service(user_id)
    return summary



