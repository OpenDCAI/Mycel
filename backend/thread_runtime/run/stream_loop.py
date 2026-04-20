"""Streaming loop helpers for thread runtime runs."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from backend.message_content import extract_text_content

logger = logging.getLogger(__name__)


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


async def run_stream_loop(
    *,
    agent: Any,
    config: dict[str, Any],
    initial_input: dict[str, Any] | None,
    emit: Any,
    dedup: Any,
    drain_activity_events: Any,
    pending_tool_calls: dict[str, dict],
    output_parts: list[str],
    thread_id: str,
    run_id: str,
    log_captured_exception: Any,
    max_stream_retries: int = 10,
) -> str:
    async def run_agent_stream(input_data: dict | None = initial_input):
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

    stream_attempt = 0
    stream_gen = None
    task = None
    trajectory_status = "completed"
    try:
        while True:
            stream_gen = run_agent_stream(initial_input if stream_attempt == 0 else None)
            task = asyncio.create_task(stream_gen.__anext__())
            stream_err: Exception | None = None

            while True:
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

                        for tc_chunk in getattr(msg_chunk, "tool_call_chunks", []):
                            tc_id = tc_chunk.get("id")
                            tc_name = tc_chunk.get("name", "")
                            if tc_id and tc_name and not dedup.already_emitted(tc_id):
                                dedup.register(tc_id)
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
                                        dedup.already_emitted(tc_id),
                                        dedup.is_duplicate(tc_id),
                                        thread_id,
                                    )
                                    # @@@checkpoint-dedup — skip tool_calls from previous runs
                                    # but allow current run's updates (delivers full args after early emission)
                                    if dedup.is_duplicate(tc_id):
                                        continue
                                    if tc_id and not dedup.already_emitted(tc_id):
                                        dedup.register(tc_id)
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
                                if dedup.is_duplicate(tc_id):
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

                await drain_activity_events()

            if stream_err is None:
                break

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
                log_captured_exception(
                    f"[streaming] stream failed for thread {thread_id}",
                    stream_err,
                )
                await emit({"event": "error", "data": json.dumps({"error": str(stream_err)}, ensure_ascii=False)})
                break
        return trajectory_status
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if stream_gen is not None:
            try:
                await stream_gen.aclose()
            except RuntimeError as err:
                if "already running" not in str(err):
                    raise
