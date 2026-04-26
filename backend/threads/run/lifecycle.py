from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def prime_sandbox(agent: Any, thread_id: str) -> None:
    def _prime_sandbox() -> None:
        mgr = agent._sandbox.manager
        mgr.enforce_idle_timeouts()
        capability = mgr.get_sandbox(thread_id)
        sandbox_runtime = getattr(getattr(capability, "_session", None), "sandbox_runtime", None)
        if sandbox_runtime:
            sandbox_runtime_status = sandbox_runtime.refresh_instance_status(mgr.provider)
            if sandbox_runtime_status == "paused" and mgr.provider_capability.can_resume and not agent._sandbox.resume_thread(thread_id):
                raise RuntimeError(f"Failed to auto-resume paused sandbox for thread {thread_id}")

    await asyncio.to_thread(_prime_sandbox)


async def write_cancellation_markers(
    agent: Any,
    config: dict[str, Any],
    pending_tool_calls: dict[str, dict],
) -> list[str]:
    cancelled_tool_call_ids = []
    if not pending_tool_calls or not agent:
        return cancelled_tool_call_ids

    try:
        from langchain_core.messages import ToolMessage
        from langgraph.checkpoint.base import create_checkpoint

        checkpointer = agent.agent.checkpointer
        if not checkpointer:
            return cancelled_tool_call_ids

        checkpoint_tuple = await checkpointer.aget_tuple(config)
        if not checkpoint_tuple:
            return cancelled_tool_call_ids

        checkpoint = checkpoint_tuple.checkpoint
        metadata = checkpoint_tuple.metadata or {}

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

        updated_channel_values = checkpoint["channel_values"].copy()
        updated_channel_values["messages"] = list(updated_channel_values.get("messages", []))
        updated_channel_values["messages"].extend(cancel_messages)

        new_checkpoint = create_checkpoint(checkpoint, None, metadata.get("step", 0))
        new_checkpoint["channel_values"] = updated_channel_values
        current_versions = dict(checkpoint.get("channel_versions", {}) or {})
        get_next_version = getattr(checkpointer, "get_next_version", None)
        if not callable(get_next_version):
            raise RuntimeError("Checkpointer missing get_next_version; cannot write cancellation markers honestly")
        next_message_version = get_next_version(current_versions.get("messages"), None)
        if not isinstance(next_message_version, str | int | float):
            raise RuntimeError("Checkpointer returned an invalid messages channel version")
        new_versions = {"messages": next_message_version}
        new_checkpoint["channel_versions"] = {**current_versions, **new_versions}
        new_checkpoint["updated_channels"] = list(new_versions)

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
        logger.exception(
            "[streaming] failed to write cancellation markers for thread %s",
            config.get("configurable", {}).get("thread_id"),
        )

    return cancelled_tool_call_ids


async def repair_incomplete_tool_calls(agent: Any, config: dict[str, Any]) -> None:
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

        pending_tc_ids: dict[str, str] = {}
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
            len(unmatched),
            thread_id,
            list(unmatched.keys()),
        )

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

        after_msgs = messages[broken_ai_idx + 1 :]

        updates = []
        for msg in after_msgs:
            msg_id = getattr(msg, "id", None)
            if msg_id:
                updates.append(RemoveMessage(id=msg_id))

        for tc_id, tool_name in unmatched.items():
            updates.append(
                ToolMessage(
                    content="Error: task was interrupted (server restart or timeout). Results unavailable.",
                    tool_call_id=tc_id,
                    name=tool_name,
                )
            )

        for msg in after_msgs:
            if msg.__class__.__name__ != "ToolMessage" or getattr(msg, "tool_call_id", None) not in unmatched:
                updates.append(msg)

        await graph.aupdate_state(config, {"messages": updates})
        logger.warning("[streaming] Repaired incomplete tool_calls for thread %s", thread_id)
    except Exception:
        logger.exception("[streaming] Failed to repair incomplete tool_calls")
