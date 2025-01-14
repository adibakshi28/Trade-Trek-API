# app/services/user_service.py

from fastapi import HTTPException
from typing import Optional, List, Dict, Any
from postgrest import APIError

from app.models.database import supabase
from app.core.config import config
from app.utils.finnhub import get_stock_quote
from app.models.sqlite_cache import execute_sql, check_table_exists
from app.models.sqlite_cache import get_from_table
from app.core.cache import create_stock_universe_cache

def user_funds_service(user_id: int):
    try:
        response = supabase.table("Cash").select("user_id", "cash").eq("user_id", user_id).eq("is_active", True).execute()        
        return response.data[0] if response.data else {"user_id": user_id, "cash": 0}
    except APIError as e:
        raise e
    
def user_info_service(user_id: int):
    try:
        response = supabase.table("Users").select("id", "first_name", "last_name", "username", "email").eq("id", user_id).eq("is_active", True).execute()        
        return response.data[0] or {}
    except APIError as e:
        raise e
    
def user_transactions_service(user_id: int):
    try:
        response = supabase.table("Transactions").select("id", "user_id", "stock_ticker", "direction", "quantity", "execution_price", "transaction_fee", "created_at").eq("user_id", user_id).eq("is_active", True).execute()
        return response.data or []
    except APIError as e:
        raise e
    
