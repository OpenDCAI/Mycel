"""Thread-scoped MCP instruction delta injection.

Mycel does not have CC's attachment plane. Keep this contract smaller:
- MCP server configs may carry `instructions`
- the loop stores which server names have already been announced per thread
- on the next turn after a change, inject one delta SystemMessage
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import SystemMessage

from core.runtime.middleware import AgentMiddleware
from core.runtime.state import AppState

_DELTA_TAG = "mcp_instructions_delta"


def _format_instruction_block(server_name: str, instructions: str) -> str:
    return f"## {server_name}\n{instructions.strip()}"


def _render_delta_message(*, added: dict[str, str], removed: list[str]) -> SystemMessage:
    payload = {
        "added_names": sorted(added),
        "removed_names": sorted(removed),
    }
    blocks = [
        "<system-reminder>",
        f"<{_DELTA_TAG}>{json.dumps(payload, ensure_ascii=False)}</{_DELTA_TAG}>",
        "MCP server instructions changed for this thread.",
    ]
    if added:
        blocks.append("Use the newly available MCP instructions below for subsequent turns:")
        blocks.extend(_format_instruction_block(name, added[name]) for name in sorted(added))
    if removed:
        blocks.append("The following MCP servers are no longer active for this thread:")
        blocks.extend(f"- {name}" for name in sorted(removed))
    blocks.append("</system-reminder>")
    return SystemMessage(content="\n".join(blocks))


class McpInstructionsDeltaMiddleware(AgentMiddleware):
    """Injects MCP instruction deltas once per thread when the connected set changes."""

    def __init__(
        self,
        *,
        get_instruction_blocks: Callable[[], dict[str, str]],
        get_app_state: Callable[[], AppState | None],
    ) -> None:
        self._get_instruction_blocks = get_instruction_blocks
        self._get_app_state = get_app_state

    def before_model(self, state: dict[str, Any], runtime: Any = None, config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        app_state = self._get_app_state()
        if app_state is None:
            return None

        config = config or {}
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        current_blocks = {name: block for name, block in self._get_instruction_blocks().items() if block.strip()}
        announced_blocks = {
            name: block
            for name, block in app_state.announced_mcp_instruction_blocks.get(thread_id, {}).items()
            if isinstance(name, str) and isinstance(block, str) and block.strip()
        }

        added_names = sorted(name for name, block in current_blocks.items() if announced_blocks.get(name) != block)
        removed_names = sorted(name for name in announced_blocks if name not in current_blocks)
        if not added_names and not removed_names:
            return None

        app_state.announced_mcp_instruction_blocks[thread_id] = dict(current_blocks)
        added = {name: current_blocks[name] for name in added_names}
        return {"messages": [_render_delta_message(added=added, removed=removed_names)]}
