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
    except Exception as e:
        raise e
    
def user_info_service(user_id: int):
    try:
        response = supabase.table("Users").select("id", "first_name", "last_name", "username", "email").eq("id", user_id).eq("is_active", True).execute()        
        return response.data[0] or {}
    except Exception as e:
        raise e
    
def user_transactions_service(user_id: int):
    try:
        response = supabase.table("Transactions").select("id", "user_id", "stock_ticker", "direction", "quantity", "execution_price", "transaction_fee", "created_at").eq("user_id", user_id).eq("is_active", True).execute()
        return response.data or []
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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

    except Exception as e:
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
            SELECT stock_ticker, stock_name, sector, sub_sector 
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker IN ({placeholders});
        """
        params = tuple(unique_tickers)
        stock_results = await execute_sql(query, params)

        stock_name_lookup = {row[0]: row[1] for row in stock_results}
        stock_sector_lookup = {row[0]: row[2] for row in stock_results}
        stock_sub_sector_lookup = {row[0]: row[3] for row in stock_results}

        for p in portfolio:
            p["execution_price"] = round(p["execution_price"], 0)
            p["stock_name"] = stock_name_lookup.get(p["stock_ticker"], p["stock_ticker"])
            p["sector"] = stock_sector_lookup.get(p["stock_ticker"], "")
            p["sub_sector"] = stock_sub_sector_lookup.get(p["stock_ticker"], "")
            if p["direction"] == "SELL" or p['direction'] == 'BUY':
                p['direction'] = 'SHORT' if p['direction'] == 'SELL' else 'LONG'
        
        for p in portfolio:
            p["value"] = round(p["quantity"] * p["execution_price"], 2)
        
        total_portfolio_value = sum(p["value"] for p in portfolio)
        
        if total_portfolio_value > 0:
            for p in portfolio:
                p["stock_percentage"] = round((p["value"] / total_portfolio_value) * 100, 2)
            
            sector_totals = {}
            for p in portfolio:
                sector = p["sector"]
                sector_totals[sector] = sector_totals.get(sector, 0) + p["value"]
            
            sector_percentages = {
                sector: (value / total_portfolio_value) * 100 
                for sector, value in sector_totals.items()
            }
            
            for p in portfolio:
                p["sector_percentage"] = round(sector_percentages.get(p["sector"], 0), 2)
        
        return portfolio

    except Exception as e:
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
    except Exception as e:
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
    


def _create_notification_utility(insert_data):
    try:
        supabase.table("Notifications").insert(insert_data).execute()
        return True
    except Exception as e:
        return False


def notification_service(user_id: int):
    try:
        response = supabase.table("Notifications").select("id", "description", "type", "read", "created_at").eq("user_id", user_id).eq("is_active", True).execute()        
        result =  response.data if response.data else []
    
        unread_count = len([item for item in result if item['read'] == False])
        return {"notifications": result, "unread_count": unread_count}
    except Exception as e:
        raise e
    

def mark_notification_read_service(user_id: int, notification_id: int):
    try:
        supabase.table("Notifications").update({"read": True}).eq("user_id", user_id).eq("id", notification_id).eq("is_active", True).execute()
        result = notification_service(user_id)

        return result
    except Exception as e:
        raise e


def get_user_friends_service(user_id: int):
    try:
        friends = set()
        response = supabase.table("Friends").select("user_1").eq("user_2", user_id).eq("is_active", True).execute()
        if response.data:
            friends.update(item["user_1"] for item in response.data)
        response = supabase.table("Friends").select("user_2").eq("user_1", user_id).eq("is_active", True).execute()
        if response.data:
            friends.update(item["user_2"] for item in response.data)
        if not friends:
            return []
        response = supabase.table("Users").select("id", "username, email, first_name, last_name").in_("id", list(friends)).eq("is_active", True).execute()
        return response.data or []

    except Exception as e:
        raise e
    

# TODO: Check if user has already sent a friend request to the recipient
def user_friend_search_to_add_service(user_id: int, user_name_str: str):
    try:
        user_response = supabase.table("Users").select(
            "id, username, email, first_name, last_name"
        ).ilike("username", f"%{user_name_str}%").eq("is_active", True).execute()
        
        if not user_response.data:
            return []

        friends = set()
        
        friends_response_1 = supabase.table("Friends").select("user_1").eq("user_2", user_id).eq("is_active", True).execute()
        if friends_response_1.data:
            friends.update(item["user_1"] for item in friends_response_1.data)
        
        friends_response_2 = supabase.table("Friends").select("user_2").eq("user_1", user_id).eq("is_active", True).execute()
        if friends_response_2.data:
            friends.update(item["user_2"] for item in friends_response_2.data)
        
        potential_friends = [
            item for item in user_response.data if item["id"] not in friends
        ]

        return potential_friends[:5]
    
    except Exception as e:
        raise e


    
def send_friend_request_service(user_id: int, request_to_username: str):
    try:
        # Fetch the recipient's user ID
        recipient_response = supabase.table("Users") \
            .select("id") \
            .eq("username", request_to_username) \
            .eq("is_active", True) \
            .execute()
        
        if not recipient_response.data:
            return {"success": False, "message": "Recipient user not found."}
        
        request_to_user_id = recipient_response.data[0]["id"]

        # Fetch the sender's username
        sender_response = supabase.table("Users") \
            .select("username") \
            .eq("id", user_id) \
            .eq("is_active", True) \
            .execute()
        
        if not sender_response.data:
            return {"success": False, "message": "Sender user not found."}
        
        sent_by_username = sender_response.data[0]["username"]

        # Function to check existing records
        def record_exists(table, conditions):
            query = supabase.table(table).select("id").eq("is_active", True)
            for field, value in conditions.items():
                query = query.eq(field, value)
            result = query.execute()
            return bool(result.data)

        # Check if users are already friends
        is_friends = (
            record_exists("Friends", {"user_1": user_id, "user_2": request_to_user_id}) or
            record_exists("Friends", {"user_1": request_to_user_id, "user_2": user_id})
        )
        
        if is_friends:
            return {"success": False, "message": "You are already friends."}

        # Check if a friend request already exists
        request_exists = (
            record_exists("Friend_Requests", {"sent_by_id": user_id, "received_by_id": request_to_user_id}) or
            record_exists("Friend_Requests", {"sent_by_id": request_to_user_id, "received_by_id": user_id})
        )
        
        if request_exists:
            return {"success": False, "message": "A friend request already exists."}

        # Create a new friend request
        supabase.table("Friend_Requests").insert({
            "sent_by_id": user_id,
            "received_by_id": request_to_user_id,
            "status": "PENDING",
            "is_active": True
        }).execute()

        # Prepare notification data
        notification_data = {
            "user_id": request_to_user_id,
            "description": f"{sent_by_username} sent you a friend request.",
            "type": "FRIEND_REQUEST",
            "read": False,
            "is_active": True
        }

        # Send notification
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        return {"success": True, "message": f"Friend request sent to {request_to_username} successfully."}
    
    except Exception as e:
        return {"success": False, "message": "An error occurred while processing your request."}

    
def accept_friend_request_service(user_id: int, accepted_username: str):
    try:
        # Helper function to check if a record exists based on conditions
        def record_exists(table, conditions):
            query = supabase.table(table).select("id").eq("is_active", True)
            for field, value in conditions.items():
                query = query.eq(field, value)
            result = query.execute()
            return bool(result.data)

        # Fetch the user ID of the accepted_username
        recipient_response = supabase.table("Users") \
            .select("id") \
            .eq("username", accepted_username) \
            .eq("is_active", True) \
            .execute()
        
        if not recipient_response.data:
            return {"success": False, "message": "User not found."}
        
        accepted_user_id = recipient_response.data[0]["id"]

        # Fetch the username of the user_id (sender)
        sender_response = supabase.table("Users") \
            .select("username") \
            .eq("id", user_id) \
            .eq("is_active", True) \
            .execute()
        
        if not sender_response.data:
            return {"success": False, "message": "Sender not found."}
        
        sender_username = sender_response.data[0]["username"]

        # **Check if the friend request exists**
        # The friend request should be from accepted_user_id to user_id
        friend_request_exists = record_exists("Friend_Requests", {
            "sent_by_id": accepted_user_id,
            "received_by_id": user_id,
            "status": "PENDING"
        })
        
        if not friend_request_exists:
            return {"success": False, "message": "Friend request does not exist."}

        # Check if the friendship already exists
        is_already_friends = (
            record_exists("Friends", {"user_1": user_id, "user_2": accepted_user_id}) or
            record_exists("Friends", {"user_1": accepted_user_id, "user_2": user_id})
        )
        
        if is_already_friends:
            return {"success": False, "message": "Friendship already exists."}

        # Create Friendship
        supabase.table("Friends").insert({
            "user_1": user_id,
            "user_2": accepted_user_id,
            "is_active": True
        }).execute()

        # Update Friend Request Status to ACCEPTED
        supabase.table("Friend_Requests").update({
            "status": "ACCEPTED",
            "is_active": False
        }).eq("sent_by_id", accepted_user_id) \
          .eq("received_by_id", user_id) \
          .eq("status", "PENDING") \
          .execute()

        # Send Notification to the Accepted User
        notification_data = {  
            "user_id": accepted_user_id,
            "description": f"{sender_username} accepted your friend request.",
            "type": "FRIEND_ACCEPTED",
            "read": False,
            "is_active": True
        }
        
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        # Mark the Original Notification as Read and Inactive
        supabase.table("Notifications").update({
            "read": True, "is_active": False
        }).eq("user_id", user_id) \
          .eq("description", f"{accepted_username} sent you a friend request.") \
          .execute()

        return {"success": True, "message": f"Friend request from {accepted_username} accepted successfully."}
    
    except Exception as e:
        print(f"APIError: {e}")
        return {"success": False, "message": "An error occurred while processing your request."}
    

def decline_friend_request_service(user_id: int, declined_username: str):
    try:
        # Helper function to check if a record exists based on conditions
        def record_exists(table, conditions):
            query = supabase.table(table).select("id").eq("is_active", True)
            for field, value in conditions.items():
                query = query.eq(field, value)
            result = query.execute()
            return bool(result.data)

        # Fetch the user ID of the declined_username
        recipient_response = supabase.table("Users") \
            .select("id") \
            .eq("username", declined_username) \
            .eq("is_active", True) \
            .execute()
        
        if not recipient_response.data:
            return {"success": False, "message": "User not found."}
        
        declined_user_id = recipient_response.data[0]["id"]

        # Fetch the username of the user_id (declining user)
        sender_response = supabase.table("Users") \
            .select("username") \
            .eq("id", user_id) \
            .eq("is_active", True) \
            .execute()
        
        if not sender_response.data:
            return {"success": False, "message": "Sender not found."}
        
        sender_username = sender_response.data[0]["username"]

        # Check if the friend request exists
        # The friend request should be from declined_user_id to user_id
        friend_request_exists = record_exists("Friend_Requests", {
            "sent_by_id": declined_user_id,
            "received_by_id": user_id,
            "status": "PENDING"
        })
        
        if not friend_request_exists:
            return {"success": False, "message": "Friend request does not exist."}

        # Check if the friendship already exists
        is_already_friends = (
            record_exists("Friends", {"user_1": user_id, "user_2": declined_user_id}) or
            record_exists("Friends", {"user_1": declined_user_id, "user_2": user_id})
        )
        
        if is_already_friends:
            return {"success": False, "message": "Friendship already exists."}

        # Update Friend Request Status to DECLINED
        update_response = supabase.table("Friend_Requests").update({
            "status": "DECLINED",
            "is_active": False
        }).eq("sent_by_id", declined_user_id) \
          .eq("received_by_id", user_id) \
          .eq("status", "PENDING") \
          .execute()
        
        if not update_response.data:
            return {"success": False, "message": "Failed to update friend request status."}

        # Send Notification to the Declined User
        notification_data = {
            "user_id": declined_user_id,
            "description": f"{sender_username} declined your friend request.",
            "type": "FRIEND_DECLINED",
            "read": False,
            "is_active": True
        }
        
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        # Mark the Original Notification as Read and Inactive
        supabase.table("Notifications").update({
            "read": True, "is_active": False
        }).eq("user_id", user_id) \
          .eq("description", f"{declined_username} sent you a friend request.") \
          .execute()

        return {"success": True, "message": f"Friend request from {declined_username} declined successfully."}
    
    except Exception as e:
        print(f"APIError: {e}")
        return {"success": False, "message": "An error occurred while processing your request."}
    

def get_all_groups_for_user_service(user_id: int):
    try:
        response = supabase.table("Group_Members") \
            .select("group_id, Groups(group_name, description)") \
            .eq("user_id", user_id) \
            .eq("is_active", True) \
            .eq("Groups.is_active", True) \
            .execute()

        return [{
            "group_id": item["group_id"],
            "group_name": item["Groups"]["group_name"],
            "description": item["Groups"]["description"]
        } for item in response.data if item.get("Groups")]

    except Exception as e:
        raise e


def create_group_service(user_id: int, group_name: str, group_description: Optional[str]):
    try:
        # Check if the group_name already exists
        group = supabase.table("Groups").select("id").eq("group_name", group_name).eq("is_active", True).execute()
        if group.data:
            return {"success": False, "message": "Group name already exists. Chose a different name."}
        
        supabase.table("Groups").insert({"leader_id": user_id, "group_name": group_name, "description": group_description, "is_active": True}).execute()
        
        # Add the leader as a member of the group
        group = supabase.table("Groups").select("id").eq("group_name", group_name).eq("is_active", True).execute()
        group_id = group.data[0]["id"]
        supabase.table("Group_Members").insert({"group_id": group_id, "user_id": user_id, "is_active": True}).execute()


        return {"success": True, "message": f"Group {group_name} created successfully."}
    except Exception as e:
        raise e


def group_info_service(user_id: int, group_name: str):
    try:
        group_res = supabase.table("Groups").select(
            "id, leader_id, description, Users!leader_id(username)"
        ).ilike("group_name", group_name).eq("is_active", True).execute()

        if not group_res.data:
            return {"success": False, "message": "Group not found or inactive"}

        group_data = group_res.data[0]
        group_id = group_data["id"]

        # Get all active members in one query
        members_res = supabase.table("Group_Members").select(
            "user_id, Users!user_id(username)"
        ).eq("group_id", group_id).eq("is_active", True).execute()

        return {
            "success": True,
            "group_name": group_name,
            "description": group_data.get("description", ""),
            "leader": group_data["Users"].get("username", "Unknown"),
            "members": [m["Users"]["username"] for m in members_res.data if m.get("Users")]
        }

    except Exception as e:
        return {"success": False, "message": "Failed to fetch group info"}
    
# TODO: Check if user is already invited to the group
# TODO: Check if the user searching is the member of the group 
def user_group_search_to_add_service (user_id: int, user_name_str: str, group_name_str: str):

    try:
        # Fetch user_ids of users with usernames matching user_name_str
        user_ids_res = supabase.table("Users").select("id").ilike("username", f"%{user_name_str}%").eq("is_active", True).execute()
        user_ids = [item["id"] for item in user_ids_res.data]

        if not user_ids:
            return []

        # Fetch user_ids of users who are already members of the group
        group_res = supabase.table("Groups").select("id").ilike("group_name", f"%{group_name_str}%").eq("is_active", True).execute()
        group_id = group_res.data[0]["id"]
        group_members_res = supabase.table("Group_Members").select("user_id").eq("group_id", group_id).eq("is_active", True).execute()
        group_members = [item["user_id"] for item in group_members_res.data]

        # Filter out users who are already members of the group
        users_to_add = [user_id for user_id in user_ids if user_id not in group_members]

        # Fetch user details of users to add
        users_res = supabase.table("Users").select("id", "username, email, first_name, last_name").in_("id", users_to_add).eq("is_active", True).execute()
        return users_res.data[:5] or []

    except Exception as e:
        return []
    

# TODO: Check if user is already invited to the group
def user_group_search_to_join_service(user_id: int, group_name_str: str):
    try:
        # Fetch all active groups matching the search term
        groups_response = supabase.table("Groups").select("id", "group_name").ilike("group_name", f"%{group_name_str}%").eq("is_active", True).execute()
        if not groups_response.data:
            return []
        
        group_ids = [group["id"] for group in groups_response.data]
        
        # Check existing memberships in these groups
        memberships_response = supabase.table("Group_Members").select("group_id").eq("user_id", user_id).eq("is_active", True).in_("group_id", group_ids).execute()
        existing_group_ids = {member["group_id"] for member in memberships_response.data}
        
        # Filter out groups where user is already a member
        available_groups = [group for group in groups_response.data if group["id"] not in existing_group_ids]
        
        # Return up to 5 groups
        return available_groups[:5]
    except Exception as e:
        print(f"An error occurred: {e}")
        return []


def request_to_join_group_service(user_id: int, username: str, group_name: str):
    try:
        # Fetch group_id of the group_name
        group = supabase.table("Groups").select("id, leader_id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}

        group_id = group.data[0]["id"]
        leader_id = group.data[0]["leader_id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "You are already a member of the group."}

        # Check if the user has already been invited to the group
        existing_invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("is_active", True).execute()
        if existing_invite.data:
            return {"success": False, "message": "You have already been invited to the group."}

        # Create group request
        supabase.table("Group_Requests").insert({
            "group_id": group_id,
            "user_id": user_id,
            "status": "PENDING",
            "is_active": True
        }).execute()

        # Send notification to the group leader
        notification_data = {
            "user_id": leader_id,
            "description": f"{group_name} has a new join request from {username}",
            "type": "GROUP_JOIN_REQUEST",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        return {"success": True, "message": "Join request sent successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}
    

def accept_group_join_request_service(user_id: int, group_name: str, user_name_joining: str):
    try:
        # Fetch group_id and leader_id of the group_name
        group = supabase.table("Groups").select("id, leader_id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}
        
        group_id = group.data[0]["id"]
        leader_id = group.data[0]["leader_id"]

        # Fetch user_id of the user_name_joining
        user = supabase.table("Users").select("id").eq("username", user_name_joining).eq("is_active", True).execute()
        if not user.data:
            return {"success": False, "message": "User not found or inactive."}
        
        user_id_joining = user.data[0]["id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", user_id_joining).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "User is already a member of the group."}

        # Check if the user has been invited to the group
        invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", user_id_joining).eq("status", "PENDING").eq("is_active", True).execute()
        if not invite.data:
            return {"success": False, "message": "No pending join request to the group found."}
        
        invite_id = invite.data[0]["id"]

        # Create group membership record
        supabase.table("Group_Members").insert({
            "group_id": group_id,
            "user_id": user_id_joining,
            "is_active": True
        }).execute()

        # Update group request status to ACCEPTED
        supabase.table("Group_Requests").update({
            "status": "ACCEPTED",
            "is_active": False
        }).eq("id", invite_id).execute()

        # Send notification to the user joining
        notification_data = {
            "user_id": user_id_joining,
            "description": f"Your join request to the group '{group_name}' has been accepted.",
            "type": "GROUP_JOIN_ACCEPTED",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}
        
        # Mark the notification of the group join request as read and inactive
        supabase.table("Notifications").update({
            "read": True,
            "is_active": False
        }).eq("user_id", leader_id).eq("description", f"{group_name} has a new join request from {user_name_joining}").execute()
                
        return {"success": True, "message": f"Group join request accepted from {user_name_joining}."}
    except Exception as e:
        return {"success": False, "message": str(e)}
    

def decline_group_join_request_service(user_id: int, group_name: str, user_name_joining: str):
    try:
        # Fetch group_id and leader_id of the group_name
        group = supabase.table("Groups").select("id, leader_id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}
        
        group_id = group.data[0]["id"]
        leader_id = group.data[0]["leader_id"]

        # Fetch user_id of the user_name_joining
        user = supabase.table("Users").select("id").eq("username", user_name_joining).eq("is_active", True).execute()
        if not user.data:
            return {"success": False, "message": "User not found or inactive."}
        
        user_id_joining = user.data[0]["id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", user_id_joining).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "User is already a member of the group."}

        # Check if the user has been invited to the group
        invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", user_id_joining).eq("status", "PENDING").eq("is_active", True).execute()
        if not invite.data:
            return {"success": False, "message": "No pending join request to the group found."}
        
        invite_id = invite.data[0]["id"]

        # Update group request status to DECLINED
        supabase.table("Group_Requests").update({
            "status": "DECLINED",
            "is_active": False
        }).eq("id", invite_id).execute()

        # Send notification to the user joining
        notification_data = {
            "user_id": user_id_joining,
            "description": f"Your join request to the group '{group_name}' has been declined.",
            "type": "GROUP_JOIN_DECLINED",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}
        
        # Mark the notification of the group join request as read and inactive
        supabase.table("Notifications").update({
            "read": True,
            "is_active": False
        }).eq("user_id", leader_id).eq("description", f"{group_name} has a new join request from {user_name_joining}").execute()
        
        return {"success": True, "message": f"Group join request declined from {user_name_joining}."}
    except Exception as e:
        return {"success": False, "message": str(e)}
    

def send_group_invite_service(user_id: int, request_to_username: str, group_name: str):
    try:
        # Fetch user_id of the request_to_username
        recipient = supabase.table("Users").select("id").eq("username", request_to_username).eq("is_active", True).execute()
        if not recipient.data:
            return {"success": False, "message": "Recipient user not found."}
        request_to_user_id = recipient.data[0]["id"]

        # Fetch group_id of the group_name
        group = supabase.table("Groups").select("id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}
        group_id = group.data[0]["id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", request_to_user_id).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "User is already a member of the group."}

        # Check if the user has already been invited to the group
        existing_invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", request_to_user_id).eq("is_active", True).execute()
        if existing_invite.data:
            return {"success": False, "message": "User has already been invited to the group."}

        # Create group request
        supabase.table("Group_Requests").insert({
            "group_id": group_id,
            "user_id": request_to_user_id,
            "status": "PENDING",
            "is_active": True
        }).execute()

        # Send notification to the recipient
        notification_data = {
            "user_id": request_to_user_id,
            "description": f"You have been invited to join the group '{group_name}'.",
            "type": "GROUP_INVITE",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        return {"success": True, "message": f"Group invite sent to {request_to_username} successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}

    
def accept_group_invite_service(user_id: int, username: str, group_name: str):
    try:
        # Fetch group_id and leader_id of the group_name
        group = supabase.table("Groups").select("id, leader_id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}
        group_id = group.data[0]["id"]
        leader_id = group.data[0]["leader_id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "You are already a member of the group."}

        # Check if the user has been invited to the group
        invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("status", "PENDING").eq("is_active", True).execute()
        if not invite.data:
            return {"success": False, "message": "No pending invite to the group found."}
        invite_id = invite.data[0]["id"]

        # Create group membership record
        supabase.table("Group_Members").insert({
            "group_id": group_id,
            "user_id": user_id,
            "is_active": True
        }).execute()

        # Update group request status to ACCEPTED
        supabase.table("Group_Requests").update({
            "status": "ACCEPTED",
            "is_active": False
        }).eq("id", invite_id).execute()

        # Send notification to the group leader
        notification_data = {
            "user_id": leader_id,
            "description": f"{username} has accepted the invite to join the group '{group_name}'.",
            "type": "GROUP_ACCEPTED",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        # Mark the notification of the group invite as read and inactive
        supabase.table("Notifications").update({
            "read": True, "is_active": False
        }).eq("user_id", user_id).eq("description", f"You have been invited to join the group '{group_name}'.").execute()

        return {"success": True, "message": f"Successfully joined the group '{group_name}'."}
    except Exception as e:
        return {"success": False, "message": str(e)}


def decline_group_invite_service(user_id: int, username: str, group_name: str):
    try:
        # Fetch group_id and leader_id of the group_name
        group = supabase.table("Groups").select("id, leader_id").eq("group_name", group_name).eq("is_active", True).execute()
        if not group.data:
            return {"success": False, "message": "Group not found or inactive."}
        group_id = group.data[0]["id"]
        leader_id = group.data[0]["leader_id"]

        # Check if the user is already a member of the group
        existing_member = supabase.table("Group_Members").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("is_active", True).execute()
        if existing_member.data:
            return {"success": False, "message": "You are already a member of the group."}

        # Check if the user has been invited to the group
        invite = supabase.table("Group_Requests").select("id").eq("group_id", group_id).eq("user_id", user_id).eq("status", "PENDING").eq("is_active", True).execute()
        if not invite.data:
            return {"success": False, "message": "No pending invite to the group found."}
        invite_id = invite.data[0]["id"]

        # Update group request status to DECLINED
        supabase.table("Group_Requests").update({
            "status": "DECLINED",
            "is_active": False
        }).eq("id", invite_id).execute()

        # Send notification to the group leader
        notification_data = {
            "user_id": leader_id,
            "description": f"{username} has declined the invite to join the group '{group_name}'.",
            "type": "GROUP_DECLINED",
            "read": False,
            "is_active": True
        }
        if not _create_notification_utility(notification_data):
            return {"success": False, "message": "Failed to send notification."}

        # Mark the notification of the group invite as read and inactive
        supabase.table("Notifications").update({
            "read": True, "is_active": False
        }).eq("user_id", user_id).eq("description", f"You have been invited to join the group '{group_name}'.").execute()

        return {"success": True, "message": f"Invite to join the group '{group_name}' declined successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}
    

def group_leaderboard_service(user_id: int, group_name: str):
    try:
        # Case-insensitive group search
        group = supabase.table("Groups").select(
            "id, leader_id, group_name, description"
        ).ilike("group_name", group_name).eq("is_active", True).execute()

        if not group.data:
            return {"success": False, "message": "Group not found or inactive"}

        group_data = group.data[0]
        group_id = group_data["id"]
        leader_id = group_data["leader_id"]

        # Single query for leader and members
        members_response = supabase.table("Group_Members").select(
            "user_id, Users(username)"
        ).eq("group_id", group_id).eq("is_active", True).execute()

        member_ids = [m["user_id"] for m in members_response.data]
        leader_data = next((m for m in members_response.data if m["user_id"] == leader_id), None)

        # Single query for all portfolios
        portfolio_response = supabase.table("Portfolio_History").select(
            "user_id, holding_value, unrealised_pnl, cash, timestamp"
        ).in_("user_id", member_ids).eq("is_active", True).order("timestamp", desc=True).execute()

        # Process portfolio data
        portfolio_map = {}
        for entry in portfolio_response.data:
            if entry["user_id"] not in portfolio_map:
                portfolio_map[entry["user_id"]] = {
                    "holding_value": entry["holding_value"],
                    "unrealised_pnl": entry["unrealised_pnl"],
                    "cash": entry["cash"],
                    "timestamp": entry["timestamp"]
                }

        # Build member data
        member_data = []
        for member in members_response.data:
            portfolio = portfolio_map.get(member["user_id"])
            member_data.append({
                "username": member["Users"]["username"],
                "portfolio": portfolio
            })

        return {
            "success": True,
            "group_name": group_data["group_name"],
            "description": group_data["description"],
            "leader": leader_data["Users"]["username"] if leader_data else "Unknown",
            "members": member_data
        }

    except Exception as e:
        return {"success": False, "message": str(e)}

    
async def friend_summary_service(user_id: int, friend_username: str):
    try:
        # Fetch user_id of the friend_username
        friend = supabase.table("Users").select("id").eq("username", friend_username).eq("is_active", True).execute()
        if not friend.data:
            return {"success": False, "message": "Friend user not found."}
        friend_to_user_id = friend.data[0]["id"]


        # Fetch the friend's transactions
        transactions = supabase.table("Transactions").select(
            "id", "stock_ticker", "direction", "quantity", "execution_price", "transaction_fee", "created_at"
        ).eq("user_id", friend_to_user_id).eq("is_active", True).execute()
        txs = transactions.data if transactions and transactions.data else []

        # Fetch the friend's portfolio history
        portfolio = supabase.table("Portfolio_History").select(
            "holding_value", "unrealised_pnl", "cash", "timestamp"
        ).eq("user_id", friend_to_user_id).eq("is_active", True).order("timestamp", desc=True).limit(1).execute()
        portfolio_record = None
        if portfolio.data:
            portfolio_record = {
                "holding_value": portfolio.data[0]["holding_value"],
                "unrealised_pnl": portfolio.data[0]["unrealised_pnl"],
                "cash": portfolio.data[0]["cash"],
                "timestamp": portfolio.data[0]["timestamp"]
            }

        # Calculate the total portfolio value for the friend
        total_portfolio_value = 0.0
        if portfolio_record:
            total_portfolio_value = portfolio_record["holding_value"] + portfolio_record["cash"]
        
        # Call the user_trade_summary_service to get the trade summary for the friend
        trade_summary = await user_trade_summary_service(friend_to_user_id)

        return {
            "success": True,
            "friend_username": friend_username,
            "portfolio": portfolio_record,
            "transactions": txs,
            "current_cash": portfolio_record["cash"],
            "total_portfolio_value": total_portfolio_value,
            "total_unrealised_pnl": portfolio_record["unrealised_pnl"],
            "trade_summary": trade_summary
        }

    except Exception as e:
        raise e
    

def calculate_final_risk_score(user_id: int) -> int:
    """
    Calculates the user's total risk score by summing up (question_weight * answer_weight) for each active answer in the User_Risk_Profile_Answers table.
    """
    try:
        response = supabase.table("User_Risk_Profile_Answers").select("*, question:Risk_Profile_Questions(*), answer:Risk_Profile_Answers(*)").eq("user_id", user_id).eq("is_active", True).execute()

        if not response:
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving user risk profile data"
            )

        rows = response.data
        total_score = 0.0

        for row in rows:
            question_weight = row["question"].get("weight") or 0
            answer_weight = row["answer"].get("weight") or 0
            total_score += float(question_weight) * float(answer_weight)

        total_score = total_score * 100

        if(total_score > 75):
            risk_category = "High"
        elif (total_score > 50):
            risk_category = "Moderate"
        elif (total_score > 25):
            risk_category = "Low"
        else:
            risk_category = "Very Low"
    
        return {"risk_score": int(total_score), "risk_category": risk_category}
    
    except Exception as e:
        return {"success": False, "message": str(e)}

    
def submit_user_risk_profile_service(user_id: int, questionnaire_result: List[Dict]):
    try:
        data_to_upsert = []
        for item in questionnaire_result:
            question_id = item.get("question_id")
            answer_id = item.get("answer_id")

            if not question_id or not answer_id:
                continue
            
            data_to_upsert.append({
                "user_id": user_id,
                "question_id": question_id,
                "answer_id": answer_id,
                "is_active": True 
            })

        if not data_to_upsert:
            raise HTTPException(
                    status_code=400,
                    detail="Nothing to update"
                )
                
        # Perform upsert: - on_conflict=["user_id","question_id"] means if a row already exists with the same user_id and question_id, it will be updated with the new answer_id.
        supabase.table("User_Risk_Profile_Answers").upsert(data_to_upsert, on_conflict="user_id, question_id").execute()

        risk_score = calculate_final_risk_score(user_id)["risk_score"]
        risk_category = calculate_final_risk_score(user_id)["risk_category"]

        return {
            "success": True,
            "risk_score": risk_score,
            "risk_category": risk_category,
            "message": "User risk profile updated successfully."
        }
    
    except Exception as e:
        return {"success": False, "message": str(e)}