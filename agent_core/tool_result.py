from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import ToolMessage


@dataclass
class ToolResultEnvelope:
    kind: str
    content: Any
    is_error: bool = False
    top_level_blocks: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def tool_success(content: Any, *, metadata: dict[str, Any] | None = None) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        kind="success",
        content=content,
        metadata=dict(metadata or {}),
    )


def tool_error(content: str, *, metadata: dict[str, Any] | None = None) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        kind="error",
        content=content,
        is_error=True,
        metadata=dict(metadata or {}),
    )


def tool_permission_denied(
    content: str,
    *,
    top_level_blocks: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        kind="permission_denied",
        content=content,
        is_error=True,
        top_level_blocks=list(top_level_blocks or []),
        metadata=dict(metadata or {}),
    )


def tool_permission_request(
    content: str,
    *,
    top_level_blocks: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        kind="permission_request",
        content=content,
        top_level_blocks=list(top_level_blocks or []),
        metadata=dict(metadata or {}),
    )


def materialize_tool_message(
    envelope: ToolResultEnvelope,
    *,
    tool_call_id: str,
    name: str,
    source: str,
) -> ToolMessage:
    additional_kwargs = {
        "tool_result_meta": {
            "kind": envelope.kind,
            "source": source,
            "top_level_blocks": list(envelope.top_level_blocks),
            **dict(envelope.metadata),
        }
    }
    return ToolMessage(
        content=envelope.content,
        tool_call_id=tool_call_id,
        name=name,
        additional_kwargs=additional_kwargs,
    )
