"""SSE streaming service for agent execution."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from backend.thread_runtime.run import activity_bridge as _run_activity_bridge
from backend.thread_runtime.run import buffer_wiring as _run_buffer_wiring
from backend.thread_runtime.run import cancellation as _run_cancellation
from backend.thread_runtime.run import emit as _run_emit
from backend.thread_runtime.run import entrypoints as _run_entrypoints
from backend.thread_runtime.run import followups as _run_followups
from backend.thread_runtime.run import input_construction as _run_input_construction
from backend.thread_runtime.run import lifecycle as _run_lifecycle
from backend.thread_runtime.run import observation as _run_observation
from backend.thread_runtime.run import observer as _run_observer
from backend.thread_runtime.run import prologue as _run_prologue
from backend.thread_runtime.run import stream_loop as _run_stream_loop
from backend.thread_runtime.run import tool_call_dedup as _run_tool_call_dedup
from backend.thread_runtime.run import trajectory as _run_trajectory
from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.event_store import cleanup_old_runs
from core.runtime.middleware.monitor import AgentState
from core.runtime.notifications import is_terminal_background_notification
from sandbox.thread_context import set_current_run_id, set_current_thread_id
from storage.contracts import RunEventRepo

logger = logging.getLogger(__name__)

type SSEEvent = dict[str, str | int]


def _log_captured_exception(message: str, err: BaseException) -> None:
    logger.error(
        message,
        exc_info=(type(err), err, err.__traceback__),
    )


def _resolve_run_event_repo(agent: Any) -> RunEventRepo:
    return _run_emit.resolve_run_event_repo(agent)


def _augment_system_prompt_for_terminal_followthrough(system_prompt: Any) -> Any:
    return _run_input_construction.augment_system_prompt_for_terminal_followthrough(system_prompt)


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
    run_event_repo = _resolve_run_event_repo(agent)
    display_builder = app.state.display_builder
    emit = _run_emit.build_emit(
        thread_id=thread_id,
        run_id=run_id,
        thread_buf=thread_buf,
        run_event_repo=run_event_repo,
        display_builder=display_builder,
    )

    pending_tool_calls: dict[str, dict] = {}
    output_parts: list[str] = []
    trajectory_status = "completed"

    def prompt_restore() -> None:
        return None

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

        drain_activity_events, attach_activity_bridge, detach_activity_bridge = _run_activity_bridge.build_activity_bridge(
            runtime=getattr(agent, "runtime", None),
            emit=emit,
        )
        attach_activity_bridge()

        # Bind per-thread handlers (idempotent — safe across runs)
        _ensure_thread_handlers(agent, thread_id, app)

        # @@@lazy-sandbox — only prime sandbox eagerly when attachments need syncing.
        # Without attachments, sandbox starts lazily on first tool call.
        if hasattr(agent, "_sandbox") and message_metadata and message_metadata.get("attachments"):
            await prime_sandbox(agent, thread_id)

        dedup = _run_tool_call_dedup.ToolCallDedup()
        try:
            # @@@checkpoint-dedup — pre-populate from checkpoint so replayed tool_calls
            # and their ToolMessages from astream(None) are skipped.
            await dedup.prepopulate_from_checkpoint(agent, config)
        except Exception:
            logger.warning("[stream:checkpoint] failed to pre-populate tc_ids for thread=%s", thread_id[:15], exc_info=True)
        logger.debug(
            "[stream:checkpoint] thread=%s pre-populated dedup state",
            thread_id[:15],
        )

        # Repair broken thread state: if last AIMessage has tool_calls without
        # matching ToolMessages, inject synthetic error ToolMessages so the LLM
        # won't reject the message history.
        await _repair_incomplete_tool_calls(agent, config)

        src, ntype = await _run_prologue.emit_run_prologue(
            agent=agent,
            thread_id=thread_id,
            message=message,
            message_metadata=message_metadata,
            run_id=run_id,
            app=app,
            emit=emit,
        )

        _initial_input, prompt_restore = await _run_input_construction.build_initial_input(
            message=message,
            message_metadata=message_metadata,
            input_messages=input_messages,
            agent=agent,
            app=app,
            thread_id=thread_id,
            emit=emit,
            emit_queued_terminal_followups=_emit_queued_terminal_followups,
        )

        trajectory_status = await _run_stream_loop.run_stream_loop(
            agent=agent,
            config=config,
            initial_input=_initial_input,
            emit=emit,
            dedup=dedup,
            drain_activity_events=drain_activity_events,
            pending_tool_calls=pending_tool_calls,
            output_parts=output_parts,
            thread_id=thread_id,
            run_id=run_id,
            log_captured_exception=_log_captured_exception,
        )

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
        prompt_restore()
        # @@@typing-lifecycle-stop — guaranteed cleanup even on crash/cancel
        typing_tracker = getattr(app.state, "typing_tracker", None)
        if typing_tracker is not None:
            typing_tracker.stop(thread_id)
        # Detach per-run event callback (per-thread handlers survive across runs)
        detach_activity_bridge()
        # Flush observation handler
        flush_observation()
        # ThreadEventBuffer is persistent — do NOT mark_done or pop
        app.state.thread_tasks.pop(thread_id, None)
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
