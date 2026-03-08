"""Thread management and execution endpoints."""

import asyncio
import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.web.core.dependencies import get_app, get_thread_agent, get_thread_lock
from backend.web.models.requests import (
    CreateThreadRequest,
    RunRequest,
    SendMessageRequest,
)
from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.sandbox_service import destroy_thread_resources_sync
from backend.web.services.streaming_service import (
    get_or_create_thread_buffer,
    observe_run_events,
    observe_thread_events,
    start_agent_run,
)
from backend.web.services.thread_service import list_threads_from_db
from backend.web.services.thread_state_service import (
    get_lease_status,
    get_sandbox_info,
    get_session_status,
    get_terminal_status,
)
from backend.web.utils.helpers import delete_thread_in_db
from backend.web.utils.serializers import serialize_message

logger = logging.getLogger(__name__)
from core.runtime.middleware.monitor import AgentState
from core.runtime.middleware.queue import format_steer_reminder
from sandbox.thread_context import set_current_thread_id

router = APIRouter(prefix="/api/threads", tags=["threads"])


def _get_agent_for_thread(app: Any, thread_id: str) -> Any | None:
    """Get agent instance for a thread from the agent pool."""
    pool = getattr(app.state, "agent_pool", None)
    if pool is None:
        return None
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"
    return pool.get(pool_key)


