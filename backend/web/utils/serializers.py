"""Message serialization utilities."""

from typing import Any


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
    result = {
        "id": getattr(msg, "id", None),
        "type": msg.__class__.__name__,
        "content": getattr(msg, "content", ""),
        "tool_calls": getattr(msg, "tool_calls", []),
        "tool_call_id": getattr(msg, "tool_call_id", None),
    }
    metadata = getattr(msg, "metadata", None)
    if metadata:
        result["metadata"] = metadata
    return result
