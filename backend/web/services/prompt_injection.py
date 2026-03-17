"""Prompt injection -- system hints for audience awareness.

Agents receive messages from two sources: owner (direct thread interaction)
and external (other entities via conversation system). The <system-hint> tag
lets the agent distinguish between these without breaking message formatting.
"""


def build_message_with_hint(content: str, source: str, sender_name: str | None = None) -> str:
    """Attach a system hint to a message based on source.

    source="owner"    -> agent knows it's talking to owner
    source="external" -> agent knows it's from another entity, use tell_owner
    """
    if source == "owner":
        hint = "This message is from your owner. Respond naturally."
    elif source == "external":
        sender = sender_name or "unknown"
        hint = (
            f"This message is from [{sender}], not your owner. "
            f"Reply using chat_send() — plain text is invisible to them. "
            f"If you need your owner, use tell_owner()."
        )
    else:
        return content

    return f"{content}\n\n<system-hint>{hint}</system-hint>"


def build_waterline_hint() -> str:
    """Hint for when owner steers into an external run."""
    return "<system-hint>Your owner is now here. Respond naturally to them.</system-hint>"
