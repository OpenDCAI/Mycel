"""SSE streaming service for agent execution."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from backend.thread_runtime.run import buffer_wiring as _run_buffer_wiring
from backend.thread_runtime.run import cancellation as _run_cancellation
from backend.thread_runtime.run import emit as _run_emit
from backend.thread_runtime.run import entrypoints as _run_entrypoints
from backend.thread_runtime.run import execution as _run_execution
from backend.thread_runtime.run import followups as _run_followups
from backend.thread_runtime.run import input_construction as _run_input_construction
from backend.thread_runtime.run import lifecycle as _run_lifecycle
from backend.thread_runtime.run import observer as _run_observer
from backend.web.services.event_buffer import RunEventBuffer, ThreadEventBuffer
from backend.web.services.event_store import append_event as _append_event
from backend.web.services.event_store import cleanup_old_runs
from core.runtime.notifications import is_terminal_background_notification
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
    _run_buffer_wiring._append_event = _append_event
    _run_buffer_wiring._start_agent_run = start_agent_run
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
    _run_execution.ensure_thread_handlers = _ensure_thread_handlers
    _run_execution.prime_sandbox = prime_sandbox
    _run_execution.repair_incomplete_tool_calls = _repair_incomplete_tool_calls
    _run_execution.write_cancellation_markers = write_cancellation_markers
    _run_execution.persist_cancelled_run_input_if_missing = _persist_cancelled_run_input_if_missing
    _run_execution.flush_cancelled_owner_steers = _flush_cancelled_owner_steers
    _run_execution.emit_queued_terminal_followups = _emit_queued_terminal_followups
    _run_execution.consume_followup_queue = _consume_followup_queue
    _run_execution.cleanup_old_runs = cleanup_old_runs
    _run_execution.log_captured_exception = _log_captured_exception
    _run_emit.append_event = _append_event
    _run_buffer_wiring._append_event = _append_event
    return await _run_execution.run_agent_to_buffer(
        agent=agent,
        thread_id=thread_id,
        message=message,
        app=app,
        enable_trajectory=enable_trajectory,
        thread_buf=thread_buf,
        run_id=run_id,
        message_metadata=message_metadata,
        input_messages=input_messages,
    )


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
