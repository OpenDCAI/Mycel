"""Message serialization utilities."""

from typing import Any

from backend.identity.avatar.urls import avatar_url
from backend.threads.message_content import extract_text_content, strip_system_tags

__all__ = ["avatar_url", "strip_system_tags", "extract_text_content", "serialize_message"]


def serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a LangChain message to a JSON-serializable dict."""
    content = getattr(msg, "content", "")
    metadata = dict(getattr(msg, "metadata", None) or {})
    additional_kwargs = getattr(msg, "additional_kwargs", None) or {}
    tool_result_meta = additional_kwargs.get("tool_result_meta")
    # @@@tool-result-meta-merge - LangChain ToolMessage keeps durable tool
    # metadata in additional_kwargs, but Mycel display rebuild consumes
    # serialized metadata. Merge the exact structured tool_result_meta here so
    # checkpoint rebuild can recover blocking subagent identity honestly.
    if isinstance(tool_result_meta, dict):
        metadata = {**tool_result_meta, **metadata}

    # Strip system tags from owner HumanMessages (context-shift hints).
    # External HumanMessages keep their <system-reminder> so frontend can
    # extract <chat-message> content for the "show hidden" toggle.
    msg_type = msg.__class__.__name__
    source = metadata.get("source", "owner") if isinstance(metadata, dict) else "owner"
    if msg_type == "HumanMessage" and isinstance(content, str) and source == "owner":
        if "<system-hint>" in content or "<system-reminder>" in content:
            content = strip_system_tags(content)

    # @@@display-content-split - LLM sees the prefixed message; frontend sees the original.
    if metadata and "original_message" in metadata:
        content = metadata["original_message"]

    result = {
        "id": getattr(msg, "id", None),
        "type": msg_type,
        "content": content,
        "tool_calls": getattr(msg, "tool_calls", []),
        "tool_call_id": getattr(msg, "tool_call_id", None),
        "name": getattr(msg, "name", None),
    }
    if metadata:
        result["metadata"] = metadata
    if metadata.get("source") == "internal":
        result["display"] = {"showing": False}
    return result