async def get_user_watchlist_service(user_id: int):
    STOCK_UNIVERSE_CACHE_TABLE = config["STOCK_UNIVERSE_CACHE_TABLE"]
    DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config["DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE"]

    try:
        watchlist_query = (
            supabase.table("Watchlist")
            .select("stock_ticker")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        watchlist_results = watchlist_query.data

        stock_tickers = [item['stock_ticker'] for item in watchlist_results]

        if stock_tickers:
            # Batch query to fetch stock names
            tickers_placeholder = ', '.join(f'"{ticker}"' for ticker in stock_tickers)
            query_stock_names = f"""
                SELECT stock_ticker, stock_name
                FROM {STOCK_UNIVERSE_CACHE_TABLE}
                WHERE stock_ticker IN ({tickers_placeholder});
            """
            results_stock_names = await execute_sql(query_stock_names, ())

            # Create a mapping of stock_ticker to stock_name
            stock_name_map = {row[0]: row[1] for row in results_stock_names}

            # Batch query to fetch prices
            query_prices = f"""
                SELECT stock_ticker, ltp, previous_close
                FROM {DORMANT_USER_STOCK_SUBSCRIPTION_CACHE_TABLE}
                WHERE stock_ticker IN ({tickers_placeholder});
            """
            results_prices = await execute_sql(query_prices, ())

            # Create mappings for ltp and previous_close
            price_data_map = {
                row[0]: {"ltp": row[1], "previous_close": row[2]} for row in results_prices
            }

            # Update watchlist_results with stock names, prices, and day_change
            for item in watchlist_results:
                stock_ticker = item['stock_ticker']
                item['stock_name'] = stock_name_map.get(stock_ticker, stock_ticker)
                
                # Default values if the stock_ticker is not found
                price_data = price_data_map.get(stock_ticker, {"ltp": 0, "previous_close": 0})
                
                item['price'] = price_data["ltp"]
                item['day_change'] = price_data["ltp"] - price_data["previous_close"]

        return watchlist_results
    except APIError as e:
        raise e
    
async def add_to_user_watchlist_service(user_id: int, ticker: str):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    MAX_STOCK_IN_WATCHLIST = config.get("MAX_STOCK_IN_WATCHLIST")
    try:
        if not await check_table_exists(STOCK_UNIVERSE_CACHE_TABLE):
            await create_stock_universe_cache()

        ticker = ticker.upper()
        query = f"""
            SELECT stock_ticker, stock_name
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker = "{ticker}";
        """
        params = ()
        results = await execute_sql(query, params)

        if not results:
            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )
        
        # Check if stock already exists in user's active watchlist
        watchlist_query = (
            supabase.table("Watchlist")
            .select("stock_ticker")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        watchlist_results = watchlist_query.data

        if any(item['stock_ticker'] == ticker for item in watchlist_results):   
            current_watchlist = await get_user_watchlist_service(user_id)

            return {
                "success": False,
                "message": f"{ticker} already exists in your watchlist.",
                "watchlist": current_watchlist
            }
        
        if len(watchlist_results) >= MAX_STOCK_IN_WATCHLIST:
            return {
                "success": False,
                "message": f"Maximum of {MAX_STOCK_IN_WATCHLIST} stocks allowed in watchlist.",
            }

        # Add stock to watchlist
        response = (
            supabase.table("Watchlist")
            .insert({
                "user_id": user_id,
                "stock_ticker": ticker,
                "is_active": True
            })
            .execute()
        )

        current_watchlist = await get_user_watchlist_service(user_id)

        return {
            "success": True,
            "message": f"{ticker} added to your watchlist successfully.",
            "watchlist": current_watchlist
        }
    except APIError as e:
        raise e
    
async def remove_from_user_watchlist_service(user_id: int, ticker: str):
    STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
    try:
        if not await check_table_exists(STOCK_UNIVERSE_CACHE_TABLE):
            await create_stock_universe_cache()

        ticker = ticker.upper()
        query = f"""
            SELECT stock_ticker, stock_name
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker = "{ticker}";
        """
        params = ()
        results = await execute_sql(query, params)

        if not results:
            raise HTTPException(
                status_code=404,
                detail="Stock not found"
            )
        
        # Check if stock exists in user's active watchlist
        watchlist_query = (
            supabase.table("Watchlist")
            .select("id")
            .eq("user_id", user_id)
            .eq("stock_ticker", ticker)
            .eq("is_active", True)
            .execute()
        )

        watchlist_results = watchlist_query.data
        if not watchlist_results:
            current_watchlist = await get_user_watchlist_service(user_id)
        
            return {
                "success": False,
                "message": f"{ticker} not found in your watchlist.",
                "watchlist": current_watchlist
            }

        # Update stock to set is_active to False
        update_query = (
            supabase.table("Watchlist")
            .update({
                "is_active": False
            })
            .eq("user_id", user_id).eq("stock_ticker", ticker).eq("is_active", True)
            .execute()
        )

        current_watchlist = await get_user_watchlist_service(user_id)

        return {
            "success": True,
            "message": f"{ticker} removed from your watchlist successfully.",
            "watchlist": current_watchlist
        }

    except APIError as e:
        raise e
    
async def user_portfolio_service(user_id: int):
    try:
        response = supabase.table("Holdings").select(
            "id", "user_id", "stock_ticker", "direction", 
            "quantity", "execution_price", "created_at"
        ).eq("user_id", user_id).eq("is_active", True).execute()
        
        portfolio = response.data or []
        
        if not portfolio:
            return portfolio

        unique_tickers = list({p["stock_ticker"] for p in portfolio})
        
        STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
        placeholders = ", ".join(["?"] * len(unique_tickers))
        
        query = f"""
            SELECT stock_ticker, stock_name 
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker IN ({placeholders});
        """
        params = tuple(unique_tickers)
        stock_results = await execute_sql(query, params)

        stock_name_lookup = {row[0]: row[1] for row in stock_results}

        for p in portfolio:
            p["stock_name"] = stock_name_lookup.get(p["stock_ticker"], p["stock_ticker"])
            p['direction'] = 'SHORT' if p['direction'] == 'SELL' else 'LONG'
        
        return portfolio

    except APIError as e:
        raise e
    

def user_portfolio_history_service(user_id: int):
    try:
        STOCK_INDEX_TICKER = config["STOCK_INDEX_TICKER"]

        # Fetch user's portfolio history (Table indexed on user_id) (Not filtered by is_active to optimize query)
        portfolio_history_response = supabase.table("Portfolio_History").select(
            "holding_value", "unrealised_pnl", "cash", "timestamp"
        ).eq("user_id", user_id).execute()

        portfolio_history = portfolio_history_response.data or []
        
        if not portfolio_history:
            return portfolio_history
        
        # Fetch stock index history (Table indexed on stock_ticker) (Not filtered by is_active to optimize query)
        stock_index_history_response = supabase.table("Stock_History").select(
            "price", "timestamp"
        ).eq("stock_ticker", STOCK_INDEX_TICKER).execute()

        stock_index_history_response = stock_index_history_response.data or []

        response = {
            "user_id": user_id,
            "portfolio_history": portfolio_history,
            "stock_index": STOCK_INDEX_TICKER,
            "stock_index_history": stock_index_history_response
        }

        return response
    except APIError as e:
        raise e

async def user_trade_summary_service(user_id: int):
    try:
        r = supabase.table("Cash").select("user_id", "cash") \
                     .eq("user_id", user_id).eq("is_active", True).execute()
        current_cash = float(r.data[0]['cash']) if r.data else 0.0
        t = supabase.table("Transactions").select(
            "id", "user_id", "stock_ticker", "direction", "quantity",
            "execution_price", "transaction_fee", "created_at"
        ).eq("user_id", user_id).eq("is_active", True).execute()
        txs = t.data if t and t.data else []
        pos = {}
        for x in txs:
            s = x["stock_ticker"]
            d = x["direction"].upper()
            q = float(x["quantity"])
            p = float(x["execution_price"])
            f = float(x["transaction_fee"])
            if s not in pos:
                pos[s] = {"qty": 0.0, "avg": 0.0, "realized": 0.0}
            po = pos[s]
            oq = po["qty"]
            oc = po["avg"]
            if d == "BUY":
                if oq >= 0:
                    nq = oq + q
                    tc = (oq * oc)
                    tc += (q * p) + f
                    if nq != 0:
                        po["avg"] = tc / nq
                    else:
                        po["avg"] = 0.0
                    po["qty"] = nq
                else:
                    cvr = min(abs(oq), q)
                    if cvr > 0:
                        if oq < 0:
                            opn_val = abs(oq) * oc
                            buy_val = cvr * p
                            g = (oc - p) * cvr
                            g -= f * (cvr / q)
                            po["realized"] += g
                            po["qty"] = oq + cvr
                        if po["qty"] == 0:
                            po["avg"] = 0.0
                    rem = q - cvr
                    if rem > 0:
                        nq = po["qty"] + rem
                        tc = po["qty"] * po["avg"]
                        tc += (rem * p) + f
                        if nq != 0:
                            po["avg"] = tc / nq
                        else:
                            po["avg"] = 0.0
                        po["qty"] = nq
            elif d == "SELL":
                if oq <= 0:
                    nq = oq - q
                    tc = abs(oq) * oc
                    tc += (q * p) + f
                    if nq != 0:
                        po["avg"] = tc / abs(nq)
                    else:
                        po["avg"] = 0.0
                    po["qty"] = nq
                else:
                    cvr = min(oq, q)
                    if cvr > 0:
                        s_val = cvr * p
                        cost_val = cvr * oc
                        g = (p - oc) * cvr
                        g -= f * (cvr / q)
                        po["realized"] += g
                        po["qty"] = oq - cvr
                    rem = q - cvr
                    if rem > 0:
                        nq = po["qty"] - rem
                        tc = abs(po["qty"]) * po["avg"]
                        tc += (rem * p) + f
                        if nq != 0:
                            po["avg"] = tc / abs(nq)
                        else:
                            po["avg"] = 0.0
                        po["qty"] = nq
        tv = 0.0
        rp = 0.0
        up = 0.0
        ib = 0.0
        ts = {}

        ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE = config.get("ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE")
        res = await get_from_table(ACTIVE_USER_STOCK_SUBSCRIPTION_CACHE_TABLE)
        stock_cache_dict = {row[0]: row[1] for row in res}

        for s, v in pos.items():
            q = v["qty"]
            a = v["avg"]
            r = v["realized"]
            try:
                cp = stock_cache_dict.get(s, 0.0)
            except:
                cp = round(a, 2) if a > 0 else 0.0
            cv = q * cp
            ic = q * a
            u = cv - ic
            rp += r
            up += u
            ib += ic
            tv += cv
            ts[s] = {
                "quantity": round(q, 4),
                "avg_cost": round(a, 4),
                "current_price": round(cp, 4),
                "current_value": round(cv, 4),
                "invested_cost_basis": round(ic, 4),
                "unrealized_pl": round(u, 4),
                "realized_pl": round(r, 4)
            }
        mv = tv
        pv = current_cash + mv
        s = {
            "cash_balance": round(current_cash, 2),
            "positions_market_value": round(mv, 2),
            "portfolio_value": round(pv, 2),
            "total_realized_pl": round(rp, 2),
            "total_unrealized_pl": round(up, 2),
            "total_invested_cost_basis": round(ib, 2),
            "total_pl": round(rp + up, 2),
            "ticker_summaries": ts
        }
        return s
    except APIError as e:
        raise e
    except Exception as ex:
        raise ex