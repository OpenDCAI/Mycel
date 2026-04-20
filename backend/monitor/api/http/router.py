"""Monitor router."""

from fastapi import APIRouter

from backend.monitor.api.http import global_router, web_local_router
from backend.monitor.api.http.dependencies import get_app, get_current_user_id
from backend.monitor.infrastructure.web import gateway as monitor_gateway

__all__ = ["router", "monitor_gateway", "get_app", "get_current_user_id"]

router = APIRouter(prefix="/api/monitor")
# @@@monitor-router-buckets - keep the aggregate import stable while carving route ownership for future monitor_app mounting.
router.include_router(global_router.router)
router.include_router(web_local_router.router)