@router.post("")
async def create_thread(
    payload: CreateThreadRequest | None = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Create a new thread with optional sandbox and cwd."""

    sandbox_type = payload.sandbox if payload else "local"
    thread_id = str(uuid.uuid4())
    cwd = payload.cwd if payload else None
    agent_name = payload.agent if payload else None
    app.state.thread_sandbox[thread_id] = sandbox_type
    if cwd:
        app.state.thread_cwd[thread_id] = cwd
    from backend.web.utils.helpers import get_active_observation_provider, init_thread_config, save_thread_config

    init_thread_config(thread_id, sandbox_type, cwd)
    model = payload.model if payload else None
    obs_provider = get_active_observation_provider()
    updates = {}
    if model:
        updates["model"] = model
    if obs_provider:
        updates["observation_provider"] = obs_provider
    if agent_name:
        updates["agent"] = agent_name
    if updates:
        save_thread_config(thread_id, **updates)
    return {"thread_id": thread_id, "sandbox": sandbox_type, "agent": agent_name}


@router.get("")
async def list_threads(app: Annotated[Any, Depends(get_app)] = None) -> dict[str, Any]:
    """List all threads with metadata."""
    threads = await asyncio.to_thread(list_threads_from_db)
    tasks = app.state.thread_tasks
    for t in threads:
        t["sandbox"] = resolve_thread_sandbox(app, t["thread_id"])
        t["running"] = t["thread_id"] in tasks
    return {"threads": threads}


@router.get("/{thread_id}")
async def get_thread_messages(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Get messages and sandbox info for a thread."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    set_current_thread_id(thread_id)  # Set thread_id before accessing agent state
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent.agent.aget_state(config)

    values = getattr(state, "values", {}) if state else {}
    messages = values.get("messages", []) if isinstance(values, dict) else []

    # Get sandbox session info (new architecture)
    sandbox_info = get_sandbox_info(agent, thread_id, sandbox_type)

    return {
        "thread_id": thread_id,
        "messages": [serialize_message(msg) for msg in messages],
        "sandbox": sandbox_info,
    }


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Delete a thread and its resources."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"

    lock = await get_thread_lock(app, thread_id)
    async with lock:
        agent = app.state.agent_pool.get(pool_key)
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            raise HTTPException(status_code=409, detail="Cannot delete thread while run is in progress")
        # Clear per-thread handlers before removing agent
        if agent and hasattr(agent, "runtime") and agent.runtime:
            agent.runtime.unbind_thread()
        # Unregister wake handler
        app.state.queue_manager.unregister_wake(thread_id)
        try:
            await asyncio.to_thread(destroy_thread_resources_sync, thread_id, sandbox_type, app.state.agent_pool)
        except Exception as exc:
            logger.warning("Failed to destroy sandbox resources for thread %s: %s", thread_id, exc)
        await asyncio.to_thread(delete_thread_in_db, thread_id)

    # Clean up thread-specific state
    app.state.thread_sandbox.pop(thread_id, None)
    app.state.thread_cwd.pop(thread_id, None)
    app.state.thread_event_buffers.pop(thread_id, None)
    app.state.queue_manager.clear_all(thread_id)

    # Remove per-thread Agent from pool
    app.state.agent_pool.pop(pool_key, None)

    return {"ok": True, "thread_id": thread_id}


@router.post("/{thread_id}/messages")
async def send_message(
    thread_id: str,
    payload: SendMessageRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Send a message to agent. Server auto-routes based on agent state:
    - Agent IDLE  → start new run
    - Agent ACTIVE → enqueue into unified queue (drained at next before_model)
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)

    qm = app.state.queue_manager
    if hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
        qm.enqueue(format_steer_reminder(payload.message), thread_id, notification_type="steer")
        return {"status": "injected", "routing": "steer", "thread_id": thread_id}

    # Agent is IDLE — start new run (both transition and run start must be atomic)
    set_current_thread_id(thread_id)
    lock = await get_thread_lock(app, thread_id)
    async with lock:
        if hasattr(agent, "runtime") and not agent.runtime.transition(AgentState.ACTIVE):
            # Race: became active between check and lock
            qm.enqueue(format_steer_reminder(payload.message), thread_id, notification_type="steer")
            return {"status": "injected", "routing": "steer", "thread_id": thread_id}
        run_id = start_agent_run(agent, thread_id, payload.message, app)
    return {"status": "started", "routing": "direct", "run_id": run_id, "thread_id": thread_id}


@router.post("/{thread_id}/queue")
async def queue_message(
    thread_id: str,
    payload: SendMessageRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Enqueue a followup message. Will be consumed when agent reaches IDLE."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    app.state.queue_manager.enqueue(payload.message, thread_id, notification_type="steer")
    return {"status": "queued", "thread_id": thread_id}


@router.get("/{thread_id}/queue")
async def get_queue(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """List pending followup messages in the queue."""
    messages = app.state.queue_manager.list_queue(thread_id)
    return {"messages": messages, "thread_id": thread_id}


@router.get("/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    limit: int = 20,
    truncate: int = 300,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Compact conversation history for debugging — no raw LangChain noise.

    Args:
        limit: Max messages to return, from the end (default 20)
        truncate: Truncate content to this many chars (default 300, 0 = no limit)
    """
    from backend.web.utils.serializers import extract_text_content

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    set_current_thread_id(thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent.agent.aget_state(config)

    values = getattr(state, "values", {}) if state else {}
    all_messages = values.get("messages", []) if isinstance(values, dict) else []
    total = len(all_messages)
    messages = all_messages[-limit:] if limit > 0 else all_messages

    def _trunc(text: str) -> str:
        if truncate > 0 and len(text) > truncate:
            return text[:truncate] + f"…[+{len(text) - truncate}]"
        return text

    def _expand(msg: Any) -> list[dict[str, Any]]:
        """Expand one LangChain message into 1-N flat entries.

        AIMessage with tool_calls → N tool_call entries (one per call),
        then the text content (if any) as an assistant entry.
        ToolMessage → one tool_result entry.
        HumanMessage → one human entry.
        """
        cls = msg.__class__.__name__
        if cls == "HumanMessage":
            metadata = getattr(msg, "metadata", {}) or {}
            if metadata.get("source") == "system":
                return [{"role": "notification", "text": _trunc(extract_text_content(msg.content))}]
            return [{"role": "human", "text": _trunc(extract_text_content(msg.content))}]
        if cls == "AIMessage":
            entries: list[dict] = []
            for c in getattr(msg, "tool_calls", []):
                entries.append({
                    "role": "tool_call",
                    "tool": c["name"],
                    "args": str(c.get("args", {}))[:200],
                })
            text = extract_text_content(msg.content)
            if text:
                entries.append({"role": "assistant", "text": _trunc(text)})
            return entries or [{"role": "assistant", "text": ""}]
        if cls == "ToolMessage":
            return [{"role": "tool_result", "tool": getattr(msg, "name", "?"), "text": _trunc(extract_text_content(msg.content))}]
        return [{"role": "system", "text": _trunc(extract_text_content(msg.content))}]

    flat: list[dict] = []
    for m in messages:
        flat.extend(_expand(m))

    return {
        "thread_id": thread_id,
        "total": total,
        "showing": len(messages),
        "messages": flat,
    }


@router.get("/{thread_id}/runtime")
async def get_thread_runtime(
    thread_id: str,
    stream: bool = False,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Get runtime status for a thread.

    - stream=false (default): compact {state, model, tokens, cost, calls, ctx_percent, last_seq}
    - stream=true: full verbose data including flags, error details, cache tokens, context breakdown
    """
    from backend.web.services.event_store import get_last_seq, get_latest_run_id, get_run_start_seq
    from backend.web.utils.helpers import lookup_thread_model

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    if not hasattr(agent, "runtime"):
        raise HTTPException(status_code=404, detail="Agent has no runtime monitor")

    last_seq = await get_last_seq(thread_id)

    if not stream:
        status = agent.runtime.get_compact_dict()
        status["model"] = lookup_thread_model(thread_id)
        status["last_seq"] = last_seq
        return status

    status = agent.runtime.get_status_dict()
    status["model"] = lookup_thread_model(thread_id)
    status["last_seq"] = last_seq
    if status.get("state", {}).get("state") == "active":
        run_id = await get_latest_run_id(thread_id)
        if run_id:
            status["run_start_seq"] = await get_run_start_seq(thread_id, run_id)
    return status


# Sandbox control endpoints for threads
@router.post("/{thread_id}/sandbox/pause")
async def pause_thread_sandbox(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Pause sandbox for a thread."""
    try:
        ok = await asyncio.to_thread(agent._sandbox.pause_thread, thread_id)
        if not ok:
            raise HTTPException(409, f"Failed to pause sandbox for thread {thread_id}")
        return {"ok": ok, "thread_id": thread_id}
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/{thread_id}/sandbox/resume")
async def resume_thread_sandbox(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Resume paused sandbox for a thread."""
    try:
        ok = await asyncio.to_thread(agent._sandbox.resume_thread, thread_id)
        if not ok:
            raise HTTPException(409, f"Failed to resume sandbox for thread {thread_id}")
        return {"ok": ok, "thread_id": thread_id}
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/{thread_id}/sandbox")
async def destroy_thread_sandbox(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Destroy sandbox session for a thread."""
    try:
        ok = await asyncio.to_thread(agent._sandbox.manager.destroy_session, thread_id)
        if not ok:
            raise HTTPException(404, f"No sandbox session found for thread {thread_id}")
        agent._sandbox._capability_cache.pop(thread_id, None)
        return {"ok": ok, "thread_id": thread_id}
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


# Session/terminal/lease status endpoints
@router.get("/{thread_id}/session")
async def get_thread_session_status(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Get ChatSession status for a thread."""
    try:
        return await get_session_status(agent, thread_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{thread_id}/terminal")
async def get_thread_terminal_status(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Get AbstractTerminal state for a thread."""
    try:
        return await get_terminal_status(agent, thread_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/{thread_id}/lease")
async def get_thread_lease_status(
    thread_id: str,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    """Get SandboxLease status for a thread."""
    try:
        return await get_lease_status(agent, thread_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


# SSE response headers: disable proxy buffering for real-time streaming
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# Persistent thread event stream (replaces /runs/events + /activity/events)
# ---------------------------------------------------------------------------


@router.get("/{thread_id}/events")
async def stream_thread_events(
    thread_id: str,
    request: Request,
    after: int = 0,
    app: Annotated[Any, Depends(get_app)] = None,
) -> EventSourceResponse:
    """Persistent SSE event stream for a thread — survives across runs.

    Supports reconnection via ``?after=N`` or ``Last-Event-ID`` header.
    The connection stays open until the client disconnects.
    ``run_start`` / ``run_done`` are in-band events, not connection lifecycle signals.
    """
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

    # No buffer yet — create one and optionally replay from SQLite
    thread_buf = get_or_create_thread_buffer(app, thread_id)

    if after > 0:
        # Replay from SQLite for reconnection
        from backend.web.services.event_store import get_latest_run_id, read_events_after

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


# Run endpoint — returns JSON, agent runs in background
@router.post("/{thread_id}/runs")
async def run_thread(
    thread_id: str,
    payload: RunRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Start an agent run. Returns {run_id, thread_id}; observe via GET /events."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    set_current_thread_id(thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)

    # Per-request model override (lightweight, no rebuild)
    if payload.model:
        await asyncio.to_thread(agent.update_config, model=payload.model)

    lock = await get_thread_lock(app, thread_id)
    async with lock:
        if hasattr(agent, "runtime") and not agent.runtime.transition(AgentState.ACTIVE):
            raise HTTPException(status_code=409, detail="Thread is already running")
        run_id = start_agent_run(agent, thread_id, payload.message, app, payload.enable_trajectory)
    return {"run_id": run_id, "thread_id": thread_id}


@router.post("/{thread_id}/runs/cancel")
async def cancel_run(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
):
    """Cancel an active run for the given thread."""
    task = app.state.thread_tasks.get(thread_id)
    if not task:
        return {"ok": False, "message": "No active run found"}
    task.cancel()
    return {"ok": True, "message": "Run cancellation requested"}


# ---------------------------------------------------------------------------
# Background Run API — bridges frontend to agent._background_runs
# ---------------------------------------------------------------------------


def _get_background_runs(app: Any, thread_id: str) -> dict:
    agent = _get_agent_for_thread(app, thread_id)
    return getattr(agent, "_background_runs", {}) if agent else {}


@router.get("/{thread_id}/tasks")
async def list_tasks(
    thread_id: str,
    request: Request,
) -> list[dict]:
    """列出线程的所有后台 run（bash + agent）"""
    runs = _get_background_runs(request.app, thread_id)
    result = []
    for task_id, run in runs.items():
        run_type = "bash" if run.__class__.__name__ == "_BashBackgroundRun" else "agent"
        result.append({
            "task_id": task_id,
            "task_type": run_type,
            "status": "completed" if run.is_done else "running",
            "command_line": getattr(run, "command", None) if run_type == "bash" else None,
            "description": getattr(run, "description", None),
            "exit_code": getattr(getattr(run, "_cmd", None), "exit_code", None) if run_type == "bash" else None,
            "error": None,
        })
    return result


@router.get("/{thread_id}/tasks/{task_id}")
async def get_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """获取 background run 详情（含完整输出）"""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        raise HTTPException(status_code=404, detail="Task not found")

    run_type = "bash" if run.__class__.__name__ == "_BashBackgroundRun" else "agent"
    result_text = run.get_result() if run.is_done else None
    return {
        "task_id": task_id,
        "task_type": run_type,
        "status": "completed" if run.is_done else "running",
        "command_line": getattr(run, "command", None) if run_type == "bash" else None,
        "result": result_text,
        "text": result_text,
    }


@router.post("/{thread_id}/tasks/{task_id}/cancel")
async def cancel_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """取消 background run（bash + agent 统一）"""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        raise HTTPException(status_code=404, detail="Task not found")
    if run.is_done:
        raise HTTPException(status_code=400, detail="Task is not running")

    if run.__class__.__name__ == "_RunningTask":
        run.task.cancel()
    elif run.__class__.__name__ == "_BashBackgroundRun":
        process = getattr(run._cmd, "process", None)
        if process:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    # Emit task_done SSE and notify main agent once cancellation completes
    asyncio.create_task(_notify_task_cancelled(request.app, thread_id, task_id, run))

    return {"success": True}


async def _notify_task_cancelled(app: Any, thread_id: str, task_id: str, run: Any) -> None:
    """Wait for run to finish, then emit task_done SSE and enqueue cancellation notice."""
    # Wait up to 5s for the task to actually stop
    for _ in range(50):
        if run.is_done:
            break
        await asyncio.sleep(0.1)

    # Emit task_done so the frontend indicator updates
    try:
        from backend.web.event_bus import get_event_bus
        event_bus = get_event_bus()
        emit_fn = event_bus.make_emitter(
            thread_id=thread_id,
            agent_id=task_id,
            agent_name=f"cancel-{task_id[:8]}",
        )
        await emit_fn({"event": "task_done", "data": json.dumps({
            "task_id": task_id,
            "background": True,
            "cancelled": True,
        }, ensure_ascii=False)})
    except Exception:
        logger.debug("Failed to emit task_done for cancelled task %s", task_id, exc_info=True)

    # Notify the main agent so it knows the user cancelled this task
    try:
        agent = _get_agent_for_thread(app, thread_id)
        qm = getattr(agent, "queue_manager", None) if agent else None
        if qm:
            notification = (
                f'<CommandNotification task_id="{task_id}" status="cancelled">'
                f"Task was cancelled by user.</CommandNotification>"
            )
            qm.enqueue(notification, thread_id, notification_type="command")
    except Exception:
        logger.debug("Failed to enqueue cancellation notice for task %s", task_id, exc_info=True)
