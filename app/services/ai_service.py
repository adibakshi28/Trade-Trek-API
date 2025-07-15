# app/services/ai_service.py

from pydantic import BaseModel
import requests
import json
from fastapi import HTTPException
from typing import Optional, List, Dict, Any
from postgrest import APIError

from app.models.database import supabase
from app.core.config import config
from app.utils.finnhub import get_stock_quote
from app.models.sqlite_cache import execute_sql, check_table_exists
from app.models.sqlite_cache import get_from_table
from app.core.cache import create_stock_universe_cache
from app.services.calculation_service import calculate_metrics_service

from app.core.config import DEEPSEEK_API_KEY

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

def ask_ai_service(user_id: int, input_str: str):
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a financial expert and a professional trader specializing in stocks."},
                {"role": "user", "content": input_str}
            ],
            "stream": False,  
            "temperature": 0.3,  
            "max_tokens": 256,  
            "top_p": 0.9,  # Nucleus sampling (more relevant tokens)
            "frequency_penalty": 0,  # No penalty for repeating words
            "presence_penalty": 0  # No penalty for introducing new topics
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            result = response.json()
            return {"reply": result["choices"][0]["message"]["content"].strip()}
        else:
            return {"error": True}

    except Exception as e:
        raise e
    

async def metric_insights_service(user_id: int, metric_config: Dict):
    try:
        metric_config["settings"]['include_portfolio'] = True

        metric_result = await calculate_metrics_service(user_id, metric_config)
        metric_result_str = json.dumps(metric_result)
        metric_result_str = "These are my risk and performance metrics for the portfolio along with my current portfolio :\n" + metric_result_str
    
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a financial expert and a professional trader specializing in stocks. Provide accurate, actionable insights exclusively related to stock analysis, trading strategies, portfolio optimization, and risk management. Avoid suggesting options, ETFs, or assets outside the S&P 500 universe. You reply in no more than 350 words."},
                {"role": "user", "content": metric_result_str}
            ],
            "stream": False, 
            "temperature": 0, 
            "max_tokens": 1024 ,
            "top_p": 0.9,  # Nucleus sampling (more relevant tokens)
            "frequency_penalty": 0,  # No penalty for repeating words
            "presence_penalty": 0  # No penalty for introducing new topics
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            result = response.json()
            return {"reply": result["choices"][0]["message"]["content"].strip()}
        else:
            return {"error": True}

    except Exception as e:
        raise e

async def stock_insights_service(user_id: int, stock_data: Dict):
    try:
        stock_data_str = json.dumps(stock_data)
        stock_data_str = "This is the data for a stock, what do you think about it ? :\n" + stock_data_str
    
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a financial expert and a professional trader specializing in stocks. You reply in no more than 350 words."},
                {"role": "user", "content": stock_data_str}
            ],
            "stream": False,  
            "temperature": 0,  
            "max_tokens": 512,  
            "top_p": 0.9,  # Nucleus sampling (more relevant tokens)
            "frequency_penalty": 0,  # No penalty for repeating words
            "presence_penalty": 0  # No penalty for introducing new topics
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            result = response.json()
            return {"reply": result["choices"][0]["message"]["content"].strip()}
        else:
            return {"error": True}

    except Exception as e:
        raise e

