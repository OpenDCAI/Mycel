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
    TaskAgentRequest,
)
from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.sandbox_service import destroy_thread_resources_sync
from backend.web.services.streaming_service import (
    get_or_create_thread_buffer,
    observe_run_events,
    observe_thread_events,
    start_agent_run,
    start_task_agent_run,
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

    def _compact(msg: Any) -> dict[str, Any]:
        cls = msg.__class__.__name__
        if cls == "HumanMessage":
            return {"role": "human", "text": _trunc(extract_text_content(msg.content))}
        if cls == "AIMessage":
            calls = getattr(msg, "tool_calls", [])
            if calls:
                return {
                    "role": "ai",
                    "calls": [
                        {"tool": c["name"], "args": str(c.get("args", {}))[:120]}
                        for c in calls
                    ],
                }
            return {"role": "ai", "text": _trunc(extract_text_content(msg.content))}
        if cls == "ToolMessage":
            tool_name = getattr(msg, "name", None) or getattr(msg, "tool_call_id", "?")
            return {"role": "tool", "tool": tool_name, "text": _trunc(extract_text_content(msg.content))}
        # SystemMessage or other
        return {"role": cls.lower().replace("message", ""), "text": _trunc(extract_text_content(msg.content))}

    return {
        "thread_id": thread_id,
        "total": total,
        "showing": len(messages),
        "messages": [_compact(m) for m in messages],
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


@router.post("/{thread_id}/commands/{command_id}/cancel")
async def cancel_command(
    thread_id: str,
    command_id: str,
    request: Request,
) -> dict[str, Any]:
    """Cancel a specific async command by terminating its process."""
    agent = _get_agent_for_thread(request.app, thread_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Find CommandMiddleware via TaskMiddleware's parent_middleware list
    parent_mw = getattr(getattr(agent, "_task_middleware", None), "parent_middleware", [])
    from core.command import CommandMiddleware

    for mw in parent_mw:
        if not isinstance(mw, CommandMiddleware):
            continue
        executor = getattr(mw, "_executor", None)
        if not executor:
            continue
        status = await executor.get_status(command_id)
        if status and not status.done:
            process = getattr(status, "process", None)
            if process:
                process.terminate()
                return {"cancelled": True, "command_id": command_id}

    raise HTTPException(404, "Command not found or already completed")


@router.post("/{thread_id}/task-agent/runs")
async def run_task_agent(
    thread_id: str,
    payload: TaskAgentRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Start a task agent run. Observe events via GET /events."""
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt cannot be empty")

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    buf = start_task_agent_run(thread_id, payload, app, sandbox_type)
    return {"run_id": buf.run_id, "thread_id": thread_id}


# ---------------------------------------------------------------------------
# Phase 4: Background Task Output API
# ---------------------------------------------------------------------------


@router.get("/{thread_id}/tasks")
async def list_tasks(
    thread_id: str,
    request: Request,
) -> list[dict]:
    """列出线程的所有后台任务"""
    registry = request.app.state.background_task_registry
    tasks = await registry.list_by_thread(thread_id)

    return [
        {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "command_line": task.command_line,  # bash only
            "description": task.description,  # agent only
            "exit_code": task.exit_code,  # bash only
            "error": task.error,
        }
        for task in tasks
    ]


@router.get("/{thread_id}/tasks/{task_id}")
async def get_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """获取任务详情（包含完整输出）"""
    registry = request.app.state.background_task_registry
    task = await registry.get(task_id)

    if not task or task.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "command_line": task.command_line,
        "description": task.description,
        "subagent_type": task.subagent_type,
        "exit_code": task.exit_code,
        "error": task.error,
        # 完整输出
        "stdout": task.stdout_buffer,  # bash only
        "stderr": task.stderr_buffer,  # bash only
        "text": task.text_buffer,  # agent only
        "result": task.result,  # agent only
    }


@router.get("/{thread_id}/tasks/{task_id}/stream")
async def stream_task_output(
    thread_id: str,
    task_id: str,
    request: Request,
):
    """SSE 流式输出任务进度（按需建连）"""
    registry = request.app.state.background_task_registry
    task = await registry.get(task_id)

    if not task or task.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        if task.task_type == "bash":
            # Tail subprocess stdout/stderr
            process = task._process
            if process and process.returncode is None:
                # 实时读取 stdout/stderr
                try:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        yield {
                            "event": "output",
                            "data": json.dumps({"type": "stdout", "line": line.decode()}, ensure_ascii=False),
                        }
                except Exception:
                    pass

        elif task.task_type == "agent":
            # 从 text_buffer 读取
            sent_count = 0
            while task.status == "running":
                if task.text_buffer and len(task.text_buffer) > sent_count:
                    for text in task.text_buffer[sent_count:]:
                        yield {
                            "event": "output",
                            "data": json.dumps({"type": "text", "content": text}, ensure_ascii=False),
                        }
                    sent_count = len(task.text_buffer)
                await asyncio.sleep(0.1)

        # 任务完成
        yield {
            "event": "task_done",
            "data": json.dumps({"status": task.status}, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator(), headers=SSE_HEADERS)


@router.post("/{thread_id}/tasks/{task_id}/cancel")
async def cancel_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """取消任务（统一 bash + agent）"""
    registry = request.app.state.background_task_registry
    task = await registry.get(task_id)

    if not task or task.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != "running":
        raise HTTPException(status_code=400, detail="Task is not running")

    # 取消任务
    if task.task_type == "bash" and task._process:
        try:
            task._process.terminate()
        except ProcessLookupError:
            pass
    elif task.task_type == "agent" and task._async_task:
        task._async_task.cancel()

    await registry.update(task_id, status="error", error="Cancelled by user")

    return {"success": True}
