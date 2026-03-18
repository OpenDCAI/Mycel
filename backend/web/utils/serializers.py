"""Message serialization utilities."""

import re
from typing import Any

# @@@strip-system-tags — remove injected system tags from user-visible content
_SYSTEM_HINT_RE = re.compile(r"\s*<system-hint>.*?</system-hint>\s*", re.DOTALL)
_SYSTEM_REMINDER_RE = re.compile(r"\s*<system-reminder>.*?</system-reminder>\s*", re.DOTALL)


def strip_system_tags(content: str) -> str:
    """Remove <system-hint> and <system-reminder> tags from user-visible content."""
    content = _SYSTEM_HINT_RE.sub("", content)
    content = _SYSTEM_REMINDER_RE.sub("", content)
    return content.strip()



def avatar_url(member_id: str | None, has_avatar: bool) -> str | None:
    """Build avatar URL. Returns None if no avatar uploaded."""
    return f"/api/members/{member_id}/avatar" if member_id and has_avatar else None


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
    # Strip system tags from owner HumanMessages (context-shift hints).
    # External HumanMessages keep their <system-reminder> so frontend can
    # extract <chat-message> content for the "show hidden" toggle.
    msg_type = msg.__class__.__name__
    metadata = getattr(msg, "metadata", None) or {}
    source = metadata.get("source", "owner") if isinstance(metadata, dict) else "owner"
    if msg_type == "HumanMessage" and isinstance(content, str) and source == "owner":
        if "<system-hint>" in content or "<system-reminder>" in content:
            content = strip_system_tags(content)
    result = {
        "id": getattr(msg, "id", None),
        "type": msg_type,
        "content": content,
        "tool_calls": getattr(msg, "tool_calls", []),
        "tool_call_id": getattr(msg, "tool_call_id", None),
        "name": getattr(msg, "name", None),
    }
    metadata = getattr(msg, "metadata", None)
    if metadata:
        result["metadata"] = metadata
    return result
