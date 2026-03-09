"""SessionPruner — Layer 1: trim/clear old ToolMessage content.

Pure string operations, no LLM calls. Protects recent tool results.
"""

from __future__ import annotations

import copy
from typing import Any


class SessionPruner:
    """Prune old ToolMessage content to reduce context size.

    Two levels:
    - soft-trim: keep head + tail, replace middle with [...trimmed...]
    - hard-clear: replace entire content with placeholder
    """

    def __init__(
        self,
        soft_trim_chars: int = 3000,
        hard_clear_threshold: int = 10000,
        protect_recent: int = 3,
    ):
        self.soft_trim_chars = soft_trim_chars
        self.hard_clear_threshold = hard_clear_threshold
        self.protect_recent = protect_recent

    def prune(self, messages: list[Any]) -> list[Any]:
        """Return new message list with old ToolMessage content trimmed/cleared.

        Does NOT modify original messages — returns shallow copies with replaced content.
        """
        protected_ids = self._get_protected_tool_call_ids(messages)
        result = []
        for msg in messages:
            if self._is_tool_message(msg) and not self._is_protected(msg, protected_ids):
                result.append(self._prune_tool_message(msg))
            else:
                result.append(msg)
        return result

    def _get_protected_tool_call_ids(self, messages: list[Any]) -> set[str]:
        """Collect tool_call_ids from the most recent N AIMessages with tool_calls."""
        ids: set[str] = set()
        count = 0
        for msg in reversed(messages):
            if count >= self.protect_recent:
                break
            if not self._is_ai_message(msg):
                continue

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                continue

            for tc in tool_calls:
                tc_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                if tc_id:
                    ids.add(tc_id)
            count += 1
        return ids

    def _is_tool_message(self, msg: Any) -> bool:
        return msg.__class__.__name__ == "ToolMessage"

    def _is_ai_message(self, msg: Any) -> bool:
        return msg.__class__.__name__ == "AIMessage"

    def _is_protected(self, msg: Any, protected_ids: set[str]) -> bool:
        tool_call_id = getattr(msg, "tool_call_id", None)
        return tool_call_id in protected_ids if tool_call_id else False

    def _prune_tool_message(self, msg: Any) -> Any:
        content = getattr(msg, "content", "")
        if not isinstance(content, str):
            return msg

        n = len(content)
        if n <= self.soft_trim_chars:
            return msg

        # Determine new content based on size
        if n > self.hard_clear_threshold:
            new_content = f"[Tool output cleared — {n} chars]"
        else:
            half = self.soft_trim_chars // 2
            new_content = content[:half] + "\n\n[...trimmed...]\n\n" + content[-half:]

        new_msg = copy.copy(msg)
        new_msg.content = new_content
        return new_msg
