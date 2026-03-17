"""SSE streaming service for agent execution."""

import asyncio
import json
import logging
import random
import traceback
import uuid as _uuid
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)

from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.event_store import cleanup_old_runs
from backend.web.utils.serializers import extract_text_content
from core.runtime.middleware.monitor import AgentState
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
        logger.exception("[streaming] failed to write cancellation markers for thread %s", config.get("configurable", {}).get("thread_id"))

    return cancelled_tool_call_ids


async def _repair_incomplete_tool_calls(agent: Any, config: dict[str, Any]) -> None:
    """Detect and repair incomplete tool_call history in checkpoint.

    If an AIMessage has tool_calls without matching ToolMessages,
    insert synthetic error ToolMessages at the correct position
    (right after the AIMessage) so the LLM doesn't reject the history.
    """
    try:
        from langchain_core.messages import RemoveMessage, ToolMessage

        graph = getattr(agent, "agent", None)
        if not graph:
            return

        state = await graph.aget_state(config)
        if not state or not state.values:
            return

        messages = state.values.get("messages", [])
        if not messages:
            return

        # Collect all tool_call IDs and their ToolMessage responses
        pending_tc_ids: dict[str, str] = {}  # tc_id -> tool_name
        answered_tc_ids: set[str] = set()

        for msg in messages:
            msg_class = msg.__class__.__name__
            if msg_class == "AIMessage":
                for tc in getattr(msg, "tool_calls", []):
                    tc_id = tc.get("id")
                    if tc_id:
                        pending_tc_ids[tc_id] = tc.get("name", "unknown")
            elif msg_class == "ToolMessage":
                tc_id = getattr(msg, "tool_call_id", None)
                if tc_id:
                    answered_tc_ids.add(tc_id)

        unmatched = {tc_id: name for tc_id, name in pending_tc_ids.items() if tc_id not in answered_tc_ids}
        if not unmatched:
            return

        thread_id = config.get("configurable", {}).get("thread_id")
        logger.warning(
            "[streaming] Repairing %d incomplete tool_call(s) in thread %s: %s",
            len(unmatched), thread_id, list(unmatched.keys()),
        )

        # Strategy: remove messages after the broken AIMessage, then re-add
        # them with the ToolMessage inserted at the correct position.
        # Find the first broken AIMessage index
        broken_ai_idx = None
        for i, msg in enumerate(messages):
            if msg.__class__.__name__ == "AIMessage":
                for tc in getattr(msg, "tool_calls", []):
                    if tc.get("id") in unmatched:
                        broken_ai_idx = i
                        break
            if broken_ai_idx is not None:
                break

        if broken_ai_idx is None:
            return

        # Messages after the broken AIMessage that need to be re-ordered
        after_msgs = messages[broken_ai_idx + 1:]

        # Build update: remove all messages after broken AI, then add
        # ToolMessage(s) + remaining messages in order
        updates = []

        # Remove messages after the broken AIMessage
        for msg in after_msgs:
            msg_id = getattr(msg, "id", None)
            if msg_id:
                updates.append(RemoveMessage(id=msg_id))

        # Add synthetic ToolMessages for unmatched tool_calls
        for tc_id, tool_name in unmatched.items():
            updates.append(
                ToolMessage(
                    content="Error: task was interrupted (server restart or timeout). Results unavailable.",
                    tool_call_id=tc_id,
                    name=tool_name,
                )
            )

        # Re-add the remaining messages (HumanMessages etc.)
        for msg in after_msgs:
            if msg.__class__.__name__ != "ToolMessage" or getattr(msg, "tool_call_id", None) not in unmatched:
                updates.append(msg)

        await graph.aupdate_state(config, {"messages": updates})
        logger.warning("[streaming] Repaired incomplete tool_calls for thread %s", thread_id)
    except Exception:
        logger.exception("[streaming] Failed to repair incomplete tool_calls")


# ---------------------------------------------------------------------------
# Thread event buffer management
# ---------------------------------------------------------------------------


