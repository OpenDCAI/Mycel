"""SSE streaming service for agent execution."""

import asyncio
import json
import logging
import traceback
import uuid as _uuid
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)

from backend.web.services.event_buffer import RunEventBuffer
from backend.web.services.event_store import cleanup_old_runs
from backend.web.utils.serializers import extract_text_content
from core.monitor import AgentState
from storage.contracts import RunEventRepo
from sandbox.thread_context import set_current_run_id, set_current_thread_id


def _resolve_run_event_repo(agent: Any) -> RunEventRepo | None:
    storage_container = getattr(agent, "storage_container", None)
    if storage_container is None:
        return None

    # @@@runtime-storage-consumer - runtime run lifecycle must consume injected storage container, not assignment-only wiring.
    return storage_container.run_event_repo()


async def prime_sandbox(agent: Any, thread_id: str) -> None:
    """Prime sandbox session before tool calls to avoid race conditions."""

    def _prime_sandbox() -> None:
        mgr = agent._sandbox.manager
        mgr.enforce_idle_timeouts()
        terminal = mgr.terminal_store.get(thread_id)
        if terminal:
            existing = mgr.session_manager.get(thread_id, terminal.terminal_id)
            if existing and existing.status == "paused":
                if not agent._sandbox.resume_thread(thread_id):
                    raise RuntimeError(f"Failed to resume paused session for thread {thread_id}")
        agent._sandbox.ensure_session(thread_id)
        terminal = mgr.terminal_store.get(thread_id)
        lease = mgr.lease_store.get(terminal.lease_id) if terminal else None
        if lease:
            lease_status = lease.refresh_instance_status(mgr.provider)
            if lease_status == "paused" and mgr.provider_capability.can_resume:
                if not agent._sandbox.resume_thread(thread_id):
                    raise RuntimeError(f"Failed to auto-resume paused sandbox for thread {thread_id}")

    await asyncio.to_thread(_prime_sandbox)


async def write_cancellation_markers(
    agent: Any,
    config: dict[str, Any],
    pending_tool_calls: dict[str, dict],
) -> list[str]:
    """Write cancellation markers to checkpoint for pending tool calls.

    Returns:
        List of cancelled tool call IDs
    """
    cancelled_tool_call_ids = []
    if not pending_tool_calls or not agent:
        return cancelled_tool_call_ids

    try:
        from langchain_core.messages import ToolMessage
        from langgraph.checkpoint.base import create_checkpoint

        checkpointer = agent.agent.checkpointer
        if not checkpointer:
            return cancelled_tool_call_ids

        # aget_tuple returns CheckpointTuple with .checkpoint and .metadata
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        if not checkpoint_tuple:
            return cancelled_tool_call_ids

        checkpoint = checkpoint_tuple.checkpoint
        metadata = checkpoint_tuple.metadata or {}

        # Create ToolMessage for each pending tool call
        cancel_messages = []
        for tc_id, tc_info in pending_tool_calls.items():
            cancelled_tool_call_ids.append(tc_id)
            cancel_messages.append(
                ToolMessage(
                    content="任务被用户取消",
                    tool_call_id=tc_id,
                    name=tc_info["name"],
                )
            )

        # Update checkpoint with cancellation markers
        updated_channel_values = checkpoint["channel_values"].copy()
        updated_channel_values["messages"] = list(updated_channel_values.get("messages", []))
        updated_channel_values["messages"].extend(cancel_messages)

        # Prepare new versions for checkpoint
        new_versions = {k: int(v) + 1 for k, v in checkpoint["channel_versions"].items()}

        # Build complete checkpoint with all required fields
        new_checkpoint = create_checkpoint(checkpoint, None, metadata.get("step", 0))
        # Override channel_values with our updated messages
        new_checkpoint["channel_values"] = updated_channel_values

        # Write updated checkpoint
        await checkpointer.aput(
            config,
            new_checkpoint,
            {
                "source": "update",
                "step": metadata.get("step", 0),
                "writes": {},
            },
            new_versions,
        )
    except Exception:
        logger.exception("[streaming] failed to write cancellation markers for thread %s", thread_id)

    return cancelled_tool_call_ids


