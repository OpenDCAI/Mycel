"""Message serialization utilities."""

import re
from typing import Any

from backend.web.core.paths import avatars_dir

# @@@strip-system-tags — remove injected system tags from user-visible content
_SYSTEM_HINT_RE = re.compile(r"\s*<system-hint>.*?</system-hint>\s*", re.DOTALL)
_SYSTEM_REMINDER_RE = re.compile(r"\s*<system-reminder>.*?</system-reminder>\s*", re.DOTALL)


def strip_system_tags(content: str) -> str:
    """Remove <system-hint> and <system-reminder> tags from user-visible content."""
    content = _SYSTEM_HINT_RE.sub("", content)
    content = _SYSTEM_REMINDER_RE.sub("", content)
    return content.strip()


def avatar_url(user_id: str | None, has_avatar: bool) -> str | None:
    """Build avatar URL. Returns None if no avatar uploaded."""
    # @@@avatar-truth-seam - current web avatar serving is file-backed; DB avatar
    # rows may legitimately stay null on the Supabase path, so visibility truth
    # must follow the actual served file surface instead of trusting the column alone.
    if not user_id:
        return None
    if has_avatar or (avatars_dir() / f"{user_id}.png").exists():
        return f"/api/users/{user_id}/avatar"
    return None


def extract_text_content(raw_content: Any) -> str:
    """Extract text content from various message content formats."""
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(raw_content)


def serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a LangChain message to a JSON-compatible dict."""
    content = getattr(msg, "content", "")
    metadata = dict(getattr(msg, "metadata", None) or {})
    additional_kwargs = getattr(msg, "additional_kwargs", None) or {}
    tool_result_meta = additional_kwargs.get("tool_result_meta")
    # @@@tool-result-meta-bridge - LangChain ToolMessage keeps durable tool
    # metadata in additional_kwargs, but Leon display rebuild consumes
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
