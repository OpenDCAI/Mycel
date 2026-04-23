"""Runtime/event/task HTTP routes for the threads backend."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.threads.activity_pool_service import get_or_create_agent
from backend.threads.api.http.runtime_support import (
    collect_display_subagent_tasks,
    get_agent_for_thread,
    get_thread_display_entries,
)
from backend.threads.events.buffer import ThreadEventBuffer
from backend.threads.events.store import get_last_seq, get_latest_run_id, get_run_start_seq, read_events_after
from backend.threads.run.buffer_wiring import get_or_create_thread_buffer
from backend.threads.run.observer import observe_thread_events
from backend.threads.runtime_access import get_optional_messaging_service
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from backend.threads.state import get_sandbox_status_from_repos
from backend.web.core.dependencies import (
    _get_thread_repo,
    _get_user_directory,
    get_app,
    get_current_user_id,
    verify_thread_owner,
    verify_thread_row_owner,
)
from core.agents.service import _background_run_cancelled, _background_run_result, request_background_run_stop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads", tags=["threads"])

# SSE response headers: disable proxy buffering for real-time streaming
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@router.get("/{thread_id}/runtime")
async def get_thread_runtime(
    thread_id: str,
    stream: bool = False,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Get runtime status for a thread."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(
        app,
        sandbox_type,
        thread_id=thread_id,
        messaging_service=get_optional_messaging_service(app),
    )
    if not hasattr(agent, "runtime"):
        raise HTTPException(status_code=404, detail="Agent has no runtime monitor")

    last_seq = await get_last_seq(thread_id)
    thread_data = _get_thread_repo(app).get_by_id(thread_id)
    model = thread_data["model"] if thread_data and thread_data.get("model") else None

    status = agent.runtime.get_status_dict()
    if model is not None:
        status["model"] = model
    status["last_seq"] = last_seq
    if status.get("state", {}).get("state") == "active":
        run_id = await get_latest_run_id(thread_id)
        if run_id:
            status["run_start_seq"] = await get_run_start_seq(thread_id, run_id)
    return status


@router.get("/{thread_id}/sandbox")
async def get_thread_sandbox_status(
    thread_id: str,
    user_id: Annotated[str | None, Depends(verify_thread_row_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any] | None:
    """Get sandbox status for a thread."""
    return await get_sandbox_status_from_repos(
        _get_thread_repo(app),
        app.state.workspace_repo,
        app.state.sandbox_repo,
        app.state.sandbox_runtime_repo,
        thread_id,
    )


@router.get("/{thread_id}/events")
async def stream_thread_events(
    thread_id: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    after: int = 0,
    app: Annotated[Any, Depends(get_app)] = None,
) -> EventSourceResponse:
    """Persistent SSE event stream over the standard Authorization header."""
    thread = _get_thread_repo(app).get_by_id(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    agent_user = _get_user_directory(app).get_by_id(thread["agent_user_id"])
    if not agent_user or agent_user.owner_user_id != user_id:
        raise HTTPException(403, "Not authorized")

    last_id = request.headers.get("Last-Event-ID")
    if last_id:
        try:
            after = max(after, int(last_id))
        except ValueError:
            pass

    thread_buf = app.state.thread_event_buffers.get(thread_id)

    if isinstance(thread_buf, ThreadEventBuffer):
        return EventSourceResponse(
            observe_thread_events(thread_buf, after=after),
            headers=SSE_HEADERS,
        )

    thread_buf = get_or_create_thread_buffer(app, thread_id)

    if after > 0:
        run_id = await get_latest_run_id(thread_id)
        if run_id:
            events = await read_events_after(thread_id, run_id, after)
            for ev in events:
                seq = ev.get("seq", 0)
                data_str = ev.get("data", "{}")
                try:
                    data = json.loads(data_str) if isinstance(data_str, str) else data_str
                except (json.JSONDecodeError, TypeError):
                    data = {}
                if isinstance(data, dict):
                    data["_seq"] = seq
                    data_str = json.dumps(data, ensure_ascii=False)
                await thread_buf.put({"event": ev["event"], "data": data_str})

    return EventSourceResponse(
        observe_thread_events(thread_buf, after=after),
        headers=SSE_HEADERS,
    )


@router.post("/{thread_id}/runs/cancel")
async def cancel_run(
    thread_id: str,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
):
    """Cancel an active run for the given thread."""
    task = app.state.thread_tasks.get(thread_id)
    if not task:
        return {"ok": False, "message": "No active run found"}
    task.cancel()
    return {"ok": True, "message": "Run cancellation requested"}


def _get_background_runs(app: Any, thread_id: str) -> dict:
    agent = get_agent_for_thread(app, thread_id)
    return getattr(agent, "_background_runs", {}) if agent else {}


def _background_run_type(run: Any) -> str:
    return "bash" if run.__class__.__name__ == "_BashBackgroundRun" else "agent"


def _serialize_background_run(task_id: str, run: Any, *, include_result: bool) -> dict[str, Any]:
    run_type = _background_run_type(run)
    result_text = _background_run_result(run) if include_result and run.is_done else None
    if _background_run_cancelled(run):
        status = "cancelled"
    else:
        status = "completed" if run.is_done else "running"
    payload = {
        "task_id": task_id,
        "task_type": run_type,
        "status": status,
        "command_line": getattr(run, "command", None) if run_type == "bash" else None,
    }
    if include_result:
        payload["result"] = result_text
        payload["text"] = result_text
        return payload
    payload["description"] = getattr(run, "description", None)
    payload["exit_code"] = getattr(getattr(run, "_cmd", None), "exit_code", None) if run_type == "bash" else None
    payload["error"] = None
    return payload


async def _get_display_task_map(app: Any, thread_id: str) -> dict[str, dict[str, Any]]:
    return collect_display_subagent_tasks(await get_thread_display_entries(app, thread_id))


@router.get("/{thread_id}/tasks")
async def list_tasks(
    thread_id: str,
    request: Request,
) -> list[dict]:
    """List all background runs for a thread."""
    runs = _get_background_runs(request.app, thread_id)
    result = [_serialize_background_run(task_id, run, include_result=False) for task_id, run in runs.items()]
    seen_task_ids = set(runs)
    for task_id, task in (await _get_display_task_map(request.app, thread_id)).items():
        if task_id in seen_task_ids:
            continue
        result.append(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
                "command_line": task["command_line"],
                "description": task["description"],
                "exit_code": task["exit_code"],
                "error": task["error"],
            }
        )
    return result


@router.get("/{thread_id}/tasks/{task_id}")
async def get_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """Get background run details including output."""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        task = (await _get_display_task_map(request.app, thread_id)).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "status": task["status"],
            "command_line": task["command_line"],
            "result": task["result"],
            "text": task["text"],
        }

    return _serialize_background_run(task_id, run, include_result=True)


@router.post("/{thread_id}/tasks/{task_id}/cancel")
async def cancel_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """Cancel a background run."""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        task = (await _get_display_task_map(request.app, thread_id)).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] != "running":
            raise HTTPException(status_code=400, detail="Task is not running")
        thread_task = request.app.state.thread_tasks.get(thread_id)
        if thread_task is None or thread_task.done():
            raise HTTPException(status_code=400, detail="Task is not independently cancellable")
        thread_task.cancel()
        return {"ok": True, "message": "Run cancellation requested", "task_id": task_id}
    if run.is_done:
        raise HTTPException(status_code=400, detail="Task is not running")

    await request_background_run_stop(run)
    asyncio.create_task(_notify_task_cancelled(request.app, thread_id, task_id, run))
    return {"success": True}


async def _notify_task_cancelled(app: Any, thread_id: str, task_id: str, run: Any) -> None:
    for _ in range(50):
        if run.is_done:
            break
        await asyncio.sleep(0.1)

    if not run.is_done:
        logger.warning("Cancelled task %s never reached a terminal state; skipping cancellation surface", task_id)
        return

    try:
        from backend.threads.event_bus import get_event_bus

        event_bus = get_event_bus()
        emit_fn = event_bus.make_emitter(
            thread_id=thread_id,
            agent_id=task_id,
            agent_name=f"cancel-{task_id[:8]}",
        )
        emission = emit_fn(
            {
                "event": "task_done",
                "data": json.dumps(
                    {
                        "task_id": task_id,
                        "background": True,
                        "cancelled": True,
                    },
                    ensure_ascii=False,
                ),
            }
        )
        if asyncio.iscoroutine(emission):
            await emission
    except Exception:
        logger.warning("Failed to emit task_done for cancelled task %s", task_id, exc_info=True)

    try:
        agent = get_agent_for_thread(app, thread_id)
        qm = getattr(agent, "queue_manager", None) if agent else None
        if qm:
            description = getattr(run, "description", "") or ""
            command = getattr(run, "command", "") or ""
            label = description or command[:80] or f"Task {task_id}"
            notification = (
                f'<CommandNotification task_id="{task_id}" status="cancelled">'
                f"<Status>cancelled</Status>"
                f"<Description>{label}</Description>"
                + (f"<CommandLine>{command[:200]}</CommandLine>" if command else "")
                + "</CommandNotification>"
            )
            qm.enqueue(notification, thread_id, notification_type="command")
    except Exception:
        logger.warning("Failed to enqueue cancellation notice for task %s", task_id, exc_info=True)
