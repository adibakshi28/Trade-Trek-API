# app/services/user_service.py

from typing import Optional, List, Dict, Any
from postgrest import APIError

from app.models.database import supabase
from app.utils.finnhub import get_stock_quote

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
    
def user_portfolio_service(user_id: int):
    try:
        response = supabase.table("Holdings").select("id", "user_id", "stock_ticker", "direction", "quantity", "execution_price", "created_at").eq("user_id", user_id).eq("is_active", True).execute()
        return response.data or []
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
        for s, v in pos.items():
            q = v["qty"]
            a = v["avg"]
            r = v["realized"]
            try:
                qt = await get_stock_quote(s)
                cp = round(float(qt["c"]), 2)
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