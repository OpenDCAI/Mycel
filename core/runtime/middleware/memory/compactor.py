"""ContextCompactor — Layer 2: LLM-based conversation summarization.

Generates summaries of old messages, caches them in memory.
Does NOT modify LangGraph state.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

SUMMARY_PROMPT = """\
Provide a detailed summary for continuing our conversation. Include:
1. Key decisions made and their rationale
2. Files created, modified, or read and their current state
3. Errors encountered and how they were resolved
4. Outstanding tasks and current progress
5. Important context that would be needed to continue the work
Be concise but retain all information needed to continue seamlessly."""

SPLIT_TURN_PREFIX_PROMPT = """\
This summary covers the prefix of a split turn. Focus on the original request,
early progress, and any details needed to understand the retained suffix.
Provide a concise summary that captures the essential context."""


class ContextCompactor:
    """Summarize old messages via LLM call. Stateless — caller manages cache."""

    def __init__(
        self,
        reserve_tokens: int = 16384,
        keep_recent_tokens: int = 20000,
    ):
        self.reserve_tokens = reserve_tokens
        self.keep_recent_tokens = keep_recent_tokens

    def should_compact(self, estimated_tokens: int, context_limit: int, threshold: float = 0.7) -> bool:
        """Whether current context exceeds the compaction threshold.

        Args:
            estimated_tokens: Current estimated token count
            context_limit: Maximum context window size
            threshold: Fraction of context_limit to trigger compaction (default 0.7)

        Returns:
            True if compaction should be triggered
        """
        threshold_tokens = int(context_limit * threshold)
        return estimated_tokens > threshold_tokens

    def split_messages(self, messages: list[Any]) -> tuple[list[Any], list[Any]]:
        """Split messages into (to_summarize, to_keep).

        Keeps recent messages up to keep_recent_tokens.
        Boundary: never splits an AIMessage(tool_calls) from its ToolMessages.
        """
        if len(messages) <= 2:
            return [], messages

        # Walk backwards, accumulating tokens for to_keep
        accumulated = 0
        split_idx = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = self._estimate_msg_tokens(messages[i])
            if accumulated + msg_tokens > self.keep_recent_tokens:
                split_idx = i + 1
                break
            accumulated += msg_tokens
        else:
            return [], messages

        # Adjust boundary to avoid splitting tool_calls from ToolMessages
        split_idx = self._adjust_boundary(messages, split_idx)

        if split_idx <= 1:
            return [], messages

        return messages[:split_idx], messages[split_idx:]

    async def compact(self, messages_to_summarize: list[Any], model: Any) -> str:
        """Generate a summary of the given messages using the LLM.

        Returns plain text summary string.
        """
        # Build the summarization request
        formatted = self._format_messages_for_summary(messages_to_summarize)
        summary_messages = [
            SystemMessage(content=SUMMARY_PROMPT),
            HumanMessage(content=f"Here is the conversation to summarize:\n\n{formatted}"),
        ]

        response = await model.ainvoke(summary_messages)
        return response.content if hasattr(response, "content") else str(response)

    def _estimate_msg_tokens(self, msg: Any) -> int:
        """Estimate tokens for a single message (chars // 2)."""
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return len(content) // 2
        if isinstance(content, list):
            total = 0
            for block in content:
                if isinstance(block, dict):
                    total += len(block.get("text", "")) // 2
                elif isinstance(block, str):
                    total += len(block) // 2
            return total
        return 0

    def _adjust_boundary(self, messages: list[Any], split_idx: int) -> int:
        """Adjust split boundary so we don't separate AIMessage(tool_calls) from ToolMessages."""
        while split_idx < len(messages) and messages[split_idx].__class__.__name__ == "ToolMessage":
            split_idx -= 1
            if split_idx <= 0:
                break

        return max(split_idx, 1)

    def detect_split_turn(self, messages: list[Any], to_keep: list[Any], context_limit: int) -> tuple[bool, list[Any]]:
        """Detect if we need to split the current turn.

        A split turn occurs when the new content (to_keep) is so large that it
        consumes more than 50% of the context window, leaving insufficient room
        for history.

        Args:
            messages: All messages
            to_keep: Messages that would be kept after normal compaction
            context_limit: Maximum context window size

        Returns:
            (is_split_turn, turn_prefix_messages): Whether to split, and the prefix to summarize
        """
        if len(to_keep) <= 1:
            return False, []

        # Calculate token budgets
        new_content_tokens = sum(self._estimate_msg_tokens(msg) for msg in to_keep)
        max_history_tokens = int(context_limit * 0.5 * 1.2)  # 50% + 20% safety margin

        if new_content_tokens <= max_history_tokens:
            return False, []

        # Need to split: extract prefix from to_keep
        turn_prefix = self._extract_turn_prefix(to_keep, max_history_tokens)
        return True, turn_prefix

    def _extract_turn_prefix(self, to_keep: list[Any], max_tokens: int) -> list[Any]:
        """Extract prefix messages from to_keep up to max_tokens."""
        accumulated = 0
        prefix_end_idx = 0

        for i, msg in enumerate(to_keep):
            msg_tokens = self._estimate_msg_tokens(msg)
            if accumulated + msg_tokens > max_tokens:
                prefix_end_idx = i
                break
            accumulated += msg_tokens
        else:
            prefix_end_idx = max(len(to_keep) - 1, 0)

        prefix_end_idx = self._adjust_boundary(to_keep, prefix_end_idx)
        return to_keep[:prefix_end_idx]

    async def compact_with_split_turn(
        self, to_summarize: list[Any], turn_prefix: list[Any], model: Any
    ) -> tuple[str, str]:
        """Generate summary with split turn handling.

        Creates two summaries:
        1. Historical summary (standard)
        2. Turn prefix summary (focused on original request)

        Returns:
            (combined_summary, prefix_summary)
        """
        history_summary = await self.compact(to_summarize, model)

        formatted_prefix = self._format_messages_for_summary(turn_prefix)
        prefix_messages = [
            SystemMessage(content=SPLIT_TURN_PREFIX_PROMPT),
            HumanMessage(content=f"Here is the turn prefix to summarize:\n\n{formatted_prefix}"),
        ]
        response = await model.ainvoke(prefix_messages)
        prefix_summary = response.content if hasattr(response, "content") else str(response)

        combined = f"{history_summary}\n\n---\n\n**Turn Context (split turn):**\n\n{prefix_summary}"
        return combined, prefix_summary

    def _format_messages_for_summary(self, messages: list[Any]) -> str:
        """Format messages into a readable string for the summarization LLM."""
        parts = []
        for msg in messages:
            role = msg.__class__.__name__.replace("Message", "")
            content = getattr(msg, "content", "")

            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = "".join(text_parts)
            else:
                text = str(content)

            if len(text) > 2000:
                text = text[:1000] + "\n[...truncated...]\n" + text[-500:]

            parts.append(f"[{role}]: {text}")
        return "\n\n".join(parts)