# ---------------------------------------------------------------------------
# Per-thread handler setup (idempotent, survives across runs)
# ---------------------------------------------------------------------------


def _ensure_thread_handlers(agent: Any, thread_id: str, app: Any) -> None:
    """Bind per-thread handlers (activity_sink, wake_handler) if not already set.

    These handlers have per-thread lifetime and must NOT be cleared between runs.
    Idempotent — safe to call at the start of every run.
    """
    runtime = getattr(agent, "runtime", None)
    if not runtime:
        return
    # Already bound? Skip.
    if getattr(runtime, "_activity_sink", None) is not None:
        return
    # Runtime must support bind_thread (AgentRuntime does, test fakes may not)
    if not hasattr(runtime, "bind_thread"):
        return

    # activity_buf is thread-scoped, reused across runs
    activity_buf = app.state.activity_buffers.get(thread_id)
    if not activity_buf:
        activity_buf = RunEventBuffer()
        activity_buf.run_id = f"activity_{thread_id}"
        app.state.activity_buffers[thread_id] = activity_buf

    async def activity_sink(event: dict) -> None:
        from backend.web.services.event_store import append_event as _append

        seq = await _append(thread_id, activity_buf.run_id, event)
        try:
            data = json.loads(event.get("data", "{}")) if isinstance(event.get("data"), str) else event.get("data", {})
        except (json.JSONDecodeError, TypeError):
            data = event.get("data", {})
        if isinstance(data, dict):
            data["_seq"] = seq
            event = {**event, "data": json.dumps(data, ensure_ascii=False)}
        await activity_buf.put(event)

    qm = app.state.queue_manager
    loop = getattr(app.state, "_event_loop", None)

    def wake_handler() -> None:
        """Called by enqueue() — may run in any thread."""
        if not (hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE)):
            logger.warning("wake_handler: failed to transition to ACTIVE for thread %s (state=%s)",
                           thread_id, getattr(agent.runtime, "current_state", "unknown") if hasattr(agent, "runtime") else "no-runtime")
            return  # ACTIVE: before_model will drain_all

        msg = qm.dequeue(thread_id)
        if not msg:
            # Lost race to finally block — undo transition
            logger.warning("wake_handler: dequeue returned None for thread %s (race with drain_all), reverting to IDLE", thread_id)
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)
            return

        async def _start_run():
            try:
                new_buf = start_agent_run(
                    agent, thread_id, msg, app,
                    message_metadata={"source": "system"},
                )
                await activity_sink({
                    "event": "new_run",
                    "data": json.dumps({"thread_id": thread_id, "run_id": new_buf.run_id}),
                })
            except Exception:
                logger.error("wake_handler failed for thread %s", thread_id, exc_info=True)
                if hasattr(agent, "runtime"):
                    agent.runtime.transition(AgentState.IDLE)
                # Do NOT re-enqueue — avoid enqueue→wake→enqueue infinite recursion

        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(loop.create_task, _start_run())
        else:
            logger.warning("wake_handler: no event loop for thread %s", thread_id)
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)

    runtime.bind_thread(activity_sink=activity_sink)
    qm.register_wake(thread_id, wake_handler)


def _parse_event_data(event: dict) -> dict:
    """Parse the JSON data field of an activity event. Returns empty dict on failure."""
    raw = event.get("data", "{}")
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Producer: runs agent, writes events to buffer
# ---------------------------------------------------------------------------


