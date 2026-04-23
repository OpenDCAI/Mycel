"""Web-owned monitor-local thread routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.identity.auth.user_resolution import get_current_user_id
from backend.monitor.application.use_cases import threads as monitor_thread_service
from backend.monitor.infrastructure.read_models import thread_read_service as monitor_thread_read_service
from backend.monitor.infrastructure.read_models import thread_workbench_read_service as monitor_thread_workbench_read_service
from backend.monitor.infrastructure.read_models import trace_read_service as monitor_trace_read_service

router = APIRouter()


@router.get("/threads")
def threads_snapshot(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    return monitor_thread_service.list_monitor_threads(
        user_id,
        workbench_reader=monitor_thread_workbench_read_service.build_owner_thread_workbench_reader(request.app),
    )


@router.get("/threads/{thread_id}")
async def thread_detail_snapshot(request: Request, thread_id: str):
    try:
        return await monitor_thread_service.get_monitor_thread_detail(
            thread_id,
            load_thread_base=lambda target_thread_id: monitor_thread_read_service.load_monitor_thread_base(request.app, target_thread_id),
            trace_reader=monitor_trace_read_service.build_monitor_trace_reader(request.app),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
