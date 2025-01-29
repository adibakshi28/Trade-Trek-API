import math
import datetime
import numpy as np
import pandas as pd
# import cvxpy as cp
from typing import List, Dict, Any
from postgrest import APIError

from app.models.database import supabase
from app.core.config import config
from app.models.sqlite_cache import execute_sql
from app.services.data_service import stock_historical_service

def _parse_date(date_str: str) -> datetime.datetime:
    return datetime.datetime.strptime(date_str, "%Y-%m-%d")

def clean_for_json(obj):
    """
    Recursively convert NaN or infinite floats to None in a nested dict/list structure.
    """
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        else:
            return obj
    else:
        return obj

def calculate_daily_returns(
    historical_data: List[Dict[str, Any]], return_type: str = "arithmetic"
) -> pd.Series:
    """
    Converts the historical price data to daily returns.
    `historical_data` is a list of dictionaries with at least 'datetime' and 'close'.
    `return_type`: 'arithmetic' or 'geometric'
    """
    if not historical_data:
        return pd.Series(dtype=float)

    df = pd.DataFrame(historical_data)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.sort_values("datetime", inplace=True)
    df.set_index("datetime", inplace=True)

    df["price"] = df["close"]
    df["price_shifted"] = df["price"].shift(1)

    if return_type == "arithmetic":
        df["returns"] = df["price"] / df["price_shifted"] - 1.0
    else:
        # geometric or log-return
        df["returns"] = np.log(df["price"] / df["price_shifted"])

    df.dropna(subset=["returns"], inplace=True)
    return df["returns"]

def compute_portfolio_returns(
    portfolio: List[Dict[str, Any]],
    ticker_returns: Dict[str, pd.Series]
) -> pd.Series:
    """
    Computes a single daily return series for the overall portfolio based on 
    static weights from each holding's initial notional value (quantity * execution_price).

    :param portfolio: List of holdings, each with:
        - stock_ticker
        - quantity
        - execution_price
    :param ticker_returns: Dict of {ticker: pd.Series of daily returns}, 
                           indices = dates
    :return: pd.Series of portfolio-level daily returns indexed by date.
    """
    if not portfolio:
        return pd.Series(dtype=float)

    # 1) Compute total initial notional for each ticker
    # (We assume "execution_price" is the cost basis or initial price)
    df_port = pd.DataFrame(portfolio)
    df_port["notional"] = df_port["quantity"] * df_port["execution_price"]
    total_notional = df_port["notional"].sum()
    if total_notional <= 0:
        return pd.Series(dtype=float)

    # 2) Compute each ticker's weight in the portfolio
    df_port["weight"] = df_port["notional"] / total_notional

    # 3) Construct a combined date index from all ticker returns
    all_dates = pd.Index([])
    for tkr in ticker_returns:
        all_dates = all_dates.union(ticker_returns[tkr].index)

    all_dates = all_dates.sort_values()

    # 4) For each date, sum(weight * that ticker's return)
    portfolio_ret = []
    for dt in all_dates:
        daily_sum = 0.0
        for _, row in df_port.iterrows():
            tkr = row["stock_ticker"]
            wgt = row["weight"]
            if dt in ticker_returns[tkr].index:
                daily_sum += wgt * ticker_returns[tkr].loc[dt]
        portfolio_ret.append(daily_sum)

    portfolio_series = pd.Series(data=portfolio_ret, index=all_dates, name="portfolio_returns")
    return portfolio_series

def calculate_rolling_std(returns: pd.Series, window: int) -> float:
    """
    Rolling standard deviation over the entire series (last value in the rolling window).
    """
    if returns.empty:
        return float("nan")
    rolling_stds = returns.rolling(window=window).std()
    return rolling_stds.dropna().iloc[-1] if not rolling_stds.dropna().empty else float("nan")

def _compute_rolling_std_series(returns: pd.Series, window: int) -> pd.Series:
    """
    Returns the rolling standard deviation time series, for each date (past 'window'),
    we compute std of the prior 'window' returns.
    """
    if returns.empty or len(returns) < window:
        return pd.Series(dtype=float)
    return returns.rolling(window=window).std()

