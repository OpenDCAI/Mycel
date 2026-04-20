from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .checkpoint_store import ThreadCheckpointState


def agent_checkpoint_conn_string(conn_string: str) -> str:
    parts = urlsplit(conn_string)
    query = parse_qsl(parts.query, keep_blank_values=True)
    merged_query: list[tuple[str, str]] = []
    saw_options = False
    for key, value in query:
        if key != "options":
            merged_query.append((key, value))
            continue
        saw_options = True
        if "search_path" in value:
            if "search_path=agent" not in value:
                raise RuntimeError("LEON_POSTGRES_URL must not set checkpointer search_path outside Mycel runtime")
            merged_query.append((key, value))
        else:
            merged_query.append((key, f"{value} -csearch_path=agent"))
    if not saw_options:
        merged_query.append(("options", "-csearch_path=agent"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged_query, quote_via=quote), parts.fragment))


@asynccontextmanager
async def agent_checkpoint_saver_from_conn_string(conn_string: str) -> AsyncIterator[AsyncPostgresSaver]:
    shaped_conn_string = agent_checkpoint_conn_string(conn_string)
    async with await AsyncConnection.connect(
        shaped_conn_string,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as conn:
        # @@@checkpoint-search-path - Supavisor may ignore libpq options, so pin
        # the live connection before LangGraph setup creates unqualified tables.
        await conn.execute("SET search_path TO agent")
        yield AsyncPostgresSaver(conn=conn)


class LangGraphCheckpointStore:
    def __init__(self, saver: Any):
        self._saver = saver

    async def load(self, thread_id: str) -> ThreadCheckpointState | None:
        checkpoint = await self._aget_checkpoint(thread_id)
        if checkpoint is None:
            return None
        channel_values = dict(checkpoint.get("channel_values", {}) or {})
        return ThreadCheckpointState(
            messages=list(channel_values.get("messages", [])),
            tool_permission_context=dict(channel_values.get("tool_permission_context", {}) or {}),
            pending_permission_requests=dict(channel_values.get("pending_permission_requests", {}) or {}),
            resolved_permission_requests=dict(channel_values.get("resolved_permission_requests", {}) or {}),
            memory_compaction_state=dict(channel_values.get("memory_compaction_state", {}) or {}),
            mcp_instruction_state=dict(channel_values.get("mcp_instruction_state", {}) or {}),
        )

    async def save(self, thread_id: str, state: ThreadCheckpointState) -> None:
        from langgraph.checkpoint.base import CheckpointMetadata, create_checkpoint, empty_checkpoint

        existing_checkpoint = await self._aget_checkpoint(thread_id)
        checkpoint = create_checkpoint(
            self._normalize_checkpoint_for_write(existing_checkpoint, empty_checkpoint),
            None,
            len(state.messages),
        )
        checkpoint["channel_values"] = {
            "messages": state.messages,
            "tool_permission_context": state.tool_permission_context,
            "pending_permission_requests": state.pending_permission_requests,
            "resolved_permission_requests": state.resolved_permission_requests,
            "memory_compaction_state": state.memory_compaction_state,
            "mcp_instruction_state": state.mcp_instruction_state,
        }
        new_versions: dict[str, Any] = {}
        get_next_version = getattr(self._saver, "get_next_version", None)
        if callable(get_next_version):
            current_versions = dict(checkpoint.get("channel_versions", {}) or {})
            for channel_name in checkpoint["channel_values"]:
                new_versions[channel_name] = get_next_version(current_versions.get(channel_name), None)
            checkpoint["channel_versions"] = {**current_versions, **new_versions}
            checkpoint["updated_channels"] = list(new_versions)
        metadata: CheckpointMetadata = {
            "source": "loop",
            "step": len(state.messages),
        }
        await self._saver.aput(self._checkpoint_config(thread_id), checkpoint, metadata, new_versions)

    async def _aget_checkpoint(self, thread_id: str) -> dict[str, Any] | None:
        cfg = self._checkpoint_config(thread_id)
        aget_tuple = getattr(self._saver, "aget_tuple", None)
        if callable(aget_tuple):
            checkpoint_tuple_result = aget_tuple(cfg)
            checkpoint_tuple = await checkpoint_tuple_result if inspect.isawaitable(checkpoint_tuple_result) else checkpoint_tuple_result
            checkpoint_value = getattr(checkpoint_tuple, "checkpoint", None)
            if isinstance(checkpoint_value, dict):
                return checkpoint_value
        aget = getattr(self._saver, "aget", None)
        if callable(aget):
            checkpoint_result = aget(cfg)
            checkpoint_value = await checkpoint_result if inspect.isawaitable(checkpoint_result) else checkpoint_result
            if isinstance(checkpoint_value, dict):
                return cast(dict[str, Any], checkpoint_value)
        return None

    @staticmethod
    def _normalize_checkpoint_for_write(raw_checkpoint: Any, empty_checkpoint_factory: Any) -> Any:
        checkpoint = empty_checkpoint_factory()
        if not isinstance(raw_checkpoint, dict):
            return checkpoint
        # @@@checkpoint-shape-normalization - local/simple savers often persist only
        # channel_values, while LangGraph savers expect the full checkpoint shape.
        # Normalize both into one writable base contract before versioning.
        for key, default_value in checkpoint.items():
            if key not in raw_checkpoint:
                continue
            value = raw_checkpoint[key]
            if isinstance(default_value, dict):
                checkpoint[key] = dict(value or {})
            elif isinstance(default_value, list):
                checkpoint[key] = list(value or [])
            else:
                checkpoint[key] = value
        return checkpoint

    @staticmethod
    def _checkpoint_config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
