from __future__ import annotations

from typing import Any


class ToolCallDedup:
    def __init__(self) -> None:
        self._checkpoint_ids: set[str] = set()
        self._emitted_ids: set[str] = set()

    async def prepopulate_from_checkpoint(self, agent: Any, config: dict[str, Any]) -> None:
        pre_state = await agent.agent.aget_state(config)
        if not pre_state or not pre_state.values:
            return
        for msg in pre_state.values.get("messages", []):
            if msg.__class__.__name__ != "AIMessage":
                continue
            for tc in getattr(msg, "tool_calls", []):
                tc_id = tc.get("id")
                if tc_id:
                    self._checkpoint_ids.add(tc_id)
                    self._emitted_ids.add(tc_id)

    def is_duplicate(self, tc_id: str | None) -> bool:
        return bool(tc_id) and tc_id in self._checkpoint_ids

    def already_emitted(self, tc_id: str | None) -> bool:
        return bool(tc_id) and tc_id in self._emitted_ids

    def register(self, tc_id: str | None) -> None:
        if tc_id:
            self._emitted_ids.add(tc_id)