async def _run_agent_to_buffer(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool,
    buf: RunEventBuffer,
    message_metadata: dict[str, Any] | None = None,
) -> None:
    """Run agent execution and write all SSE events into *buf*."""
    from backend.web.services.event_store import append_event

    run_id = buf.run_id
    run_event_repo = _resolve_run_event_repo(agent)

    async def emit(event: dict, message_id: str | None = None) -> None:
        seq = await append_event(
            thread_id,
            run_id,
            event,
            message_id,
            run_event_repo=run_event_repo,
        )
        try:
            data = json.loads(event.get("data", "{}")) if isinstance(event.get("data"), str) else event.get("data", {})
        except (json.JSONDecodeError, TypeError):
            data = event.get("data", {})
        if isinstance(data, dict):
            data["_seq"] = seq
            data["_run_id"] = run_id
            if message_id:
                data["message_id"] = message_id
            event = {**event, "data": json.dumps(data, ensure_ascii=False)}
        await buf.put(event)

    task = None
    stream_gen = None
    pending_tool_calls: dict[str, dict] = {}
    # Per-subagent RunEventBuffer: task_id → (sa_thread_id, buf)
    subagent_buffers: dict[str, tuple[str, RunEventBuffer]] = {}
    try:
        config = {"configurable": {"thread_id": thread_id}}
        if hasattr(agent, "_current_model_config"):
            config["configurable"].update(agent._current_model_config)
        set_current_thread_id(thread_id)
        # Bind thread_id to TaskBoardMiddleware so ClaimTask records the executor
        if hasattr(agent, '_taskboard_middleware'):
            agent._taskboard_middleware.thread_id = thread_id
        # @@@web-run-context - web runs have no TUI checkpoint; use run_id to group file ops per run.
        set_current_run_id(run_id)

        # Trajectory tracing (eval system)
        tracer = None
        if enable_trajectory:
            try:
                from eval.tracer import TrajectoryTracer

                cost_calc = getattr(
                    getattr(getattr(agent, "runtime", None), "token", None),
                    "cost_calculator",
                    None,
                )
                tracer = TrajectoryTracer(
                    thread_id=thread_id,
                    user_message=message,
                    cost_calculator=cost_calc,
                )
                config["callbacks"] = [tracer]
            except ImportError:
                pass

        # Observation provider: provider from thread config, credentials from global config
        obs_handler = None
        obs_active = None
        obs_provider = None
        try:
            from backend.web.utils.helpers import load_thread_config

            thread_cfg = load_thread_config(thread_id)
            obs_provider = thread_cfg.observation_provider if thread_cfg else None

            if obs_provider:
                from config.observation_loader import ObservationLoader

                obs_config = ObservationLoader().load()

                if obs_provider == "langfuse":
                    from langfuse import Langfuse
                    from langfuse.langchain import CallbackHandler as LangfuseHandler

                    cfg = obs_config.langfuse
                    if cfg.secret_key and cfg.public_key:
                        obs_active = "langfuse"
                        # Initialize global Langfuse client (CallbackHandler uses it)
                        Langfuse(
                            public_key=cfg.public_key,
                            secret_key=cfg.secret_key,
                            host=cfg.host or "https://cloud.langfuse.com",
                        )
                        obs_handler = LangfuseHandler(public_key=cfg.public_key)
                        config.setdefault("callbacks", []).append(obs_handler)
                        config.setdefault("metadata", {})["langfuse_session_id"] = thread_id
                elif obs_provider == "langsmith":
                    from langchain_core.tracers.langchain import LangChainTracer
                    from langsmith import Client as LangSmithClient

                    cfg = obs_config.langsmith
                    if cfg.api_key:
                        obs_active = "langsmith"
                        ls_client = LangSmithClient(
                            api_key=cfg.api_key,
                            api_url=cfg.endpoint or "https://api.smith.langchain.com",
                        )
                        obs_handler = LangChainTracer(
                            client=ls_client,
                            project_name=cfg.project or "default",
                        )
                        config.setdefault("callbacks", []).append(obs_handler)
                        config.setdefault("metadata", {})["session_id"] = thread_id
        except ImportError as imp_err:
            logger.warning("Observation provider '%s' missing package: %s. Install: uv pip install 'leonai[%s]'", obs_provider, imp_err, obs_provider)
        except Exception as obs_err:
            logger.warning("Observation handler error: %s", obs_err, exc_info=True)

        # Real-time activity event callback (replaces post-hoc batch drain)
        activity_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

        def on_activity_event(event: dict) -> None:
            try:
                activity_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Backpressure: drop under overload

        if hasattr(agent, "runtime"):
            agent.runtime.set_event_callback(on_activity_event)

        # Bind per-thread handlers (idempotent — safe across runs)
        _ensure_thread_handlers(agent, thread_id, app)

        if hasattr(agent, "_sandbox"):
            await prime_sandbox(agent, thread_id)

        emitted_tool_call_ids: set[str] = set()

        async def run_agent_stream():
            if message_metadata:
                from langchain_core.messages import HumanMessage
                input_msg = HumanMessage(content=message, metadata=message_metadata)
            else:
                input_msg = {"role": "user", "content": message}
            async for chunk in agent.agent.astream(
                {"messages": [input_msg]},
                config=config,
                stream_mode=["messages", "updates"],
            ):
                yield chunk

        stream_gen = run_agent_stream()
        task = asyncio.create_task(stream_gen.__anext__())
        app.state.thread_tasks[thread_id] = task

        while True:
            try:
                chunk = await task
                task = asyncio.create_task(stream_gen.__anext__())
                app.state.thread_tasks[thread_id] = task
            except StopAsyncIteration:
                break
            except Exception as stream_error:
                traceback.print_exc()
                await emit({"event": "error", "data": json.dumps({"error": str(stream_error)}, ensure_ascii=False)})
                break
            if not chunk:
                continue

            if not isinstance(chunk, tuple) or len(chunk) != 2:
                continue
            mode, data = chunk

            if mode == "messages":
                msg_chunk, metadata = data
                msg_class = msg_chunk.__class__.__name__
                if msg_class == "AIMessageChunk":
                    content = extract_text_content(getattr(msg_chunk, "content", ""))
                    chunk_msg_id = getattr(msg_chunk, "id", None)
                    if content:
                        await emit(
                            {
                                "event": "text",
                                "data": json.dumps({"content": content}, ensure_ascii=False),
                            },
                            message_id=chunk_msg_id,
                        )

            elif mode == "updates":
                if not isinstance(data, dict):
                    continue
                for _node_name, node_update in data.items():
                    if not isinstance(node_update, dict):
                        continue
                    messages = node_update.get("messages", [])
                    if not isinstance(messages, list):
                        messages = [messages]
                    for msg in messages:
                        msg_class = msg.__class__.__name__
                        if msg_class == "AIMessage":
                            ai_msg_id = getattr(msg, "id", None)
                            for tc in getattr(msg, "tool_calls", []):
                                tc_id = tc.get("id")
                                if tc_id and tc_id in emitted_tool_call_ids:
                                    continue
                                if tc_id:
                                    emitted_tool_call_ids.add(tc_id)
                                    pending_tool_calls[tc_id] = {
                                        "name": tc.get("name", "unknown"),
                                        "args": tc.get("args", {}),
                                    }
                                await emit(
                                    {
                                        "event": "tool_call",
                                        "data": json.dumps(
                                            {
                                                "id": tc.get("id"),
                                                "name": tc.get("name", "unknown"),
                                                "args": tc.get("args", {}),
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                    message_id=ai_msg_id,
                                )
                        elif msg_class == "ToolMessage":
                            tc_id = getattr(msg, "tool_call_id", None)
                            tool_msg_id = getattr(msg, "id", None)
                            if tc_id:
                                pending_tool_calls.pop(tc_id, None)
                            await emit(
                                {
                                    "event": "tool_result",
                                    "data": json.dumps(
                                        {
                                            "tool_call_id": tc_id,
                                            "name": getattr(msg, "name", "unknown"),
                                            "content": str(getattr(msg, "content", "")),
                                            "metadata": getattr(msg, "metadata", None) or {},
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                                message_id=tool_msg_id,
                            )
                            if hasattr(agent, "runtime"):
                                status = agent.runtime.get_status_dict()
                                status["current_tool"] = getattr(msg, "name", None)
                                await emit(
                                    {
                                        "event": "status",
                                        "data": json.dumps(status, ensure_ascii=False),
                                    }
                                )

            # Drain real-time activity events (sub-agent, command progress, etc.)
            while not activity_queue.empty():
                try:
                    act_event = activity_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                event_type = act_event.get("event", "")

                sa_data = _parse_event_data(act_event)

                if event_type == "subagent_task_start":
                    # Create dedicated SSE buffer for the subagent thread
                    task_id = sa_data.get("task_id", "")
                    sa_thread_id = sa_data.get("thread_id", f"subagent_{task_id}")
                    if task_id:
                        sa_buf = RunEventBuffer()
                        sa_buf.run_id = str(_uuid.uuid4())
                        subagent_buffers[task_id] = (sa_thread_id, sa_buf)
                        app.state.thread_event_buffers[sa_thread_id] = sa_buf
                    # Emit slim lifecycle notification to parent SSE
                    await emit(act_event)

                elif event_type in ("subagent_task_text", "subagent_task_tool_call", "subagent_task_tool_result"):
                    # Route to subagent buffer only — skip parent SSE (prevents leakage)
                    task_id = sa_data.get("task_id", "")
                    sa_entry = subagent_buffers.get(task_id)
                    if sa_entry:
                        _, sa_buf = sa_entry
                        await sa_buf.put(act_event)

                elif event_type in ("subagent_task_done", "subagent_task_error"):
                    # Close subagent buffer + emit lifecycle notification to parent
                    task_id = sa_data.get("task_id", "")
                    sa_entry = subagent_buffers.pop(task_id, None)
                    if sa_entry:
                        sa_thread_id, sa_buf = sa_entry
                        await sa_buf.put(act_event)
                        # Emit terminal event so SSE consumer exits cleanly
                        await sa_buf.put({"event": "done", "data": json.dumps({"thread_id": sa_thread_id})})
                        await sa_buf.mark_done()
                        app.state.thread_event_buffers.pop(sa_thread_id, None)
                    await emit(act_event)

                else:
                    # All other activity events (command_progress, background_task_*, etc.)
                    await emit(act_event)

        # Final status
        if hasattr(agent, "runtime"):
            await emit(
                {
                    "event": "status",
                    "data": json.dumps(agent.runtime.get_status_dict(), ensure_ascii=False),
                }
            )

        # Persist trajectory
        if tracer is not None:
            try:
                from eval.storage import TrajectoryStore

                trajectory = tracer.to_trajectory()
                if hasattr(agent, "runtime"):
                    tracer.enrich_from_runtime(trajectory, agent.runtime)
                store = TrajectoryStore()
                store.save_trajectory(trajectory)
            except Exception:
                logger.error("Failed to persist trajectory for thread %s", thread_id, exc_info=True)

        await emit({"event": "done", "data": json.dumps({"thread_id": thread_id})})
    except asyncio.CancelledError:
        cancelled_tool_call_ids = await write_cancellation_markers(agent, config, pending_tool_calls)
        await emit(
            {
                "event": "cancelled",
                "data": json.dumps(
                    {
                        "message": "Run cancelled by user",
                        "cancelled_tool_call_ids": cancelled_tool_call_ids,
                    }
                ),
            }
        )
    except Exception as e:
        traceback.print_exc()
        await emit({"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)})
    finally:
        # Clean up any subagent buffers not already closed (e.g., on cancellation/error)
        for _task_id, (sa_thread_id, sa_buf) in list(subagent_buffers.items()):
            await sa_buf.mark_done()
            app.state.thread_event_buffers.pop(sa_thread_id, None)
        subagent_buffers.clear()

        # Notify activity channel that this run finished (so frontend can refresh)
        if hasattr(agent, "runtime"):
            agent.runtime.emit_activity_event(
                {"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})}
            )
        # Detach per-run event callback (per-thread handlers survive across runs)
        if hasattr(agent, "runtime"):
            agent.runtime.set_event_callback(None)
        # Flush observation handler
        if obs_handler is not None:
            try:
                if obs_active == "langfuse":
                    from langfuse import get_client
                    get_client().flush()
                elif obs_active == "langsmith":
                    obs_handler.wait_for_futures()
            except Exception as flush_err:
                logger.warning("Observation flush error: %s", flush_err)
        await buf.mark_done()
        app.state.thread_tasks.pop(thread_id, None)
        app.state.thread_event_buffers.pop(thread_id, None)
        if stream_gen is not None:
            await stream_gen.aclose()
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            agent.runtime.transition(AgentState.IDLE)

        # Check for pending board tasks on idle
        if hasattr(agent, '_taskboard_middleware') and agent._taskboard_middleware.auto_claim:
            try:
                next_task = await agent._taskboard_middleware.on_idle()
                if next_task:
                    logger.info("Board task available: %s (id=%s)", next_task.get("title"), next_task["id"])
                    # V1: log only. Auto-execution requires thread management design (V2).
            except Exception:
                logger.debug("Board task idle check failed", exc_info=True)

        # Clean up old run events and close repo BEFORE starting followup run,
        # so the new run gets a fresh connection and there is no closed-repo race.
        try:
            await cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=run_event_repo)
        except Exception:
            logger.warning("Failed to cleanup old runs for thread %s", thread_id, exc_info=True)
        if run_event_repo is not None:
            run_event_repo.close()

        # Consume followup queue: if messages are pending, start a new run
        await _consume_followup_queue(agent, thread_id, app)


# ---------------------------------------------------------------------------
# Followup queue consumption (extracted for testability)
# ---------------------------------------------------------------------------


async def _consume_followup_queue(agent: Any, thread_id: str, app: Any) -> None:
    """Dequeue a pending followup message and start a new run.

    If starting the new run fails, re-enqueue the message so it is not lost.
    """
    followup = None
    try:
        qm = app.state.queue_manager
        followup = qm.dequeue(thread_id)
        if followup and app:
            if hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE):
                new_buf = start_agent_run(agent, thread_id, followup, app,
                                          message_metadata={"source": "system"})
                # Emit new_run so the frontend notification stream reconnects.
                # Mirrors wake_handler._start_run() which does the same for idle-triggered runs.
                activity_sink = getattr(getattr(agent, "runtime", None), "_activity_sink", None)
                if activity_sink:
                    await activity_sink({
                        "event": "new_run",
                        "data": json.dumps({"thread_id": thread_id, "run_id": new_buf.run_id}),
                    })
    except Exception:
        logger.exception("Failed to consume followup queue for thread %s", thread_id)
        # Re-enqueue the message if it was already dequeued to prevent data loss
        if followup:
            try:
                app.state.queue_manager.enqueue(followup, thread_id)
            except Exception:
                logger.error("Failed to re-enqueue followup for thread %s — message lost: %.200s", thread_id, followup)


# ---------------------------------------------------------------------------
# Orchestrator: creates buffer + launches background task
# ---------------------------------------------------------------------------


def start_agent_run(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool = False,
    message_metadata: dict[str, Any] | None = None,
) -> RunEventBuffer:
    """Create a RunEventBuffer and launch the agent producer as a background task."""

    buf = RunEventBuffer()
    buf.run_id = str(_uuid.uuid4())
    app.state.thread_event_buffers[thread_id] = buf
    bg_task = asyncio.create_task(
        _run_agent_to_buffer(agent, thread_id, message, app, enable_trajectory, buf, message_metadata)
    )
    # Store the background task so cancel_run can still cancel it
    app.state.thread_tasks[thread_id] = bg_task
    return buf


# ---------------------------------------------------------------------------
# Consumer: reads from buffer and yields SSE dicts
# ---------------------------------------------------------------------------


async def observe_run_events(
    buf: RunEventBuffer,
    after: int = 0,
) -> AsyncGenerator[dict[str, str], None]:
    """Consume events from a RunEventBuffer. Yields SSE event dicts.

    Safe to abort — does not affect the producer or agent state.
    When *after* > 0, skip events whose injected ``_seq`` <= after.
    Sends heartbeat comments every 30s to keep the connection alive.
    Each event includes an ``id`` field for Last-Event-ID reconnection.
    """
    # Tell the browser to reconnect after 5s if the connection drops
    yield {"retry": 5000}

    cursor = 0
    while True:
        events, cursor = await buf.read_with_timeout(cursor, timeout=30)
        if events is None and not buf.finished.is_set():
            yield {"comment": "keepalive"}
            continue
        if not events and buf.finished.is_set():
            break
        if not events:
            continue
        for event in events:
            # Parse data once, reuse for both after-filtering and id injection
            parsed_data = None
            try:
                parsed_data = json.loads(event.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            if after > 0 and isinstance(parsed_data, dict):
                if parsed_data.get("_seq", 0) <= after:
                    continue

            # Inject SSE id from _seq for Last-Event-ID support
            seq_id = str(parsed_data["_seq"]) if isinstance(parsed_data, dict) and "_seq" in parsed_data else None
            if seq_id:
                yield {**event, "id": seq_id}
            else:
                yield event


# ---------------------------------------------------------------------------
# Task agent: buffer-based producer (same pattern as main agent)
# ---------------------------------------------------------------------------


def start_task_agent_run(
    thread_id: str,
    payload: Any,
    app: Any,
    sandbox_type: str,
) -> RunEventBuffer:
    """Create a RunEventBuffer and launch task agent as background task."""

    buf = RunEventBuffer()
    buf.run_id = str(_uuid.uuid4())
    app.state.thread_event_buffers[thread_id] = buf
    bg_task = asyncio.create_task(_run_task_agent_to_buffer(thread_id, payload, app, sandbox_type, buf))
    app.state.thread_tasks[thread_id] = bg_task
    return buf


async def _run_task_agent_to_buffer(
    thread_id: str,
    payload: Any,
    app: Any,
    sandbox_type: str,
    buf: RunEventBuffer,
) -> None:
    """Task agent producer — writes events to buffer."""
    try:
        set_current_thread_id(thread_id)
        from backend.web.services.agent_pool import get_or_create_agent

        agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
        # Bind thread_id to TaskBoardMiddleware
        if hasattr(agent, '_taskboard_middleware'):
            agent._taskboard_middleware.thread_id = thread_id

        # Get TaskMiddleware from agent
        task_middleware = None
        if hasattr(agent, "middleware"):
            for mw in agent.middleware:
                if mw.__class__.__name__ == "TaskMiddleware":
                    task_middleware = mw
                    break

        if not task_middleware:
            await buf.put(
                {
                    "event": "task_error",
                    "data": json.dumps({"error": "TaskMiddleware not available"}, ensure_ascii=False),
                }
            )
            return

        # Build task params
        params: dict[str, Any] = {
            "SubagentType": payload.subagent_type,
            "Prompt": payload.prompt,
        }
        if payload.description:
            params["Description"] = payload.description
        if payload.model:
            params["Model"] = payload.model
        if payload.max_turns:
            params["MaxTurns"] = payload.max_turns

        # Stream task execution into buffer
        async for event in task_middleware.run_task_streaming(params):
            await buf.put(event)

        await buf.put({"event": "done", "data": json.dumps({"thread_id": thread_id})})
    except Exception as e:
        traceback.print_exc()
        await buf.put(
            {
                "event": "task_error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }
        )
    finally:
        await buf.mark_done()
        app.state.thread_tasks.pop(thread_id, None)
        app.state.thread_event_buffers.pop(thread_id, None)
