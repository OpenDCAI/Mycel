"""Execution orchestration helpers for thread runtime runs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.threads.run import activity_bridge as _run_activity_bridge
from backend.threads.run import emit as _run_emit
from backend.threads.run import epilogue as _run_epilogue
from backend.threads.run import input_construction as _run_input_construction
from backend.threads.run import observation as _run_observation
from backend.threads.run import prologue as _run_prologue
from backend.threads.run import stream_loop as _run_stream_loop
from backend.threads.run import tool_call_dedup as _run_tool_call_dedup
from backend.threads.run import trajectory as _run_trajectory
from core.runtime.middleware.monitor import AgentState
from sandbox.thread_context import set_current_run_id, set_current_thread_id

logger = logging.getLogger(__name__)


async def _unbound_async(*_args, **_kwargs):
    raise RuntimeError("thread runtime execution helper was not bound")


def _unbound_sync(*_args, **_kwargs):
    raise RuntimeError("thread runtime execution helper was not bound")


ensure_thread_handlers = _unbound_sync
prime_sandbox = _unbound_async
repair_incomplete_tool_calls = _unbound_async
write_cancellation_markers = _unbound_async
persist_cancelled_run_input_if_missing = _unbound_async
flush_cancelled_owner_steers = _unbound_async
emit_queued_terminal_followups = _unbound_async
consume_followup_queue = _unbound_async
cleanup_old_runs = _unbound_async
log_captured_exception = _unbound_sync


async def run_agent_to_buffer(
    agent: Any,
    thread_id: str,
    message: str,
    app: Any,
    enable_trajectory: bool,
    thread_buf: Any,
    run_id: str,
    message_metadata: dict[str, Any] | None = None,
    input_messages: list[Any] | None = None,
    typing_tracker: Any | None = None,
) -> str:
    run_event_repo = _run_emit.resolve_run_event_repo(agent)
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    display_builder = getattr(runtime_state, "display_builder", None)
    if display_builder is None:
        raise RuntimeError("display_builder is required for thread run execution")
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

        ensure_thread_handlers(agent, thread_id, app)

        if hasattr(agent, "_sandbox") and message_metadata and message_metadata.get("attachments"):
            await prime_sandbox(agent, thread_id)

        dedup = _run_tool_call_dedup.ToolCallDedup()
        try:
            await dedup.prepopulate_from_checkpoint(agent, config)
        except Exception:
            logger.warning("[stream:checkpoint] failed to pre-populate tc_ids for thread=%s", thread_id[:15], exc_info=True)
        logger.debug("[stream:checkpoint] thread=%s pre-populated dedup state", thread_id[:15])

        await repair_incomplete_tool_calls(agent, config)

        await _run_prologue.emit_run_prologue(
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
            emit_queued_terminal_followups=emit_queued_terminal_followups,
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
            log_captured_exception=log_captured_exception,
        )

        if hasattr(agent, "runtime"):
            await _run_epilogue.emit_run_epilogue(
                emit=emit,
                thread_id=thread_id,
                run_id=run_id,
                outcome="success",
                payload={"status": agent.runtime.get_status_dict()},
            )

        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_success(agent=agent, trajectory_status=trajectory_status)
            except Exception:
                logger.error("Failed to persist trajectory for thread %s", thread_id, exc_info=True)

        return "".join(output_parts).strip()
    except asyncio.CancelledError:
        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_cancelled()
            except Exception:
                logger.error("Failed to finalize cancelled trajectory for thread %s", thread_id, exc_info=True)
        cancelled_tool_call_ids = await write_cancellation_markers(agent, config, pending_tool_calls)
        await persist_cancelled_run_input_if_missing(
            agent=agent,
            config=config,
            message=message,
            message_metadata=message_metadata,
        )
        await flush_cancelled_owner_steers(
            agent=agent,
            config=config,
            thread_id=thread_id,
            app=app,
        )
        await _run_epilogue.emit_run_epilogue(
            emit=emit,
            thread_id=thread_id,
            run_id=run_id,
            outcome="cancelled",
            payload={"cancelled_tool_call_ids": cancelled_tool_call_ids},
        )
        return ""
    except Exception as e:
        if trajectory_scope is not None:
            try:
                trajectory_scope.finalize_error()
            except Exception:
                logger.error("Failed to finalize errored trajectory for thread %s", thread_id, exc_info=True)
        log_captured_exception(f"[streaming] run failed for thread {thread_id}", e)
        await _run_epilogue.emit_run_epilogue(
            emit=emit,
            thread_id=thread_id,
            run_id=run_id,
            outcome="error",
            payload={"error": str(e)},
        )
        return ""
    finally:
        prompt_restore()
        if typing_tracker is not None:
            typing_tracker.stop(thread_id)
        detach_activity_bridge()
        flush_observation()
        app.state.thread_tasks.pop(thread_id, None)
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            agent.runtime.transition(AgentState.IDLE)
        try:
            await cleanup_old_runs(thread_id, keep_latest=1, run_event_repo=run_event_repo)
        except Exception:
            logger.warning("Failed to cleanup old runs for thread %s", thread_id, exc_info=True)
        if run_event_repo is not None:
            run_event_repo.close()
        await consume_followup_queue(agent, thread_id, app)
