"""XML formatters for steer messages and task notifications.

Matches Claude Code's system-reminder convention so the LLM treats
injected content as authoritative system instructions.
Frontend strips <system-reminder> tags — agent sees full XML, user sees clean text.
"""

import json
from html import escape
from typing import Literal


def format_chat_notification(sender_name: str, chat_id: str, unread_count: int, signal: str | None = None) -> str:
    """Lightweight notification — agent must read_messages to see content.

    @@@v3-notification-only — no message content injected. Agent calls
    read_messages(chat_id=...) to read, then send_message() to reply.
    """
    signal_hint = f" [signal: {signal}]" if signal and signal != "open" else ""
    return (
        "<system-reminder>\n"
        f"New message from {sender_name} in chat {chat_id} ({unread_count} unread).{signal_hint}\n"
        f'Read it with read_messages(chat_id="{chat_id}").\n'
        f'Reply with send_message(chat_id="{chat_id}", content="...").\n'
        "Prefer using this exact chat_id directly.\n"
        "Do not treat your normal assistant text as a chat reply.\n"
        "</system-reminder>"
    )


def format_agent_message(sender_name: str, message: str) -> str:
    """Format inter-agent delivery for steering injection on the next turn."""
    return (
        "<system-reminder>\n"
        "<agent-message>\n"
        f"  <from>{escape(sender_name)}</from>\n"
        f"  <content>{escape(message)}</content>\n"
        "</agent-message>\n"
        "</system-reminder>"
    )


def format_progress_notification(
    agent_id: str,
    description: str,
    *,
    step: str = "running",
) -> str:
    """Format background worker progress for coordinator-style prompt injection."""
    return (
        "<system-reminder>\n"
        "<worker-progress>\n"
        f"  <agent-id>{escape(agent_id)}</agent-id>\n"
        f"  <step>{escape(step)}</step>\n"
        f"  <description>{escape(description)}</description>\n"
        "</worker-progress>\n"
        "</system-reminder>"
    )


def format_background_notification(
    task_id: str,
    status: str,
    summary: str,
    result: str | None = None,
    usage: dict | None = None,
    description: str | None = None,
) -> str:
    """Format background task completion as system-reminder XML."""
    parts = [
        "<system-reminder>",
        "<task-notification>",
        f"  <run-id>{task_id}</run-id>",
        f"  <status>{status}</status>",
    ]
    if description:
        parts.append(f"  <description>{escape(description)}</description>")
    parts.append(f"  <summary>{escape(summary)}</summary>")
    if result is not None:
        # Truncate long results to avoid flooding context
        truncated = result[:2000] + "..." if len(result) > 2000 else result
        parts.append(f"  <result>{escape(truncated)}</result>")
    if usage:
        parts.append(f"  <usage>{json.dumps(usage)}</usage>")
    parts.append("</task-notification>")
    parts.append("</system-reminder>")
    return "\n".join(parts)


def format_command_notification(
    command_id: str,
    status: Literal["completed", "failed"],
    exit_code: int,
    command_line: str,
    output: str,
    description: str | None = None,
) -> str:
    """Format Bash command completion as system-reminder XML."""
    # Truncate output to 1000 characters
    truncated_output = output[:1000] if output else ""

    # Escape XML special characters
    escaped_command = escape(command_line)
    escaped_output = escape(truncated_output)

    desc_line = f"  <Description>{escape(description)}</Description>\n" if description else ""

    return (
        "<system-reminder>\n"
        "<CommandNotification>\n"
        f"  <CommandId>{command_id}</CommandId>\n"
        f"  <Status>{status}</Status>\n"
        f"  <ExitCode>{exit_code}</ExitCode>\n"
        f"{desc_line}"
        f"  <CommandLine>{escaped_command}</CommandLine>\n"
        f"  <Output>{escaped_output}</Output>\n"
        "</CommandNotification>\n"
        "</system-reminder>"
    )
