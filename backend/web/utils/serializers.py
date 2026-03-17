"""Message serialization utilities."""

import re
from typing import Any

# @@@strip-system-hint — remove <system-hint>...</system-hint> injected by prompt_injection
_SYSTEM_HINT_RE = re.compile(r"\s*<system-hint>.*?</system-hint>\s*", re.DOTALL)


def strip_system_hints(content: str) -> str:
    """Remove <system-hint> tags from user-visible content."""
    return _SYSTEM_HINT_RE.sub("", content).strip()


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
    # Strip system hints from HumanMessage content (injected by prompt_injection)
    msg_type = msg.__class__.__name__
    if msg_type == "HumanMessage" and isinstance(content, str) and "<system-hint>" in content:
        content = strip_system_hints(content)
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
