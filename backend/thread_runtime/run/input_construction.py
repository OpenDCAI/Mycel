"""Input construction helpers for thread runtime runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

_TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE = (
    "Terminal background completion notifications require an explicit assistant followthrough. "
    "Treat these notifications as fresh inputs that need a visible assistant reply. "
    "You must produce at least one visible assistant message for them; "
    "do not stay silent and do not end the run after only surfacing a notice. "
    "Do not call TaskOutput or TaskStop for a terminal notification. "
    "If no further tool is truly needed, answer directly in natural language "
    "and briefly acknowledge the completion, failure, or cancellation honestly."
)


def augment_system_prompt_for_terminal_followthrough(system_prompt: Any) -> Any:
    content = getattr(system_prompt, "content", None)
    if not isinstance(content, str):
        return system_prompt
    if _TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE in content:
        return system_prompt
    # @@@terminal-followthrough-system-note - live models can otherwise treat
    # terminal background notifications as internal reminders and emit no
    # assistant text, leaving caller surfaces notice-only.
    return system_prompt.__class__(content=f"{content}\n\n{_TERMINAL_FOLLOWTHROUGH_SYSTEM_NOTE}")


def is_terminal_background_notification_message(
    message: str,
    *,
    source: str | None,
    notification_type: str | None,
) -> bool:
    if source not in {"system", "external"}:
        return False
    if notification_type not in {"agent", "command", "chat"}:
        return False
    return "<system-reminder>" in message or bool(message.strip())


async def build_initial_input(
    *,
    message: str,
    message_metadata: dict[str, Any] | None,
    input_messages: list[Any] | None,
    agent: Any,
    app: Any,
    thread_id: str,
    emit: Callable[[dict[str, str], str | None], Awaitable[None]] | None,
    emit_queued_terminal_followups: Callable[..., Awaitable[list[dict[str, str | None]]]] | None,
) -> tuple[dict[str, Any], Callable[[], None]]:
    meta = message_metadata or {}
    src = meta.get("source")
    ntype = meta.get("notification_type")

    original_system_prompt = None

    def prompt_restore() -> None:
        nonlocal original_system_prompt
        if original_system_prompt is not None and hasattr(agent, "agent") and hasattr(agent.agent, "system_prompt"):
            agent.agent.system_prompt = original_system_prompt

    terminal_followthrough_items: list[dict[str, str | None]] | None = None
    # @@@terminal-followthrough-reentry - terminal background completions
    # still surface as durable notices first, but they must then re-enter the
    # model as a real followthrough turn instead of terminating at notice-only.
    if is_terminal_background_notification_message(
        message,
        source=src,
        notification_type=ntype,
    ):
        terminal_followthrough_items = [
            {
                "content": message,
                "source": src or "system",
                "notification_type": ntype,
            }
        ]
        if emit_queued_terminal_followups is not None:
            terminal_followthrough_items.extend(await emit_queued_terminal_followups(app=app, thread_id=thread_id, emit=emit))
        if hasattr(agent, "agent") and hasattr(agent.agent, "system_prompt"):
            original_system_prompt = agent.agent.system_prompt
            agent.agent.system_prompt = augment_system_prompt_for_terminal_followthrough(original_system_prompt)

    if terminal_followthrough_items:
        from langchain_core.messages import HumanMessage

        initial_input: dict[str, Any] = {
            "messages": [
                HumanMessage(
                    content=str(item["content"] or ""),
                    metadata={
                        "source": item["source"] or "system",
                        "notification_type": item["notification_type"],
                    },
                )
                for item in terminal_followthrough_items
            ]
        }
    elif input_messages is not None:
        initial_input = {"messages": input_messages}
    elif message_metadata:
        from langchain_core.messages import HumanMessage

        initial_input = {"messages": [HumanMessage(content=message, metadata=message_metadata)]}
    else:
        initial_input = {"messages": [{"role": "user", "content": message}]}

    return initial_input, prompt_restore
