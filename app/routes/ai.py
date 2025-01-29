# app/routes/users.py

from fastapi import APIRouter, Depends
from typing import List, Dict, Optional

from app.middlewares.jwt_auth import require_active_session
from app.services.ai_service import ask_ai_service, metric_insights_service, stock_insights_service
from app.services.calculation_service import calculate_metrics_service

router = APIRouter()

@router.get("/ask-deepseek")
def ask_ai(input_str: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Ask Deepseek 
    """
    user_id = payload.get("user_id")
    res = ask_ai_service(user_id, input_str)
    return res


@router.post("/metric-insights")
async def get_metric_insights(metric_config: dict, payload: dict = Depends(require_active_session)):
    """
    Get metric insights from the user's portfolio metrics using AI
    """
    user_id = payload.get("user_id")
    response = await metric_insights_service(user_id, metric_config)
    return response


@router.post("/stock-insights")
async def get_stock_insights(stock_data: dict, payload: dict = Depends(require_active_session)):
    """
    Get stock insights from the stock data using AI
    """
    user_id = payload.get("user_id")
    response = await stock_insights_service(user_id, stock_data)
    return response