def calculate_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Simple beta calculation using covariance/variance.
    """
    if stock_returns.empty or benchmark_returns.empty:
        return float("nan")
    cov = np.cov(stock_returns, benchmark_returns)[0, 1]
    var = np.var(benchmark_returns)
    if var == 0:
        return float("nan")
    return cov / var

def calculate_var_es(
    returns: pd.Series, confidence_level: float = 0.95
) -> Dict[str, float]:
    """
    Naive historical VaR/ES estimation.
    """
    if returns.empty:
        return {"var": float("nan"), "es": float("nan")}
    sorted_returns = returns.sort_values()
    index = int((1 - confidence_level) * len(sorted_returns))
    if index < 0 or index >= len(sorted_returns):
        return {"var": float("nan"), "es": float("nan")}

    var_value = sorted_returns.iloc[index]
    es_value = sorted_returns.iloc[: index + 1].mean()
    return {"var": var_value, "es": es_value}

def _compute_rolling_var_es_series(
    returns: pd.Series, window: int, confidence_level: float = 0.95
) -> pd.DataFrame:
    """
    Computes rolling VaR & ES time series over a specified window.
    Returns a DataFrame with columns ["var", "es"] indexed by date.
    """
    records = []
    if returns.empty or len(returns) < window:
        return pd.DataFrame(columns=["var", "es"], dtype=float)

    sorted_index = returns.sort_index().index 
    for i in range(window, len(sorted_index) + 1):
        window_slice = returns.loc[sorted_index[i - window : i - 1]]
        var_es_result = calculate_var_es(window_slice, confidence_level=confidence_level)
        date_label = sorted_index[i - 1] 
        records.append({
            "date": date_label,
            "var": var_es_result["var"],
            "es": var_es_result["es"]
        })

    df_out = pd.DataFrame(records)
    df_out.set_index("date", inplace=True)
    return df_out

def calculate_skew_kurt(returns: pd.Series) -> Dict[str, float]:
    """Skewness & Kurtosis."""
    return {
        "skewness": returns.skew() if not returns.empty else float("nan"),
        "kurtosis": returns.kurt() if not returns.empty else float("nan"),
    }

def calculate_drawdowns(returns: pd.Series) -> Dict[str, float]:
    """
    Calculates drawdown metrics: Maximum Drawdown (mdd), Average Drawdown, and Recovery Time.

    Recovery Time is measured in days if the index is a DatetimeIndex,
    otherwise in 'periods' for integer-based or other indices.
    """
    if returns.empty:
        return {
            "mdd": float("nan"),
            "average_drawdown": float("nan"),
            "recovery_time": float("nan"),
        }

    cum_returns = (1 + returns).cumprod()
    peak = cum_returns.cummax()
    drawdown = (cum_returns - peak) / peak

    mdd = drawdown.min()
    avg_dd = drawdown.mean()

    i_dd = drawdown.idxmin()
    peak_value = peak.loc[i_dd]

    post_drawdown = cum_returns.loc[i_dd:]
    recovered_mask = post_drawdown >= peak_value

    if recovered_mask.any():
        recovery_date = recovered_mask.idxmax()

        if (isinstance(cum_returns.index, pd.DatetimeIndex) 
                and isinstance(i_dd, pd.Timestamp)
                and isinstance(recovery_date, pd.Timestamp)):
            recovery_time = (recovery_date - i_dd).days
        else:
            i_dd_pos = cum_returns.index.get_loc(i_dd)
            recovery_date_pos = cum_returns.index.get_loc(recovery_date)
            recovery_time = recovery_date_pos - i_dd_pos
    else:
        recovery_time = float("nan")

    return {
        "mdd": mdd,
        "average_drawdown": avg_dd,
        "recovery_time": recovery_time,
    }

def _compute_rolling_mdd_series(returns: pd.Series, window: int) -> pd.Series:
    """
    Computes a trailing (rolling) Max Drawdown over 'window' bars/days.
    Returns a Series with NaN for the first (window-1) periods.
    """
    def rolling_mdd(subseries: pd.Series) -> float:
        if subseries.empty:
            return float("nan")
        cum_r = (1 + subseries).cumprod()
        peaks = cum_r.cummax()
        drawdown = (cum_r - peaks) / peaks
        return drawdown.min() if not drawdown.empty else float("nan")

    return returns.rolling(window=window).apply(rolling_mdd, raw=False)


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.03,
    freq: str = "daily"
) -> float:
    """
    Computes a simple annualized Sharpe ratio.
    """
    if returns.empty:
        return float("nan")

    if freq == "daily":
        rf_daily = (1 + risk_free_rate) ** (1 / 252) - 1
    elif freq == "monthly":
        rf_daily = (1 + risk_free_rate) ** (1 / 12) - 1
    else:
        rf_daily = risk_free_rate

    excess_returns = returns - rf_daily
    avg_excess = excess_returns.mean()
    std_excess = excess_returns.std()

    if std_excess == 0:
        return float("nan")

    sharpe_daily = avg_excess / std_excess
    sharpe_annualized = sharpe_daily * np.sqrt(252)
    return sharpe_annualized


def _subset_by_period(returns: pd.Series, period_str: str) -> pd.Series:
    """
    Subset the returns Series to the last X years/months/weeks, etc.
    E.g. "1Y" -> last 365 days, "3Y" -> last ~1095 days, etc.
    You can expand logic for "6M", "1W", etc. as needed.
    """
    if returns.empty:
        return returns

    if not isinstance(returns.index, pd.DatetimeIndex):
        # If there's no DatetimeIndex, we can't do a date-based subset
        return returns

    end_date = returns.index.max()
    if period_str.endswith("Y"):
        # e.g. "1Y", "3Y"
        num_years = int(period_str.replace("Y", ""))
        start_date = end_date - pd.DateOffset(years=num_years)
    elif period_str.endswith("M"):
        # e.g. "6M"
        num_months = int(period_str.replace("M", ""))
        start_date = end_date - pd.DateOffset(months=num_months)
    elif period_str.endswith("W"):
        # e.g. "1W"
        num_weeks = int(period_str.replace("W", ""))
        start_date = end_date - pd.DateOffset(weeks=num_weeks)
    else:
        # Unrecognized; default to entire range
        return returns

    return returns.loc[(returns.index >= start_date) & (returns.index <= end_date)]


def _compute_rolling_sharpe_ratio(
    returns: pd.Series, risk_free_rate: float = 0.03, window: int = 30
) -> pd.Series:
    """
    Compute a rolling Sharpe ratio over 'window' periods, assuming daily frequency.
    Returns a Series with the same index (NaN until the window is full).
    """
    if returns.empty or len(returns) < window:
        return pd.Series(dtype=float)

    # Precompute daily risk-free (assuming ~252 trading days)
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

    def rolling_sharpe(sub_ret: pd.Series) -> float:
        # sub_ret is the last 'window' returns
        if sub_ret.empty:
            return float("nan")
        # Excess returns
        ex_ret = sub_ret - daily_rf
        if ex_ret.std() == 0:
            return float("nan")
        # Annualize
        sr_daily = ex_ret.mean() / ex_ret.std()
        sr_annual = sr_daily * np.sqrt(252)
        return sr_annual

    return returns.rolling(window=window).apply(rolling_sharpe, raw=False)


def calculate_distribution_metrics(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes sector distribution and HHI using quantity * execution_price as weighting.
    """
    if not portfolio:
        return {"sector_distribution": {}, "hhi": float("nan")}

    df = pd.DataFrame(portfolio)
    if "execution_price" in df.columns:
        df["value"] = df["quantity"] * df["execution_price"]
    else:
        df["value"] = df["quantity"] * df.get("price", 1.0)

    total = df["value"].sum()
    if total == 0:
        return {"sector_distribution": {}, "hhi": float("nan")}

    sector_weights = df.groupby("stock_name")["value"].sum() / total
    hhi_value = np.sum(sector_weights ** 2)

    return {
        "sector_distribution": sector_weights.to_dict(),
        "hhi": hhi_value,
    }

