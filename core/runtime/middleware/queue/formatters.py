"""XML formatters for steer messages and task notifications.

Matches Claude Code's system-reminder convention so the LLM treats
injected content as authoritative system instructions.
"""

import json
from html import escape
from typing import Literal


def format_chat_message(content: str, sender_name: str, chat_id: str) -> str:
    """Wrap incoming chat message for agent brain thread.

    @@@external-routing-instruction - wrapped in <system-reminder> so the LLM
    treats routing rules as authoritative. Frontend strips this via
    stripSystemReminders regex.
    """
    return (
        "<system-reminder>\n"
        f"[{escape(sender_name)}] sent you a chat message.\n\n"
        f'<chat-message sender="{escape(sender_name)}" chat="{escape(chat_id)}">\n'
        f"{content}\n"
        "</chat-message>\n\n"
        "You are now in a private context — your owner cannot see your text output here.\n"
        f"- To [{escape(sender_name)}]: chat_send(chat_id='{escape(chat_id)}', content=...)\n"
        "- To your owner: tell_owner(message=...)\n"
        "- Plain text goes nowhere. Nobody sees it.\n"
        "</system-reminder>"
    )


def format_owner_message(content: str) -> str:
    """Wrap owner's direct message with visibility context.

    @@@owner-context-shift — after external messages, the agent may not realize
    its text output is visible again. This hint restores awareness.
    """
    return (
        f"{content}\n\n"
        "<system-reminder>\n"
        "Context shift: you are now talking to your owner. Your text output is visible to them.\n"
        "</system-reminder>"
    )


def format_owner_steer(content: str) -> str:
    """Owner sent a message while agent was busy."""
    return (
        "<system-reminder>\n"
        "Your owner sent a message while you were working:\n"
        f"{content}\n\n"
        "Context shift: you are now talking to your owner. Your text output is visible to them. Address their message.\n"
        "</system-reminder>"
    )


# Alias for TUI and tests that still import the old name
format_steer_reminder = format_owner_steer


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
        "<background-notification>",
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
    parts.append("</background-notification>")
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
