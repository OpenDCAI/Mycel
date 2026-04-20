"""Neutral message-content helpers shared across backend owners."""

import re
from typing import Any

_SYSTEM_HINT_RE = re.compile(r"\s*<system-hint>.*?</system-hint>\s*", re.DOTALL)
_SYSTEM_REMINDER_RE = re.compile(r"\s*<system-reminder>.*?</system-reminder>\s*", re.DOTALL)


def strip_system_tags(content: str) -> str:
    """Remove user-hidden system tags from owner-visible content."""
    content = _SYSTEM_HINT_RE.sub("", content)
    content = _SYSTEM_REMINDER_RE.sub("", content)
    return content.strip()


def extract_text_content(raw_content: Any) -> str:
    """Extract text content from common message payload shapes."""
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