# def portfolio_optimization(
#     returns_df: pd.DataFrame,
#     config_section: dict
# ) -> dict:
#     """
#     Performs basic portfolio optimization with the following goals:
#       - "min_variance": minimize w^T Sigma w
#       - "maximize_return": maximize w^T mu

#     SUBJECT TO:
#       - sum(w) = 1
#       - w_i in [min_allocation, max_allocation]
#       - optional target_volatility (annual)
#       - optional min_return_constraint (annual)
#       - optional transaction costs (simply reduce mu)

#     :param returns_df: DataFrame of historical returns, shape (time, tickers)
#     :param config_section: config dict with fields like:
#       {
#         "goal": "min_variance" or "maximize_return",
#         "constraints": {
#           "min_allocation": 0.05,
#           "max_allocation": 0.50
#         },
#         "target_volatility": 0.2,
#         "min_return_constraint": 0.1,
#         "include_transaction_costs": true,
#         "transaction_costs": 0.01,
#         "rebalance_frequency": "monthly",
#         "risk_free_rate": 0.03
#       }
#     :return: dict with keys:
#       - "optimal_allocation": {ticker: weight, ...}
#       - "objective_value": float (variance or return, depending on goal)
#       - "goal": str (the selected optimization goal)
#       - "rebalance_frequency": str
#       - "note_on_transaction_costs": str
#     """
#     if returns_df.empty:
#         raise ValueError("No historical returns data provided for optimization.")