def get_or_create_thread_buffer(app: Any, thread_id: str) -> ThreadEventBuffer:
    """Get existing or create new ThreadEventBuffer for a thread."""
    buf = app.state.thread_event_buffers.get(thread_id)
    if isinstance(buf, ThreadEventBuffer):
        return buf
    buf = ThreadEventBuffer()
    app.state.thread_event_buffers[thread_id] = buf
    return buf


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

    thread_buf = get_or_create_thread_buffer(app, thread_id)

    async def activity_sink(event: dict) -> None:
        from backend.web.services.event_store import append_event as _append

        seq = await _append(thread_id, f"activity_{thread_id}", event)
        try:
            data = json.loads(event.get("data", "{}")) if isinstance(event.get("data"), str) else event.get("data", {})
        except (json.JSONDecodeError, TypeError):
            data = event.get("data", {})
        if isinstance(data, dict):
            data["_seq"] = seq
            event = {**event, "data": json.dumps(data, ensure_ascii=False)}
        # Only SSE-valid fields: extra metadata (agent_id, agent_name) stays in event_store
        _SSE_FIELDS = frozenset({"event", "data", "id", "retry", "comment"})
        await thread_buf.put({k: v for k, v in event.items() if k in _SSE_FIELDS})

    qm = app.state.queue_manager
    loop = getattr(app.state, "_event_loop", None)

    def wake_handler(item: Any) -> None:
        """Called by enqueue() with the newly-enqueued QueueItem — may run in any thread."""
        if not (hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE)):
            # Agent already ACTIVE — before_model will drain_all on the next LLM call.
            # Emit only this one notice immediately so the frontend sees it in real-time
            # instead of requiring a page refresh. The item is the exact QueueItem just
            # enqueued — no list_queue() needed, so no duplicate emissions.
            if loop and not loop.is_closed():
                async def _emit_one_notice() -> None:
                    await activity_sink({
                        "event": "notice",
                        "data": json.dumps({
                            "content": item.content,
                            "source": getattr(item, "source", None),
                            "notification_type": item.notification_type,
                        }, ensure_ascii=False),
                    })
                loop.call_soon_threadsafe(loop.create_task, _emit_one_notice())
            return

        item = qm.dequeue(thread_id)
        if not item:
            # Lost race to finally block — undo transition
            logger.warning("wake_handler: dequeue returned None for thread %s (race with drain_all), reverting to IDLE", thread_id)
            if hasattr(agent, "runtime"):
                agent.runtime.transition(AgentState.IDLE)
            return

        async def _start_run():
            try:
                start_agent_run(
                    agent, thread_id, item.content, app,
                    message_metadata={
                        "source": getattr(item, "source", None) or "system",
                        "notification_type": item.notification_type,
                        "sender_name": getattr(item, "sender_name", None),
                    },
                )
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

    # Subscribe to EventBus so sub-agent events (spawned via AgentService)
    # flow into this thread's SSE stream.
    try:
        from backend.web.event_bus import get_event_bus
        get_event_bus().subscribe(thread_id, activity_sink)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Producer: runs agent, writes events to ThreadEventBuffer
# ---------------------------------------------------------------------------


