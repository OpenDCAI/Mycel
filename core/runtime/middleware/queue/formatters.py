"""XML formatters for steer messages and task notifications.

Matches Claude Code's system-reminder convention so the LLM treats
injected content as authoritative system instructions.
"""

import json
from html import escape
from typing import Literal


def format_chat_message(content: str, sender_name: str, chat_id: str) -> str:
    """Wrap chat message in XML for agent brain thread.

    @@@external-routing-instruction - the routing instruction MUST be inside
    <system-reminder> and BEFORE the message so the LLM treats it as
    authoritative. Placing it after (as a hint) causes the LLM to sometimes
    respond in plain text, which is invisible to the sender.
    """
    return (
        "<system-reminder>\n"
        f"INCOMING CHAT MESSAGE from [{escape(sender_name)}] in chat {escape(chat_id)}.\n"
        f"RULES:\n"
        f"1. Reply using chat_send(chat_id='{escape(chat_id)}', content=...). Plain text is INVISIBLE.\n"
        f"2. If [{escape(sender_name)}] asks you to notify/inform/tell your owner, "
        f"use tell_owner(message=...).\n"
        f"3. If this is a reply to something you sent earlier, CONTINUE the conversation.\n\n"
        f'<chat-message sender="{escape(sender_name)}" chat="{escape(chat_id)}">\n'
        f"{content}\n"
        "</chat-message>\n"
        "</system-reminder>"
    )


def format_steer_reminder(content: str) -> str:
    """Format user steer message as system-reminder XML."""
    return (
        "<system-reminder>\n"
        "The user sent a new message while you were working:\n"
        f"{content}\n\n"
        "IMPORTANT: After completing your current task, "
        "you MUST address the user's message above. Do not ignore it.\n"
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
    """Format Bash command completion as system-reminder XML.

    Args:
        command_id: Command ID
        status: Completion status
        exit_code: Exit code
        command_line: Command line
        output: Output content (truncated to first 1000 characters)
        description: Human-readable description for frontend rendering

    Returns:
        XML formatted notification string
    """
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
