"""Provider-specific streaming usage patches.

Centralizes workarounds for upstream bugs where streaming responses
return incomplete token usage data. Each patch is idempotent and
guarded by a flag so it can be called multiple times safely.

Remove individual patches once the upstream library is fixed.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# @@@langchain-anthropic-streaming-usage-regression
# langchain-anthropic >= 1.0 dropped usage extraction from message_start,
# assuming message_delta carries complete info. But Anthropic API only puts
# input_tokens (+ cache tokens) in message_start and output_tokens in
# message_delta. This patch restores the v0.2.4 behavior.
# Remove this once upstream is fixed.
# ---------------------------------------------------------------------------

_anthropic_patched = False


def patch_anthropic_streaming_usage() -> None:
    """Restore input-token extraction from message_start in streaming."""
    global _anthropic_patched
    if _anthropic_patched:
        return

    try:
        import langchain_anthropic.chat_models as mod
    except ImportError:
        return

    original = mod._make_message_chunk_from_anthropic_event

    def _patched_make_chunk(
        event: Any,
        *,
        stream_usage: bool = True,
        coerce_content_to_string: bool = True,
        block_start_event: Any = None,
    ) -> tuple:
        msg, block = original(
            event,
            stream_usage=stream_usage,
            coerce_content_to_string=coerce_content_to_string,
            block_start_event=block_start_event,
        )
        # Inject usage from message_start (where Anthropic reports input_tokens)
        if (
            stream_usage
            and event.type == "message_start"
            and msg is not None
            and not msg.usage_metadata
            and hasattr(event.message, "usage")
        ):
            msg.usage_metadata = mod._create_usage_metadata(event.message.usage)
        return msg, block

    mod._make_message_chunk_from_anthropic_event = _patched_make_chunk
    _anthropic_patched = True


def apply_all() -> None:
    """Apply all provider-specific streaming usage patches."""
    patch_anthropic_streaming_usage()