async def _run_agent_to_buffer(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool,
    thread_buf: ThreadEventBuffer,
    run_id: str,
    message_metadata: dict[str, Any] | None = None,
) -> None:
    """Run agent execution and write all SSE events into *thread_buf*."""
    from backend.web.services.event_store import append_event

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
        await thread_buf.put(event)

    task = None
    stream_gen = None
    pending_tool_calls: dict[str, dict] = {}
    try:
        config = {"configurable": {"thread_id": thread_id, "run_id": run_id}}
        if hasattr(agent, "_current_model_config"):
            config["configurable"].update(agent._current_model_config)
        set_current_thread_id(thread_id)
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
            thread_data = app.state.thread_repo.get_by_id(thread_id) if hasattr(app.state, "thread_repo") else None
            obs_provider = thread_data.get("observation_provider") if thread_data else None

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

        # Repair broken thread state: if last AIMessage has tool_calls without
        # matching ToolMessages, inject synthetic error ToolMessages so the LLM
        # won't reject the message history.
        await _repair_incomplete_tool_calls(agent, config)

        # Emit notice BEFORE run_start when this run was triggered by a queue notification.
        src = (message_metadata or {}).get("source")
        if src and src != "owner":
            await emit({
                "event": "notice",
                "data": json.dumps({
                    "content": message,
                    "source": src,
                    "notification_type": (message_metadata or {}).get("notification_type"),
                }, ensure_ascii=False),
            })

        # @@@run-source-tracking — set on runtime so tell_owner can check context
        if hasattr(agent, "runtime"):
            agent.runtime.current_run_source = src or "owner"

        # @@@display-projection-sse — run_start carries display_mode for frontend
        display_mode = "collapsed" if src and src != "owner" else "expanded"
        await emit({
            "event": "run_start",
            "data": json.dumps({
                "thread_id": thread_id,
                "run_id": run_id,
                "source": src,
                "sender_name": (message_metadata or {}).get("sender_name"),
                "display_mode": display_mode,
            }),
        })

        if message_metadata:
            from langchain_core.messages import HumanMessage
            _initial_input: dict | None = {"messages": [HumanMessage(content=message, metadata=message_metadata)]}
        else:
            _initial_input = {"messages": [{"role": "user", "content": message}]}

        async def run_agent_stream(input_data: dict | None = _initial_input):
            chunk_count = 0
            # @@@astream-reentry — LangGraph's astream(input) silently returns
            # 0 chunks when the graph is at __end__ (completed previous run).
            # The fix: always use aupdate_state to inject input, then astream(None).
            # This works for both fresh threads (no checkpoint) and existing ones.
            if input_data is not None:
                pre_state = await agent.agent.aget_state(config)
                has_checkpoint = pre_state.values is not None and len(pre_state.values.get("messages", [])) > 0
                if has_checkpoint:
                    # Existing thread: inject message via aupdate_state, then resume
                    await agent.agent.aupdate_state(config, input_data, as_node="__start__")
                    effective_input = None
                else:
                    # Fresh thread: direct astream works fine
                    effective_input = input_data
            else:
                effective_input = input_data

            async for chunk in agent.agent.astream(
                effective_input,
                config=config,
                stream_mode=["messages", "updates"],
            ):
                chunk_count += 1
                yield chunk
            logger.debug("[stream] thread=%s STREAM DONE chunks=%d", thread_id[:15], chunk_count)

        MAX_STREAM_RETRIES = 10

        def _is_retryable_stream_error(err: Exception) -> bool:
            try:
                import httpx
                return isinstance(err, (
                    httpx.RemoteProtocolError,
                    httpx.ReadError,
                ))
            except ImportError:
                return False

        stream_attempt = 0
        while True:  # 外层重试循环
            # First attempt sends the user message; retries pass None so LangGraph
            # resumes from the last checkpoint without re-appending the user message.
            stream_gen = run_agent_stream(_initial_input if stream_attempt == 0 else None)
            task = asyncio.create_task(stream_gen.__anext__())
            app.state.thread_tasks[thread_id] = task
            stream_err: Exception | None = None

            while True:  # 内层 chunk 循环
                try:
                    chunk = await task
                    task = asyncio.create_task(stream_gen.__anext__())
                    app.state.thread_tasks[thread_id] = task
                except StopAsyncIteration:
                    break
                except Exception as err:
                    stream_err = err
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

                        # Early tool_call emission: LangGraph streams tool_call_chunks in real-time
                        # but the "updates" mode only fires after the full LLM response is generated.
                        # By emitting tool_call as soon as we see the first chunk with name+id,
                        # the UI can show the tool name immediately (typically within 1 second of
                        # LLM start) rather than waiting for the full generation (3-8 seconds).
                        for tc_chunk in getattr(msg_chunk, "tool_call_chunks", []):
                            tc_id = tc_chunk.get("id")
                            tc_name = tc_chunk.get("name", "")
                            if tc_id and tc_name and tc_id not in emitted_tool_call_ids:
                                emitted_tool_call_ids.add(tc_id)
                                pending_tool_calls[tc_id] = {"name": tc_name, "args": {}}
                                # @@@display-projection-sse — tell_owner/ask_owner punch through
                                tc_display = "punch_through" if tc_name in ("tell_owner", "ask_owner") else None
                                tc_data = {"id": tc_id, "name": tc_name, "args": {}}
                                if tc_display:
                                    tc_data["display_mode"] = tc_display
                                await emit(
                                    {
                                        "event": "tool_call",
                                        "data": json.dumps(tc_data, ensure_ascii=False),
                                    },
                                    message_id=chunk_msg_id,
                                )
                                # Also update status so ThinkingIndicator shows current tool
                                if hasattr(agent, "runtime"):
                                    status = agent.runtime.get_status_dict()
                                    status["current_tool"] = tc_name
                                    await emit(
                                        {
                                            "event": "status",
                                            "data": json.dumps(status, ensure_ascii=False),
                                        }
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
                                # A6: inject run_id into message metadata
                                if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
                                    msg.metadata["run_id"] = run_id
                                for tc in getattr(msg, "tool_calls", []):
                                    tc_id = tc.get("id")
                                    full_args = tc.get("args", {})
                                    if tc_id and tc_id not in emitted_tool_call_ids:
                                        emitted_tool_call_ids.add(tc_id)
                                        pending_tool_calls[tc_id] = {
                                            "name": tc.get("name", "unknown"),
                                            "args": full_args,
                                        }
                                    # Always emit from updates mode — carries complete args.
                                    # Early emission (messages mode) sends args:{} for real-time
                                    # tool name display; this emission delivers the full args.
                                    await emit(
                                        {
                                            "event": "tool_call",
                                            "data": json.dumps(
                                                {
                                                    "id": tc_id,
                                                    "name": tc.get("name", "unknown"),
                                                    "args": full_args,
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
                                # A6: inject run_id into ToolMessage metadata
                                if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
                                    msg.metadata["run_id"] = run_id
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
                    await emit(act_event)

            if stream_err is None:
                break  # 正常完成，退出外层重试循环

            if _is_retryable_stream_error(stream_err) and stream_attempt < MAX_STREAM_RETRIES:
                stream_attempt += 1
                wait = max(min(2 ** stream_attempt, 30) + random.uniform(-1.0, 1.0), 1.0)
                await emit({"event": "retry", "data": json.dumps({
                    "attempt": stream_attempt,
                    "max_attempts": MAX_STREAM_RETRIES,
                    "wait_seconds": round(wait, 1),
                }, ensure_ascii=False)})
                await stream_gen.aclose()
                await asyncio.sleep(wait)
            else:
                traceback.print_exc()
                await emit({"event": "error", "data": json.dumps(
                    {"error": str(stream_err)}, ensure_ascii=False)})
                break

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

        # @@@A6-disabled — aupdate_state after a completed run leaves the graph
        # at __end__, causing the NEXT astream(new_input) to produce 0 chunks.
        # This broke multi-run threads (e.g. external message delivery).
        # run_id is available from run_start SSE event; no need to patch checkpoint.
        # See: https://github.com/langchain-ai/langgraph/issues/XXX

        # A5: emit run_done instead of done (persistent buffer — no mark_done)
        await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
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
        # Also emit run_done so frontend knows the run ended
        await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
    except Exception as e:
        traceback.print_exc()
        await emit({"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)})
        await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
    finally:
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
        # ThreadEventBuffer is persistent — do NOT mark_done or pop
        app.state.thread_tasks.pop(thread_id, None)
        if stream_gen is not None:
            await stream_gen.aclose()
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            agent.runtime.transition(AgentState.IDLE)

        # Check for pending board tasks on idle
        taskboard_svc = getattr(agent, '_taskboard_service', None)
        if taskboard_svc is not None and taskboard_svc.auto_claim:
            try:
                next_task = await taskboard_svc.on_idle()
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
    item = None
    try:
        qm = app.state.queue_manager
        item = qm.dequeue(thread_id)
        if item and app:
            if hasattr(agent, "runtime") and agent.runtime.transition(AgentState.ACTIVE):
                start_agent_run(agent, thread_id, item.content, app,
                                message_metadata={
                                    "source": item.source or "system",
                                    "notification_type": item.notification_type,
                                    "sender_name": item.sender_name,
                                })
    except Exception:
        logger.exception("Failed to consume followup queue for thread %s", thread_id)
        # Re-enqueue the message if it was already dequeued to prevent data loss
        if item:
            try:
                app.state.queue_manager.enqueue(item.content, thread_id, notification_type=item.notification_type)
            except Exception:
                logger.error("Failed to re-enqueue followup for thread %s — message lost: %.200s", thread_id, item.content)


# ---------------------------------------------------------------------------
# Orchestrator: creates run on persistent ThreadEventBuffer
# ---------------------------------------------------------------------------


def start_agent_run(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool = False,
    message_metadata: dict[str, Any] | None = None,
) -> str:
    """Launch agent producer on the persistent ThreadEventBuffer. Returns run_id."""
    thread_buf = get_or_create_thread_buffer(app, thread_id)
    run_id = str(_uuid.uuid4())
    bg_task = asyncio.create_task(
        _run_agent_to_buffer(agent, thread_id, message, app, enable_trajectory, thread_buf, run_id, message_metadata)
    )
    # Store the background task so cancel_run can still cancel it
    app.state.thread_tasks[thread_id] = bg_task
    return run_id


# ---------------------------------------------------------------------------
# Consumer: persistent thread event stream
# ---------------------------------------------------------------------------


async def observe_thread_events(
    thread_buf: ThreadEventBuffer,
    after: int = 0,
) -> AsyncGenerator[dict[str, str], None]:
    """Consume events from a persistent ThreadEventBuffer. Yields SSE event dicts.

    Unlike observe_run_events, this never terminates on its own — the client
    disconnect (or server shutdown) closes the connection.
    run_done is a flow event, not a terminal signal.
    """
    yield {"retry": 5000}

    # Always start from the beginning of the ring buffer.
    # For after=0 (new connection): replay all buffered events so we never miss
    # events emitted between postRun and SSE connect (race condition fix).
    # For after>0 (reconnect): start from ring start, filter by _seq below.
    cursor = 0

    while True:
        events, cursor = await thread_buf.read_with_timeout(cursor, timeout=30)
        if events is None:
            yield {"comment": "keepalive"}
            continue
        if not events:
            continue
        for event in events:
            parsed_data = None
            try:
                parsed_data = json.loads(event.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            if after > 0 and isinstance(parsed_data, dict):
                if parsed_data.get("_seq", 0) <= after:
                    continue

            seq_id = str(parsed_data["_seq"]) if isinstance(parsed_data, dict) and "_seq" in parsed_data else None
            if seq_id:
                yield {**event, "id": seq_id}
            else:
                yield event


async def observe_run_events(
    buf: RunEventBuffer,
    after: int = 0,
) -> AsyncGenerator[dict[str, str], None]:
    """Consume events from a RunEventBuffer (subagent streams only). Yields SSE event dicts."""
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
            parsed_data = None
            try:
                parsed_data = json.loads(event.get("data", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            if after > 0 and isinstance(parsed_data, dict):
                if parsed_data.get("_seq", 0) <= after:
                    continue

            seq_id = str(parsed_data["_seq"]) if isinstance(parsed_data, dict) and "_seq" in parsed_data else None
            if seq_id:
                yield {**event, "id": seq_id}
            else:
                yield event

