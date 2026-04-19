"""SSE streaming service for agent execution."""

import asyncio
import json
import logging
import random
from collections.abc import AsyncGenerator
from typing import Any

from backend.thread_runtime.run import buffer_wiring as _run_buffer_wiring
from backend.thread_runtime.run import cancellation as _run_cancellation
from backend.thread_runtime.run import entrypoints as _run_entrypoints
from backend.thread_runtime.run import followups as _run_followups
from backend.thread_runtime.run import lifecycle as _run_lifecycle
from backend.thread_runtime.run import observation as _run_observation
from backend.thread_runtime.run import observer as _run_observer
from backend.thread_runtime.run import trajectory as _run_trajectory
from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.event_store import cleanup_old_runs
from backend.web.utils.serializers import extract_text_content
from core.runtime.middleware.monitor import AgentState
from core.runtime.notifications import is_terminal_background_notification
from sandbox.thread_context import set_current_run_id, set_current_thread_id
from storage.contracts import RunEventRepo

logger = logging.getLogger(__name__)

type SSEEvent = dict[str, str | int]

_TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE = (
    "Terminal background completion notifications require an explicit assistant followthrough. "
    "Treat these notifications as fresh inputs that need a visible assistant reply. "
    "You must produce at least one visible assistant message for them; "
    "do not stay silent and do not end the run after only surfacing a notice. "
    "Do not call TaskOutput or TaskStop for a terminal notification. "
    "If no further tool is truly needed, answer directly in natural language "
    "and briefly acknowledge the completion, failure, or cancellation honestly."
)


def _log_captured_exception(message: str, err: BaseException) -> None:
    logger.error(
        message,
        exc_info=(type(err), err, err.__traceback__),
    )


def _resolve_run_event_repo(agent: Any) -> RunEventRepo:
    storage_container = getattr(agent, "storage_container", None)
    if storage_container is None:
        raise RuntimeError("streaming_service requires agent.storage_container.run_event_repo()")

    # @@@runtime-storage-consumer - runtime run lifecycle must consume injected storage container, not assignment-only wiring.
    run_event_repo = getattr(storage_container, "run_event_repo", None)
    if not callable(run_event_repo):
        raise RuntimeError("streaming_service requires agent.storage_container.run_event_repo()")
    repo = run_event_repo()
    if not isinstance(repo, RunEventRepo):
        raise RuntimeError("agent.storage_container.run_event_repo() returned an invalid repo")
    return repo


def _augment_system_prompt_for_terminal_followthrough(system_prompt: Any) -> Any:
    content = getattr(system_prompt, "content", None)
    if not isinstance(content, str):
        return system_prompt
    if _TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE in content:
        return system_prompt
    # @@@terminal-followthrough-system-note - live models can otherwise treat
    # terminal background notifications as internal reminders and emit no
    # assistant text, leaving caller surfaces notice-only.
    return system_prompt.__class__(content=f"{content}\n\n{_TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE}")


async def prime_sandbox(agent: Any, thread_id: str) -> None:
    await _run_lifecycle.prime_sandbox(agent, thread_id)


async def write_cancellation_markers(
    agent: Any,
    config: dict[str, Any],
    pending_tool_calls: dict[str, dict],
) -> list[str]:
    return await _run_lifecycle.write_cancellation_markers(agent, config, pending_tool_calls)


async def _repair_incomplete_tool_calls(agent: Any, config: dict[str, Any]) -> None:
    await _run_lifecycle.repair_incomplete_tool_calls(agent, config)


# ---------------------------------------------------------------------------
# Thread event buffer management
# ---------------------------------------------------------------------------


def get_or_create_thread_buffer(app: Any, thread_id: str) -> ThreadEventBuffer:
    return _run_buffer_wiring.get_or_create_thread_buffer(app, thread_id)


# ---------------------------------------------------------------------------
# Per-thread handler setup (idempotent, survives across runs)
# ---------------------------------------------------------------------------


def _ensure_thread_handlers(agent: Any, thread_id: str, app: Any) -> None:
    _run_buffer_wiring.ensure_thread_handlers(agent, thread_id, app)


