import logging
from typing import Any

from backend.threads.events.buffer import ThreadEventBuffer
from backend.threads.events.store import append_event as _append_event
from backend.threads.events.store import cleanup_old_runs
from backend.threads.run import buffer_wiring as _run_buffer_wiring
from backend.threads.run import cancellation as _run_cancellation
from backend.threads.run import emit as _run_emit
from backend.threads.run import entrypoints as _run_entrypoints
from backend.threads.run import execution as _run_execution
from backend.threads.run import followups as _run_followups
from backend.threads.run import lifecycle as _run_lifecycle

logger = logging.getLogger(__name__)


def _log_captured_exception(message: str, err: BaseException) -> None:
    logger.error(
        message,
        exc_info=(type(err), err, err.__traceback__),
    )


def _ensure_thread_handlers(agent: Any, thread_id: str, app: Any) -> None:
    _run_buffer_wiring._append_event = _append_event
    _run_buffer_wiring._start_agent_run = start_agent_run
    _run_buffer_wiring.ensure_thread_handlers(agent, thread_id, app)


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
    _run_execution.prime_sandbox = _run_lifecycle.prime_sandbox
    _run_execution.repair_incomplete_tool_calls = _run_lifecycle.repair_incomplete_tool_calls
    _run_execution.write_cancellation_markers = _run_lifecycle.write_cancellation_markers
    _run_execution.persist_cancelled_run_input_if_missing = _persist_cancelled_run_input_if_missing
    _run_execution.flush_cancelled_owner_steers = _flush_cancelled_owner_steers
    _run_execution.emit_queued_terminal_followups = _emit_queued_terminal_followups
    _run_execution.consume_followup_queue = _consume_followup_queue
    _run_execution.cleanup_old_runs = cleanup_old_runs
    _run_execution.log_captured_exception = _log_captured_exception
    _run_emit.append_event = _append_event
    _run_buffer_wiring._append_event = _append_event
    # @@@run-buffer-borrowed-typing-tracker - borrow chat-owned typing state at the wrapper boundary.
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
        typing_tracker=(
            getattr(runtime_state, "typing_tracker", None)
            if (runtime_state := getattr(app.state, "threads_runtime_state", None)) is not None
            else None
        ),
    )


async def _consume_followup_queue(agent: Any, thread_id: str, app: Any) -> None:
    _run_followups._start_agent_run = start_agent_run
    await _run_followups.consume_followup_queue(agent, thread_id, app)


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
    _run_entrypoints._get_or_create_thread_buffer = _run_buffer_wiring.get_or_create_thread_buffer
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
    from backend.threads.sandbox_resolution import resolve_thread_sandbox
    from backend.web.utils.serializers import extract_text_content

    _run_entrypoints._start_agent_run = start_agent_run
    _run_entrypoints._resolve_thread_sandbox = resolve_thread_sandbox
    _run_entrypoints._ensure_thread_handlers = _ensure_thread_handlers
    _run_entrypoints._get_or_create_thread_buffer = _run_buffer_wiring.get_or_create_thread_buffer
    _run_entrypoints._extract_text_content = extract_text_content
    return await _run_entrypoints.run_child_thread_live(
        agent,
        thread_id,
        message,
        app,
        input_messages=input_messages,
    )