#     # 1) Clean the data: drop columns with all NaNs or zero variance
#     returns_df = returns_df.dropna(axis=1, how="all")
#     zero_var_cols = [c for c in returns_df.columns if returns_df[c].std() == 0]
#     returns_df = returns_df.drop(columns=zero_var_cols, errors="ignore")
#     if returns_df.empty:
#         raise ValueError("After dropping empty/zero-variance assets, no data left for optimization.")

#     # 2) Compute daily means & covariance
#     daily_means_pd = returns_df.mean()
#     cov_matrix_pd = returns_df.cov()
#     tickers = returns_df.columns.tolist()

#     mu = daily_means_pd.values  # shape (n,)
#     Sigma = cov_matrix_pd.values # shape (n,n)
#     n = len(mu)

#     # 3) Transaction costs (naive approach)
#     note_on_tc = "No transaction cost applied."
#     if config_section.get("include_transaction_costs", False):
#         tc = config_section.get("transaction_costs", 0.0)
#         if tc > 0:
#             # approximate daily cost
#             daily_tc = (1 + tc)**(1/252) - 1
#             mu = mu - daily_tc
#             note_on_tc = (
#                 f"Transaction costs of {tc*100:.2f}% included. "
#                 f"Approximated as daily deduction of {daily_tc*100:.4f}% from returns."
#             )

#     # 4) Constraints
#     min_alloc = config_section["constraints"].get("min_allocation", 0.0)
#     max_alloc = config_section["constraints"].get("max_allocation", 1.0)

#     # target_volatility -> daily
#     target_vol = None
#     if "target_volatility" in config_section:
#         annual_vol = config_section["target_volatility"]
#         target_vol = annual_vol / np.sqrt(252)

#     # min_return_constraint -> daily
#     min_ret = None
#     if "min_return_constraint" in config_section:
#         annual_req = config_section["min_return_constraint"]
#         min_ret = (1 + annual_req)**(1/252) - 1

#     rebalance_freq = config_section.get("rebalance_frequency", "N/A")
#     goal = config_section.get("goal", "min_variance")

#     # 5) Setup CVX variables & constraints
#     w = cp.Variable(n)
#     constraints = [cp.sum(w) == 1, w >= min_alloc, w <= max_alloc]

#     if target_vol is not None:
#         constraints.append(cp.quad_form(w, Sigma) <= target_vol**2)
#     if min_ret is not None:
#         constraints.append(w @ mu >= min_ret)

#     # 6) Objective
#     if goal == "min_variance":
#         objective = cp.Minimize(cp.quad_form(w, Sigma))
#     elif goal == "maximize_return":
#         objective = cp.Maximize(mu @ w)
#     else:
#         # If user tries a goal that's not supported, raise error
#         raise ValueError(
#             f"Unsupported optimization goal '{goal}'. "
#             f"Use 'min_variance' or 'maximize_return' instead."
#         )

#     # 7) Solve
#     problem = cp.Problem(objective, constraints)
#     result = problem.solve()

#     if w.value is None:
#         raise ValueError("No feasible solution found for the optimization problem.")

#     # 8) Prepare final result
#     w_val = w.value.round(4)
#     final_allocation = {tickers[i]: float(w_val[i]) for i in range(n)}

#     return {
#         "optimal_allocation": final_allocation,
#         "objective_value": float(result),
#         "goal": goal,
#         "rebalance_frequency": rebalance_freq,
#         "note_on_transaction_costs": note_on_tc
#     }


