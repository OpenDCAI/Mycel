"""XML formatters for steer messages and task notifications.

Matches Claude Code's system-reminder convention so the LLM treats
injected content as authoritative system instructions.
Frontend strips <system-reminder> tags — agent sees full XML, user sees clean text.
"""

import json
from html import escape
from typing import Literal


def format_agent_message(sender_name: str, message: str) -> str:
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
    status: Literal["completed", "failed", "cancelled"],
    exit_code: int,
    command_line: str,
    output: str,
    description: str | None = None,
) -> str:
    truncated_output = output[:1000] if output else ""

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
