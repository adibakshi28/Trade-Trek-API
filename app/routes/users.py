# app/routes/users.py

from fastapi import APIRouter, Depends
from typing import List, Dict, Optional

from app.middlewares.jwt_auth import require_active_session
from app.services.user_service import user_transactions_service, user_funds_service, user_info_service, user_portfolio_service, user_trade_summary_service, get_user_watchlist_service, add_to_user_watchlist_service, remove_from_user_watchlist_service, user_portfolio_history_service, notification_service, mark_notification_read_service, get_user_friends_service, send_friend_request_service, accept_friend_request_service, decline_friend_request_service, create_group_service, send_group_invite_service, accept_group_invite_service, decline_group_invite_service, group_info_service, group_leaderboard_service, friend_summary_service, get_all_groups_for_user_service, user_group_search_to_add_service, user_friend_search_to_add_service, user_group_search_to_join_service, request_to_join_group_service, accept_group_join_request_service, decline_group_join_request_service
from app.services.calculation_service import calculate_metrics_service

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
async def get_user_portfolio(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Return all user transactions
    """
    user_id = payload.get("user_id")
    portfolio = await user_portfolio_service(user_id)
    return portfolio

@router.get("/portfolio/history")
async def get_user_portfolio_history(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns user portfolio history (Holding value, Unrealised P&L, Cash balance and Index value)
    """
    user_id = payload.get("user_id")
    portfolio = user_portfolio_history_service(user_id)
    return portfolio

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
    """
    user_id = payload.get("user_id")
    summary = await user_trade_summary_service(user_id)
    return summary


@router.get("/dashboard")
async def get_user_dashboard(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns the integrated infor required for the user dashboard
    """
    user_id = payload.get("user_id")
    portfolio = await user_portfolio_service(user_id)
    funds = user_funds_service(user_id)
    response = {
        "portfolio": portfolio,
        "funds": funds,
    }
    return response

@router.get("/watchlist")
async def get_user_watchlist(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Returns the users watchlist
    """
    user_id = payload.get("user_id")
    response = await get_user_watchlist_service(user_id)
    return response

@router.get("/watchlist/add")
async def add_to_user_watchlist(ticker: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Adds a stock to the users watchlist
    """
    user_id = payload.get("user_id")
    response = await add_to_user_watchlist_service(user_id, ticker)
    return response

@router.get("/watchlist/remove")
async def remove_from_user_watchlist(ticker: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Removes a stock from the users watchlist
    """
    user_id = payload.get("user_id")
    response = await remove_from_user_watchlist_service(user_id , ticker)
    return response

@router.get("/notifications")
def get_user_notification(payload: dict = Depends(require_active_session)) -> Dict:
    """
    Returns the users notifications
    """
    user_id = payload.get("user_id")
    response = notification_service(user_id)
    return response


@router.get("/notifications/read")
def mark_notification_read(notification_id: int, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Marks a notification as read
    """
    user_id = payload.get("user_id")
    response = mark_notification_read_service(user_id , notification_id)
    return response


@router.get("/friend")
def get_user_friends(payload: dict = Depends(require_active_session)) -> List[Dict]:
    """
    Returns the users friends
    """
    user_id = payload.get("user_id")
    response = get_user_friends_service(user_id)
    return response


@router.get("/friend/search/to-add")
def user_friend_search_to_add(user_name_str: str, payload: dict = Depends(require_active_session)):
    """
    Search for users to add as friendb (Only returns users who are not already friends)
    """
    user_id = payload.get("user_id")
    response = user_friend_search_to_add_service(user_id, user_name_str)
    return response


@router.get("/friend/request/send")
def send_friend_request(request_to_username: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Send a friend request to a user
    """
    user_id = payload.get("user_id")
    response = send_friend_request_service(user_id, request_to_username)
    return response


@router.get("/friend/request/accept")
def accept_friend_request(accepted_username: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Accept user friend request
    """
    user_id = payload.get("user_id")
    response = accept_friend_request_service(user_id, accepted_username)
    return response


@router.get("/friend/request/decline")
def decline_friend_request(declined_username: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Decline user friend request
    """
    user_id = payload.get("user_id")
    response = decline_friend_request_service(user_id, declined_username)
    return response


@router.get("/friend/summary")
async def friend_summary(friend_username: str, payload: dict = Depends(require_active_session)):
    """
    Get friend activity and portfolio summary
    """
    user_id = payload.get("user_id")
    response = await friend_summary_service(user_id, friend_username)
    return response

@router.get("/group")
def get_all_groups_for_user(payload: dict = Depends(require_active_session)):
    """
    Get all groups for whcih user is a member
    """
    user_id = payload.get("user_id")
    response = get_all_groups_for_user_service(user_id)
    return response

@router.post("/group/create")
def create_group(group_name: str, group_description: Optional[str], payload: dict = Depends(require_active_session)):
    """
    Create a group
    """
    user_id = payload.get("user_id")
    response = create_group_service(user_id, group_name, group_description)
    return response


@router.post("/group/info")
def group_info(group_name: str, payload: dict = Depends(require_active_session)):
    """
    Get group information
    """
    user_id = payload.get("user_id")
    response = group_info_service(user_id, group_name)
    return response

@router.get("/group/search/to-add")
def user_group_search_to_add(group_name: str, user_name_str: str, payload: dict = Depends(require_active_session)):
    """
    Search for users to add to the given group_name (Only returns users who are not already in the group)
    """
    user_id = payload.get("user_id")
    response = user_group_search_to_add_service(user_id, user_name_str, group_name)
    return response

@router.get("/group/search/to-join")
def user_group_search_to_join(group_name_str: str, payload: dict = Depends(require_active_session)):
    """
    Search for group name from part string group_name_str (Only returns groups that the user is not a memeber of)
    """
    user_id = payload.get("user_id")
    response = user_group_search_to_join_service(user_id, group_name_str)
    return response


@router.get("/group/request/join")
def request_to_join_group(group_name: str, payload: dict = Depends(require_active_session)):
    """
    Resquest to join a group by group_name
    """
    user_id = payload.get("user_id")
    username = payload.get("username")
    response = request_to_join_group_service(user_id, username, group_name)
    return response


@router.get("/group/request/join/accept")
def accept_group_join_request(group_name: str, user_name_joining: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Accept group join request
    """
    user_id = payload.get("user_id")
    response = accept_group_join_request_service(user_id, group_name, user_name_joining)
    return response


@router.get("/group/request/join/decline")
def decline_group_join_request(group_name: str, user_name_joining: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Decline group join request
    """
    user_id = payload.get("user_id")
    response = decline_group_join_request_service(user_id, group_name, user_name_joining)
    return response


@router.get("/group/request/invite")
def send_group_invite(request_to_username: str, group_name: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Send a group invite to a user
    """
    user_id = payload.get("user_id")
    response = send_group_invite_service(user_id, request_to_username, group_name)
    return response


@router.get("/group/request/accept")
def accept_group_invite(group_name: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Accept group invite by group_name
    """
    user_id = payload.get("user_id")
    username = payload.get("username")
    response = accept_group_invite_service(user_id, username, group_name)
    return response


@router.get("/group/request/decline")
def decline_group_invite(group_name: str, payload: dict = Depends(require_active_session)) -> Dict:
    """
    Decline group invite by group_name
    """
    user_id = payload.get("user_id")
    username = payload.get("username")
    response = decline_group_invite_service(user_id, username, group_name)
    return response


@router.get("/group/leaderboard")
def group_leaderboard(group_name: str, payload: dict = Depends(require_active_session)):
    """
    Get group leaderboard by group_name
    """
    user_id = payload.get("user_id")
    response = group_leaderboard_service(user_id, group_name)
    return response


@router.post("/metrics")
async def calculate_metrics(metric_config: dict, payload: dict = Depends(require_active_session)):
    """
    Calculate user portfolio metrics
    """
    user_id = payload.get("user_id")
    response = await calculate_metrics_service(user_id, metric_config)
    return response