# -------------------------------------------------------------------------
# Main service function
# -------------------------------------------------------------------------
async def calculate_metrics_service(user_id: int, metric_config: Dict) -> Dict:
    """
    Main function to:
    1. Fetch user portfolio
    2. Fetch sector data
    3. Fetch historical prices
    4. Calculate per-ticker and portfolio-level metrics (incl time series).
    """
    try:
        # 1. Fetch user portfolio
        portfolio = supabase.table("Holdings") \
                            .select("stock_ticker", "direction", "quantity", "execution_price") \
                            .eq("user_id", user_id) \
                            .eq("is_active", True) \
                            .execute()

        portfolio = portfolio.data or []
        if not portfolio:
            return {"message": "No active holdings found", "portfolio": []}

        unique_tickers = list({p["stock_ticker"] for p in portfolio})

        # 2. Fetch sector (stock_name) data
        STOCK_UNIVERSE_CACHE_TABLE = config.get("STOCK_UNIVERSE_CACHE_TABLE")
        placeholders = ", ".join(["?"] * len(unique_tickers))

        query = f"""
            SELECT stock_ticker, sector
            FROM {STOCK_UNIVERSE_CACHE_TABLE}
            WHERE stock_ticker IN ({placeholders});
        """
        params = tuple(unique_tickers)
        stock_results = await execute_sql(query, params)
        stock_sector_lookup = {row[0]: row[1] for row in stock_results}

        for p in portfolio:
            p["stock_name"] = stock_sector_lookup.get(p["stock_ticker"], "Unknown Sector")
            if p["direction"] == "SELL":
                p['direction'] = 'SHORT'
            elif p["direction"] == "BUY":
                p['direction'] = 'LONG'

        # 3. Fetch historical data for each ticker
        start_date = metric_config.get("timeframe", {}).get("start_date")
        end_date = metric_config.get("timeframe", {}).get("end_date")
        resolution = metric_config.get("resolution", "1day")

        historical = {}
        for stock in portfolio:
            tkr = stock["stock_ticker"]
            data = await stock_historical_service(tkr, start_date, end_date, resolution)
            historical[tkr] = data

        # 4. Prepare results dict
        results = {
            "metrics": {}
        }

        if metric_config["settings"].get("include_portfolio", True):
            results["portfolio"] = portfolio

        # 5. Benchmark data
        benchmark_ticker = metric_config.get("benchmark", "SPY")
        benchmark_data = await stock_historical_service(benchmark_ticker, start_date, end_date, resolution)
        return_type = metric_config["settings"].get("return_type", "arithmetic")
        benchmark_returns = calculate_daily_returns(benchmark_data, return_type=return_type)

        # Convert all tickers to daily returns
        ticker_returns = {}
        for t in unique_tickers:
            ticker_returns[t] = calculate_daily_returns(historical[t], return_type=return_type)

        # ----------- Compute portfolio-level returns -------------
        portfolio_returns = compute_portfolio_returns(portfolio, ticker_returns)

        # --------------------------------------------------------------------------------
        # 5A. Volatility Measures (both per-ticker and portfolio-level)
        # --------------------------------------------------------------------------------
        vol_config = metric_config["metrics"].get("volatility_measures", {})
        if vol_config.get("enable"):
            vol_results = {}
            measures = vol_config.get("measures", [])
            rolling_window = vol_config.get("rolling_window", 30)
            conf_level = vol_config.get("var_es_settings", {}).get("confidence_level", 0.95)
            ts_list = vol_config.get("time_series", [])  # e.g. ["standard_deviation", "var", "es"]

            # Per-ticker results
            ticker_vols = {}
            for ticker in unique_tickers:
                r_series = ticker_returns[ticker]
                result_for_ticker = {}

                if "standard_deviation" in measures:
                    std_val = calculate_rolling_std(r_series, rolling_window)
                    result_for_ticker["standard_deviation"] = std_val

                if "beta" in measures and not benchmark_returns.empty:
                    b_val = calculate_beta(r_series.dropna(), benchmark_returns.dropna())
                    result_for_ticker["beta"] = b_val

                if ("var" in measures) or ("es" in measures):
                    var_es_result = calculate_var_es(r_series.dropna(), confidence_level=conf_level)
                    if "var" in measures:
                        result_for_ticker["var"] = var_es_result["var"]
                    if "es" in measures:
                        result_for_ticker["es"] = var_es_result["es"]

                ticker_vols[ticker] = result_for_ticker

            vol_results["per_ticker"] = ticker_vols

            # ------ Portfolio-Level Volatility Measures ---------
            portfolio_vol_info = {}
            if "standard_deviation" in measures:
                portfolio_vol_info["standard_deviation"] = calculate_rolling_std(portfolio_returns, rolling_window)
            if "beta" in measures and not benchmark_returns.empty:
                portfolio_vol_info["beta"] = calculate_beta(portfolio_returns.dropna(), benchmark_returns.dropna())
            if ("var" in measures) or ("es" in measures):
                port_var_es = calculate_var_es(portfolio_returns.dropna(), confidence_level=conf_level)
                if "var" in measures:
                    portfolio_vol_info["var"] = port_var_es["var"]
                if "es" in measures:
                    portfolio_vol_info["es"] = port_var_es["es"]

            time_series_results = {}
            if "standard_deviation" in ts_list:
                std_series = _compute_rolling_std_series(portfolio_returns, rolling_window)
                time_series_results["standard_deviation"] = std_series.dropna().to_dict()
            if ("var" in ts_list) or ("es" in ts_list):
                var_es_df = _compute_rolling_var_es_series(portfolio_returns, rolling_window, confidence_level=conf_level)
                if "var" in ts_list:
                    time_series_results["var"] = var_es_df["var"].dropna().to_dict()
                if "es" in ts_list:
                    time_series_results["es"] = var_es_df["es"].dropna().to_dict()

            if time_series_results:
                portfolio_vol_info["time_series"] = time_series_results

            vol_results["portfolio"] = portfolio_vol_info

            results["metrics"]["volatility_measures"] = vol_results

        # --------------------------------------------------------------------------------
        # 5B. Correlation & Diversification
        # --------------------------------------------------------------------------------
        corr_config = metric_config["metrics"].get("correlation_diversification", {})
        if corr_config.get("enable"):
            corr_results = {}
            measures = corr_config.get("measures", [])
            correlation_method = corr_config.get("correlation_method", "pearson")
            
            all_idx = pd.Index([])
            for t in unique_tickers:
                all_idx = all_idx.union(ticker_returns[t].index)
            all_idx = all_idx.union(portfolio_returns.index)
            all_idx = all_idx.union(benchmark_returns.index)
            all_idx = all_idx.sort_values()

            df_all = pd.DataFrame(index=all_idx)
            for t in unique_tickers:
                df_all[t] = ticker_returns[t].reindex(all_idx)
            df_all["portfolio"] = portfolio_returns.reindex(all_idx)
            df_all["benchmark"] = benchmark_returns.reindex(all_idx)

            if "correlation_coefficient" in measures:
                corr_matrix = df_all.corr(method=correlation_method)
                corr_results["correlation_matrix"] = corr_matrix.to_dict()

            if "r_squared" in measures:
                if "correlation_matrix" in corr_results:
                    r_matrix = corr_matrix ** 2
                else:
                    r_matrix = df_all.corr(method=correlation_method) ** 2
                corr_results["r_squared_matrix"] = r_matrix.to_dict()

            if "tracking_error" in measures:
                te_vals = {}
                columns_ex_bench = [col for col in df_all.columns if col != "benchmark"]

                for col in columns_ex_bench:
                    diff = df_all[col] - df_all["benchmark"]
                    te_vals[col] = diff.std() * np.sqrt(252)
                corr_results["tracking_error"] = te_vals

            results["metrics"]["correlation_diversification"] = corr_results

        # --------------------------------------------------------------------------------
        # 5C. Drawdown Measures
        # --------------------------------------------------------------------------------
        dd_config = metric_config["metrics"].get("drawdown_measures", {})
        if dd_config.get("enable"):
            dd_results = {}
            measures = dd_config.get("measures", [])
            rolling_window = dd_config.get("rolling_drawdown_window", 30)
            dd_time_series = dd_config.get("time_series", [])

            per_ticker_dd = {}
            for ticker in unique_tickers:
                r_series = ticker_returns[ticker].dropna()
                dd_calc = calculate_drawdowns(r_series)

                dd_dict = {}
                if "mdd" in measures:
                    dd_dict["mdd"] = dd_calc["mdd"]
                if "average_drawdown" in measures:
                    dd_dict["average_drawdown"] = dd_calc["average_drawdown"]
                if "recovery_time" in measures:
                    dd_dict["recovery_time"] = dd_calc["recovery_time"]

                if "mdd" in dd_time_series and not r_series.empty:
                    rolling_mdd_series = _compute_rolling_mdd_series(r_series, rolling_window).dropna()
                    dd_dict["mdd_time_series"] = {
                        str(idx): val for idx, val in rolling_mdd_series.items()
                    }

                per_ticker_dd[ticker] = dd_dict

            port_dd = {}
            portfolio_dd_calc = calculate_drawdowns(portfolio_returns.dropna())
            if "mdd" in measures:
                port_dd["mdd"] = portfolio_dd_calc["mdd"]
            if "average_drawdown" in measures:
                port_dd["average_drawdown"] = portfolio_dd_calc["average_drawdown"]
            if "recovery_time" in measures:
                port_dd["recovery_time"] = portfolio_dd_calc["recovery_time"]

            if "mdd" in dd_time_series and not portfolio_returns.dropna().empty:
                rolling_mdd_series_port = _compute_rolling_mdd_series(portfolio_returns.dropna(), rolling_window).dropna()
                port_dd["mdd_time_series"] = {
                    str(idx): val for idx, val in rolling_mdd_series_port.items()
                }

            dd_results["per_ticker"] = per_ticker_dd
            dd_results["portfolio"] = port_dd

            results["metrics"]["drawdown_measures"] = dd_results


        # --------------------------------------------------------------------------------
        # 5D. Tail Risk
        # --------------------------------------------------------------------------------
        tail_config = metric_config["metrics"].get("tail_risk", {})
        if tail_config.get("enable"):
            tail_results = {}
            measures = tail_config.get("measures", [])

            per_ticker_tail = {}
            for ticker in unique_tickers:
                r_series = ticker_returns[ticker].dropna()
                stats = {}
                if "skewness" in measures or "kurtosis" in measures:
                    skk = calculate_skew_kurt(r_series)
                    if "skewness" in measures:
                        stats["skewness"] = skk["skewness"]
                    if "kurtosis" in measures:
                        stats["kurtosis"] = skk["kurtosis"]
                per_ticker_tail[ticker] = stats

            port_tail_stats = {}
            p_series = portfolio_returns.dropna()
            if "skewness" in measures or "kurtosis" in measures:
                skk_port = calculate_skew_kurt(p_series)
                if "skewness" in measures:
                    port_tail_stats["skewness"] = skk_port["skewness"]
                if "kurtosis" in measures:
                    port_tail_stats["kurtosis"] = skk_port["kurtosis"]

            tail_results["per_ticker"] = per_ticker_tail
            tail_results["portfolio"] = port_tail_stats

            results["metrics"]["tail_risk"] = tail_results

        # --------------------------------------------------------------------------------
        # 5E. Risk-Adjusted Performance
        # --------------------------------------------------------------------------------
        rap_config = metric_config["metrics"].get("risk_adjusted_performance", {})
        if rap_config.get("enable"):
            rap_results = {}
            measures = rap_config.get("measures", [])
            risk_free_rate = rap_config.get("risk_free_rate", 0.03)
            benchmark_for_rap = rap_config.get("benchmark", "SPY")

            comparison_periods = rap_config.get("comparison_periods", [])  
            adjust_benchmark_weights = rap_config.get("adjust_benchmark_weights", False)

            rap_time_series = rap_config.get("time_series", [])  

            benchmark_returns_rap = benchmark_returns

            def information_ratio(asset_returns: pd.Series, bench: pd.Series) -> float:
                if asset_returns.empty or bench.empty:
                    return float("nan")
                active_ret = asset_returns - bench
                if active_ret.std() == 0:
                    return float("nan")
                ir = (active_ret.mean() * 252) / (active_ret.std() * np.sqrt(252))
                return ir

            per_ticker_rap = {}
            portfolio_rap = {}

            for ticker in unique_tickers:
                r_series = ticker_returns[ticker].dropna()
                period_metrics = {}

                for period_str in comparison_periods:
                    sub_r = _subset_by_period(r_series, period_str)
                    if sub_r.empty:
                        period_metrics[period_str] = {m: float("nan") for m in measures}
                    else:
                        temp = {}
                        if "sharpe_ratio" in measures:
                            temp["sharpe_ratio"] = calculate_sharpe_ratio(sub_r, risk_free_rate=risk_free_rate, freq="daily")
                        if "information_ratio" in measures and not benchmark_returns_rap.empty:
                            bench_sub = _subset_by_period(benchmark_returns_rap, period_str)
                            sub_r_aligned = sub_r.reindex(bench_sub.index).dropna()
                            bench_sub_aligned = bench_sub.dropna()
                            if not sub_r_aligned.empty and not bench_sub_aligned.empty:
                                temp["information_ratio"] = information_ratio(sub_r_aligned, bench_sub_aligned)
                            else:
                                temp["information_ratio"] = float("nan")

                        period_metrics[period_str] = temp

                full_period = {}
                if "sharpe_ratio" in measures:
                    full_period["sharpe_ratio"] = calculate_sharpe_ratio(r_series, risk_free_rate=risk_free_rate)
                if "information_ratio" in measures and not benchmark_returns_rap.empty:
                    full_period["information_ratio"] = information_ratio(r_series, benchmark_returns_rap)
                period_metrics["full_period"] = full_period

                if "sharpe_ratio" in rap_time_series and not r_series.empty:
                    rolling_window_sharpe = rap_config.get("rolling_sharpe_window", 30)
                    rolling_sr = _compute_rolling_sharpe_ratio(r_series, risk_free_rate, rolling_window_sharpe).dropna()
                    full_period["sharpe_ratio_time_series"] = {
                        str(idx): val for idx, val in rolling_sr.items()
                    }

                per_ticker_rap[ticker] = period_metrics

            portfolio_rap_data = {}
            port_series = portfolio_returns.dropna()

            for period_str in comparison_periods:
                sub_r = _subset_by_period(port_series, period_str)
                if sub_r.empty:
                    portfolio_rap_data[period_str] = {m: float("nan") for m in measures}
                else:
                    temp = {}
                    if "sharpe_ratio" in measures:
                        temp["sharpe_ratio"] = calculate_sharpe_ratio(sub_r, risk_free_rate=risk_free_rate, freq="daily")
                    if "information_ratio" in measures and not benchmark_returns_rap.empty:
                        bench_sub = _subset_by_period(benchmark_returns_rap, period_str)
                        sub_r_aligned = sub_r.reindex(bench_sub.index).dropna()
                        bench_sub_aligned = bench_sub.dropna()
                        if not sub_r_aligned.empty and not bench_sub_aligned.empty:
                            temp["information_ratio"] = information_ratio(sub_r_aligned, bench_sub_aligned)
                        else:
                            temp["information_ratio"] = float("nan")

                    portfolio_rap_data[period_str] = temp

            full_port_dict = {}
            if "sharpe_ratio" in measures:
                full_port_dict["sharpe_ratio"] = calculate_sharpe_ratio(port_series, risk_free_rate=risk_free_rate)
            if "information_ratio" in measures and not benchmark_returns_rap.empty:
                full_port_dict["information_ratio"] = information_ratio(port_series, benchmark_returns_rap)

            if "sharpe_ratio" in rap_time_series and not port_series.empty:
                rolling_window_sharpe = rap_config.get("rolling_sharpe_window", 30)
                rolling_sr_port = _compute_rolling_sharpe_ratio(port_series, risk_free_rate, rolling_window_sharpe).dropna()
                full_port_dict["sharpe_ratio_time_series"] = {
                    str(idx): val for idx, val in rolling_sr_port.items()
                }

            portfolio_rap_data["full_period"] = full_port_dict

            rap_results["per_ticker"] = per_ticker_rap
            rap_results["portfolio"] = portfolio_rap_data
            rap_results["adjust_benchmark_weights"] = adjust_benchmark_weights 

            results["metrics"]["risk_adjusted_performance"] = rap_results

        # --------------------------------------------------------------------------------
        # 5F. Distribution
        # --------------------------------------------------------------------------------
        dist_config = metric_config["metrics"].get("distribution", {})
        if dist_config.get("enable"):
            dist_measures = dist_config.get("measures", [])
            distribution_results = {}
            if "sector_distribution" in dist_measures or "hhi" in dist_measures:
                distribution_output = calculate_distribution_metrics(portfolio)
                distribution_results["sector_distribution"] = distribution_output["sector_distribution"]
                distribution_results["hhi"] = distribution_output["hhi"]

            results["metrics"]["distribution"] = distribution_results

        # --------------------------------------------------------------------------------
        # 5G. Portfolio Optimization
        # --------------------------------------------------------------------------------
        # opt_config = metric_config["metrics"].get("portfolio_optimization", {})
        # if opt_config.get("enable"):
        #     if not ticker_returns:
        #         results["metrics"]["portfolio_optimization"] = {"error": "No ticker returns available"}
        #     else:
        #         all_idx = pd.Index([])
        #         for t in ticker_returns:
        #             all_idx = all_idx.union(ticker_returns[t].index)
        #         all_idx = all_idx.sort_values()

        #         df_ret = pd.DataFrame(index=all_idx)
        #         for t in ticker_returns:
        #             df_ret[t] = ticker_returns[t].reindex(all_idx)

        #         try:
        #             optimization_output = portfolio_optimization(df_ret, opt_config)
        #             results["metrics"]["portfolio_optimization"] = optimization_output
        #         except ValueError as ve:
        #             results["metrics"]["portfolio_optimization"] = {"error": str(ve)}
        #         except Exception as ex:
        #             raise APIError({"message": f"An error occurred in portfolio optimization: {ex}"})


        # --------------------------------------------------------------------------------
        # 6. Additional Metrics
        # --------------------------------------------------------------------------------
        if metric_config["settings"].get("include_benchmark_trend") and not benchmark_returns.empty:
            results["benchmark_trend"] = benchmark_returns.to_dict()

        results = clean_for_json(results)
        return results

    except APIError as e:
        raise e
    except Exception as err:
        raise APIError(f"An error occurred: {err}")