def _is_terminal_background_notification_message(
    message: str,
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    return is_terminal_background_notification(
        message,
        source=source,
        notification_type=notification_type,
    )


def _partition_terminal_followups(items: list[Any]) -> tuple[list[Any], list[Any]]:
    return _run_cancellation.partition_terminal_followups(items)


def _message_metadata_dict(message_metadata: dict[str, Any] | None) -> dict[str, Any]:
    return dict(message_metadata or {})


def _message_already_persisted(message: Any, *, content: str, metadata: dict[str, Any]) -> bool:
    if message.__class__.__name__ != "HumanMessage":
        return False
    if getattr(message, "content", None) != content:
        return False
    return (getattr(message, "metadata", None) or {}) == metadata


async def _persist_cancelled_run_input_if_missing(
    *,
    agent: Any,
    config: dict[str, Any],
    message: str,
    message_metadata: dict[str, Any] | None,
) -> None:
    await _run_cancellation.persist_cancelled_run_input_if_missing(
        agent=agent,
        config=config,
        message=message,
        message_metadata=message_metadata,
    )


def _is_owner_steer_followup_message(
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    return source == "owner" and notification_type == "steer"


async def _persist_cancelled_owner_steers(
    *,
    agent: Any,
    config: dict[str, Any],
    items: list[dict[str, str | None]],
) -> None:
    await _run_cancellation.persist_cancelled_owner_steers(
        agent=agent,
        config=config,
        items=items,
    )


async def _flush_cancelled_owner_steers(
    *,
    agent: Any,
    config: dict[str, Any],
    thread_id: str,
    app: Any,
) -> None:
    await _run_cancellation.flush_cancelled_owner_steers(
        agent=agent,
        config=config,
        thread_id=thread_id,
        app=app,
    )


async def _emit_queued_terminal_followups(
    *,
    app: Any,
    thread_id: str,
    emit: Any,
) -> list[dict[str, str | None]]:
    return await _run_cancellation.emit_queued_terminal_followups(
        app=app,
        thread_id=thread_id,
        emit=emit,
    )


# ---------------------------------------------------------------------------
# Producer: runs agent, writes events to ThreadEventBuffer
# ---------------------------------------------------------------------------


async def _run_agent_to_buffer(  # pyright: ignore[reportGeneralTypeIssues]  # @@@nu59-complexity-honesty
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool,
    thread_buf: ThreadEventBuffer,
    run_id: str,
    message_metadata: dict[str, Any] | None = None,
    input_messages: list[Any] | None = None,
) -> str:
    """Run agent execution and write all SSE events into *thread_buf*."""
    from backend.web.services.event_store import append_event

    run_event_repo = _resolve_run_event_repo(agent)

    # @@@display-builder — compute display deltas alongside raw events
    display_builder = app.state.display_builder

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

        # Compute display delta and emit it alongside the raw event.
        event_type = event.get("event", "")
        if event_type and isinstance(data, dict):
            delta = display_builder.apply_event(thread_id, event_type, data)
            if delta:
                # @@@display-delta-source-seq - replay after-filter only knows raw
                # event seqs. Carry the source seq onto the derived delta so a
                # reconnect after GET /thread can skip stale display_delta
                # replays instead of rebuilding the same thread a second time.
                delta["_seq"] = seq
                await thread_buf.put(
                    {
                        "event": "display_delta",
                        "data": json.dumps(delta, ensure_ascii=False),
                    }
                )

    task = None
    stream_gen = None
    pending_tool_calls: dict[str, dict] = {}
    output_parts: list[str] = []
    trajectory_status = "completed"
    try:
        config = {"configurable": {"thread_id": thread_id, "run_id": run_id}}
        if hasattr(agent, "_current_model_config"):
            config["configurable"].update(agent._current_model_config)
        set_current_thread_id(thread_id)
        # @@@web-run-context - web runs have no TUI checkpoint; use run_id to group file ops per run.
        set_current_run_id(run_id)

        trajectory_scope = _run_trajectory.build_trajectory_scope(
            agent=agent,
            thread_id=thread_id,
            run_id=run_id,
            user_message=message,
            enable_trajectory=enable_trajectory,
        )
        if trajectory_scope is not None:
            trajectory_scope.inject_callback(config)

        _obs_handler, _obs_active, flush_observation = _run_observation.build_observation(app, thread_id, config)

        # Real-time activity event callback (replaces post-hoc batch drain)
        activity_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

        def on_activity_event(event: dict) -> None:
            try:
                activity_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Backpressure: drop under overload

        async def drain_activity_events() -> None:
            while not activity_queue.empty():
                try:
                    act_event = activity_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                logger.info("[stream:drain] emitting activity event: %s", act_event.get("event", "?"))
                await emit(act_event)

        if hasattr(agent, "runtime"):
            agent.runtime.set_event_callback(on_activity_event)

        # Bind per-thread handlers (idempotent — safe across runs)
        _ensure_thread_handlers(agent, thread_id, app)

        # @@@lazy-sandbox — only prime sandbox eagerly when attachments need syncing.
        # Without attachments, sandbox starts lazily on first tool call.
        if hasattr(agent, "_sandbox") and message_metadata and message_metadata.get("attachments"):
            await prime_sandbox(agent, thread_id)

        emitted_tool_call_ids: set[str] = set()

        # @@@checkpoint-dedup — pre-populate from checkpoint so replayed tool_calls
        # and their ToolMessages from astream(None) are skipped.
        checkpoint_tc_ids: set[str] = set()
        try:
            pre_state = await agent.agent.aget_state(config)
            if pre_state and pre_state.values:
                for msg in pre_state.values.get("messages", []):
                    if msg.__class__.__name__ == "AIMessage":
                        for tc in getattr(msg, "tool_calls", []):
                            tc_id = tc.get("id")
                            if tc_id:
                                checkpoint_tc_ids.add(tc_id)
        except Exception:
            logger.warning("[stream:checkpoint] failed to pre-populate tc_ids for thread=%s", thread_id[:15], exc_info=True)
        emitted_tool_call_ids.update(checkpoint_tc_ids)
        logger.debug("[stream:checkpoint] thread=%s pre-populated %d tc_ids", thread_id[:15], len(checkpoint_tc_ids))

        # Repair broken thread state: if last AIMessage has tool_calls without
        # matching ToolMessages, inject synthetic error ToolMessages so the LLM
        # won't reject the message history.
        await _repair_incomplete_tool_calls(agent, config)

        meta = message_metadata or {}
        src = meta.get("source")

        # @@@run-source-tracking — set on runtime for source tracking
        if hasattr(agent, "runtime"):
            agent.runtime.current_run_source = src or "owner"

        # Track last-active for sidebar sorting
        import time as _time

        app.state.thread_last_active[thread_id] = _time.time()

        # @@@user-entry — emit user_message so display_builder can add a UserMessage
        # entry.  Skip for steers — wake_handler already emitted user_message at
        # enqueue time (@@@steer-instant-feedback).
        # Note: is_steer is NOT persisted in queue, so check notification_type too.
        is_steer = meta.get("is_steer") or meta.get("notification_type") == "steer"
        if meta.get("ask_user_question_answered"):
            await emit(
                {
                    "event": "user_message",
                    "data": json.dumps(
                        {
                            "content": "",
                            "showing": False,
                            "ask_user_question_answered": meta["ask_user_question_answered"],
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        elif (not src or src == "owner") and not is_steer:
            # @@@strip-for-display — agent sees full content (with system-reminder),
            # frontend sees clean text (tags stripped)
            from backend.web.utils.serializers import strip_system_tags

            display_content = strip_system_tags(message) if "<system-reminder>" in message else message
            await emit(
                {
                    "event": "user_message",
                    "data": json.dumps(
                        {
                            "content": display_content,
                            "showing": True,
                            **({"attachments": meta["attachments"]} if meta.get("attachments") else {}),
                        },
                        ensure_ascii=False,
                    ),
                }
            )

        await emit(
            {
                "event": "run_start",
                "data": json.dumps(
                    {
                        "thread_id": thread_id,
                        "run_id": run_id,
                        "source": src,
                        "sender_name": meta.get("sender_name"),
                        "showing": True,
                    }
                ),
            }
        )

        # @@@run-notice — emit notice right after run_start so frontend folds it
        # into the (re)opened turn. Mirror the cold-path DisplayBuilder rule:
        # any source=system message is a notice; external notices stay chat-only.
        ntype = meta.get("notification_type")
        if src == "system" or (src == "external" and ntype == "chat"):
            await emit(
                {
                    "event": "notice",
                    "data": json.dumps(
                        {
                            "content": message,
                            "source": src,
                            "notification_type": ntype,
                        },
                        ensure_ascii=False,
                    ),
                }
            )

        terminal_followthrough_items: list[dict[str, str | None]] | None = None
        original_system_prompt = None
        # @@@terminal-followthrough-reentry - terminal background completions
        # still surface as durable notices first, but they must then re-enter the
        # model as a real followthrough turn instead of terminating at notice-only.
        if _is_terminal_background_notification_message(
            message,
            source=src,
            notification_type=ntype,
        ):
            terminal_followthrough_items = [
                {
                    "content": message,
                    "source": src or "system",
                    "notification_type": ntype,
                }
            ]
            terminal_followthrough_items.extend(await _emit_queued_terminal_followups(app=app, thread_id=thread_id, emit=emit))
            if hasattr(agent, "agent") and hasattr(agent.agent, "system_prompt"):
                original_system_prompt = agent.agent.system_prompt
                agent.agent.system_prompt = _augment_system_prompt_for_terminal_followthrough(original_system_prompt)

        if terminal_followthrough_items:
            from langchain_core.messages import HumanMessage

            _initial_input = {
                "messages": [
                    HumanMessage(
                        content=str(item["content"] or ""),
                        metadata={
                            "source": item["source"] or "system",
                            "notification_type": item["notification_type"],
                        },
                    )
                    for item in terminal_followthrough_items
                ]
            }
        elif input_messages is not None:
            _initial_input = {"messages": input_messages}
        elif message_metadata:
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
            effective_input = input_data
            if input_data is not None:
                pre_state = await agent.agent.aget_state(config)
                has_checkpoint = pre_state.values is not None and len(pre_state.values.get("messages", [])) > 0
                if has_checkpoint:
                    # Existing thread: inject message via aupdate_state, then resume
                    await agent.agent.aupdate_state(config, input_data, as_node="__start__")
                    effective_input = None

            async for chunk in agent.agent.astream(
                effective_input,
                config=config,
                stream_mode=["messages", "updates"],
            ):
                chunk_count += 1
                yield chunk
            logger.debug("[stream] thread=%s STREAM DONE chunks=%d", thread_id[:15], chunk_count)

        max_stream_retries = 10

        def _is_retryable_stream_error(err: Exception) -> bool:
            try:
                import httpx

                return isinstance(
                    err,
                    (
                        httpx.RemoteProtocolError,
                        httpx.ReadError,
                    ),
                )
            except ImportError:
                return False

        stream_attempt = 0
        while True:  # 外层重试循环
            # First attempt sends the user message; retries pass None so LangGraph
            # resumes from the last checkpoint without re-appending the user message.
            stream_gen = run_agent_stream(_initial_input if stream_attempt == 0 else None)
            task = asyncio.create_task(stream_gen.__anext__())
            stream_err: Exception | None = None

            while True:  # 内层 chunk 循环
                try:
                    chunk = await task
                    task = asyncio.create_task(stream_gen.__anext__())
                except StopAsyncIteration:
                    break
                except Exception as err:
                    stream_err = err
                    break
                if not chunk:
                    continue

                # @@@drain-before-chunk — drain activity events BEFORE processing chunk.
                await drain_activity_events()

                if not isinstance(chunk, tuple) or len(chunk) != 2:
                    continue
                mode, data = chunk

                if mode == "messages":
                    msg_chunk, _metadata = data
                    msg_class = msg_chunk.__class__.__name__
                    if msg_class == "AIMessageChunk":
                        # @@@compact-leak-guard — skip chunks from compact's summary LLM call.
                        # Compact sets isCompacting flag; these chunks are internal, not agent output.
                        if hasattr(agent, "runtime") and agent.runtime.state.flags.is_compacting:
                            continue
                        content = extract_text_content(getattr(msg_chunk, "content", ""))
                        chunk_msg_id = getattr(msg_chunk, "id", None)
                        if content:
                            output_parts.append(content)
                            await emit(
                                {
                                    "event": "text",
                                    "data": json.dumps(
                                        {
                                            "content": content,
                                            "showing": True,
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                                message_id=chunk_msg_id,
                            )

                        # Early tool_call emission
                        for tc_chunk in getattr(msg_chunk, "tool_call_chunks", []):
                            tc_id = tc_chunk.get("id")
                            tc_name = tc_chunk.get("name", "")
                            if tc_id and tc_name and tc_id not in emitted_tool_call_ids:
                                emitted_tool_call_ids.add(tc_id)
                                pending_tool_calls[tc_id] = {"name": tc_name, "args": {}}
                                tc_data: dict[str, Any] = {
                                    "id": tc_id,
                                    "name": tc_name,
                                    "args": {},
                                    "showing": True,
                                }
                                await emit(
                                    {
                                        "event": "tool_call",
                                        "data": json.dumps(tc_data, ensure_ascii=False),
                                    },
                                    message_id=chunk_msg_id,
                                )
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

                            if msg_class == "HumanMessage":
                                # @@@mid-turn-notice-parity — hot streaming must use the
                                # same notice contract as cold checkpoint rebuild:
                                # source=system always folds as notice; external stays
                                # limited to chat notifications.
                                meta = getattr(msg, "metadata", None) or {}
                                if meta.get("source") == "system" or (
                                    meta.get("source") == "external" and meta.get("notification_type") == "chat"
                                ):
                                    await emit(
                                        {
                                            "event": "notice",
                                            "data": json.dumps(
                                                {
                                                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                                                    "source": meta.get("source", "external"),
                                                    "notification_type": meta.get("notification_type"),
                                                },
                                                ensure_ascii=False,
                                            ),
                                        }
                                    )
                                continue

                            if msg_class == "AIMessage":
                                ai_msg_id = getattr(msg, "id", None)
                                if hasattr(msg, "metadata") and isinstance(msg.metadata, dict):
                                    msg.metadata["run_id"] = run_id

                                for tc in getattr(msg, "tool_calls", []):
                                    tc_id = tc.get("id")
                                    tc_name = tc.get("name", "unknown")
                                    full_args = tc.get("args", {})
                                    logger.debug(
                                        "[stream:update] tc=%s name=%s dup=%s chk=%s thread=%s",
                                        tc_id or "?",
                                        tc_name,
                                        tc_id in emitted_tool_call_ids,
                                        tc_id in checkpoint_tc_ids,
                                        thread_id,
                                    )
                                    # @@@checkpoint-dedup — skip tool_calls from previous runs
                                    # but allow current run's updates (delivers full args after early emission)
                                    if tc_id and tc_id in checkpoint_tc_ids:
                                        continue
                                    if tc_id and tc_id not in emitted_tool_call_ids:
                                        emitted_tool_call_ids.add(tc_id)
                                        pending_tool_calls[tc_id] = {
                                            "name": tc_name,
                                            "args": full_args,
                                        }
                                    await emit(
                                        {
                                            "event": "tool_call",
                                            "data": json.dumps(
                                                {"id": tc_id, "name": tc_name, "args": full_args, "showing": True},
                                                ensure_ascii=False,
                                            ),
                                        },
                                        message_id=ai_msg_id,
                                    )
                            elif msg_class == "ToolMessage":
                                tc_id = getattr(msg, "tool_call_id", None)
                                tool_msg_id = getattr(msg, "id", None)
                                # @@@checkpoint-dedup — skip replayed ToolMessages
                                if tc_id and tc_id in checkpoint_tc_ids:
                                    continue
                                if tc_id:
                                    pending_tool_calls.pop(tc_id, None)
                                merged_meta = dict(getattr(msg, "metadata", None) or {})
                                tool_result_meta = getattr(msg, "additional_kwargs", {}).get("tool_result_meta")
                                if isinstance(tool_result_meta, dict):
                                    merged_meta = {**tool_result_meta, **merged_meta}
                                merged_meta["run_id"] = run_id
                                tool_name = getattr(msg, "name", "") or ""
                                await emit(
                                    {
                                        "event": "tool_result",
                                        "data": json.dumps(
                                            {
                                                "tool_call_id": tc_id,
                                                "name": tool_name,
                                                "content": str(getattr(msg, "content", "")),
                                                "metadata": merged_meta,
                                                "showing": True,
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
                await drain_activity_events()

            if stream_err is None:
                break  # 正常完成，退出外层重试循环

            # @@@drain-before-stream-error - activity events can happen before
            # the first model chunk. Preserve user-visible notices such as
            # compact_start even when the model call fails immediately.
            await drain_activity_events()

            if _is_retryable_stream_error(stream_err) and stream_attempt < max_stream_retries:
                stream_attempt += 1
                wait = max(min(2**stream_attempt, 30) + random.uniform(-1.0, 1.0), 1.0)
                await emit(
                    {
                        "event": "retry",
                        "data": json.dumps(
                            {
                                "attempt": stream_attempt,
                                "max_attempts": max_stream_retries,
                                "wait_seconds": round(wait, 1),
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                await stream_gen.aclose()
                await asyncio.sleep(wait)
            else:
                trajectory_status = "error"
                _log_captured_exception(
                    f"[streaming] stream failed for thread {thread_id}",
                    stream_err,
                )
                await emit({"event": "error", "data": json.dumps({"error": str(stream_err)}, ensure_ascii=False)})
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
        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_success(agent=agent, trajectory_status=trajectory_status)
            except Exception:
                logger.error("Failed to persist trajectory for thread %s", thread_id, exc_info=True)

        # @@@A6-disabled — aupdate_state after a completed run leaves the graph
        # at __end__, causing the NEXT astream(new_input) to produce 0 chunks.
        # This broke multi-run threads (e.g. external message delivery).
        # run_id is available from run_start SSE event; no need to patch checkpoint.
        # See: https://github.com/langchain-ai/langgraph/issues/XXX

        # A5: emit run_done instead of done (persistent buffer — no mark_done)
        await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
        return "".join(output_parts).strip()
    except asyncio.CancelledError:
        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_cancelled()
            except Exception:
                logger.error("Failed to finalize cancelled trajectory for thread %s", thread_id, exc_info=True)
        cancelled_tool_call_ids = await write_cancellation_markers(agent, config, pending_tool_calls)
        await _persist_cancelled_run_input_if_missing(
            agent=agent,
            config=config,
            message=message,
            message_metadata=message_metadata,
        )
        await _flush_cancelled_owner_steers(
            agent=agent,
            config=config,
            thread_id=thread_id,
            app=app,
        )
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
        return ""
    except Exception as e:
        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_error()
            except Exception:
                logger.error("Failed to finalize errored trajectory for thread %s", thread_id, exc_info=True)
        _log_captured_exception(
            f"[streaming] run failed for thread {thread_id}",
            e,
        )
        await emit({"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)})
        await emit({"event": "run_done", "data": json.dumps({"thread_id": thread_id, "run_id": run_id})})
        return ""
    finally:
        if original_system_prompt is not None and hasattr(agent, "agent") and hasattr(agent.agent, "system_prompt"):
            agent.agent.system_prompt = original_system_prompt
        # @@@typing-lifecycle-stop — guaranteed cleanup even on crash/cancel
        typing_tracker = getattr(app.state, "typing_tracker", None)
        if typing_tracker is not None:
            typing_tracker.stop(thread_id)
        # Detach per-run event callback (per-thread handlers survive across runs)
        if hasattr(agent, "runtime"):
            agent.runtime.set_event_callback(None)
        # Flush observation handler
        flush_observation()
        # ThreadEventBuffer is persistent — do NOT mark_done or pop
        app.state.thread_tasks.pop(thread_id, None)
        if stream_gen is not None:
            await stream_gen.aclose()
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            agent.runtime.transition(AgentState.IDLE)

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
    _run_followups._start_agent_run = start_agent_run
    await _run_followups.consume_followup_queue(agent, thread_id, app)


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
    input_messages: list[Any] | None = None,
) -> str:
    _run_entrypoints._run_agent_to_buffer = _run_agent_to_buffer
    _run_entrypoints._get_or_create_thread_buffer = get_or_create_thread_buffer
    return _run_entrypoints.start_agent_run(
        agent,
        thread_id,
        message,
        app,
        enable_trajectory=enable_trajectory,
        message_metadata=message_metadata,
        input_messages=input_messages,
    )


async def run_child_thread_live(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    *,
    input_messages: list[Any],
) -> str:
    from backend.web.services.agent_pool import resolve_thread_sandbox
    from backend.web.utils.serializers import extract_text_content

    _run_entrypoints._start_agent_run = start_agent_run
    _run_entrypoints._resolve_thread_sandbox = resolve_thread_sandbox
    _run_entrypoints._ensure_thread_handlers = _ensure_thread_handlers
    _run_entrypoints._get_or_create_thread_buffer = get_or_create_thread_buffer
    _run_entrypoints._extract_text_content = extract_text_content
    return await _run_entrypoints.run_child_thread_live(
        agent,
        thread_id,
        message,
        app,
        input_messages=input_messages,
    )


# ---------------------------------------------------------------------------
# Consumer: persistent thread event stream
# ---------------------------------------------------------------------------


async def observe_thread_events(
    thread_buf: ThreadEventBuffer,
    after: int = 0,
) -> AsyncGenerator[SSEEvent, None]:
    async for event in _run_observer.observe_thread_events(thread_buf, after=after):
        yield event


async def observe_run_events(
    buf: RunEventBuffer,
    after: int = 0,
) -> AsyncGenerator[SSEEvent, None]:
    async for event in _run_observer.observe_run_events(buf, after=after):
        yield event


async def _observe_sse_buffer(
    buf: ThreadEventBuffer | RunEventBuffer,
    *,
    after: int,
    stop_on_finish: bool,
) -> AsyncGenerator[SSEEvent, None]:
    async for event in _run_observer.observe_sse_buffer(buf, after=after, stop_on_finish=stop_on_finish):
        yield event
