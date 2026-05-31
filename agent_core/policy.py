"""PermissionPolicy — a pluggable allow/deny/ask gate for tool calls.

Pass to ``Agent(can_use_tool=policy)``. ``ToolRunner`` calls it before every
registered tool and blocks on ``deny``/``ask``. Matching is by tool name with
fnmatch globs; precedence is deny > allow > ask > (block_destructive) > default.

Note: ``ask`` requires an interactive permission surface
(``request_permission`` on the context). With no surface wired (the standalone
default) an ``ask`` resolves to a deny — fail-closed.
"""

from __future__ import annotations

import fnmatch
from typing import Any


class PermissionPolicy:
    def __init__(
        self,
        *,
        default: str = "allow",
        allow: list[str] | None = None,
        deny: list[str] | None = None,
        ask: list[str] | None = None,
        block_destructive: bool = False,
    ) -> None:
        self.default = default
        self.allow = list(allow or [])
        self.deny = list(deny or [])
        self.ask = list(ask or [])
        self.block_destructive = block_destructive

    @staticmethod
    def _matches(name: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)

    def decide(self, name: str, *, is_destructive: bool = False) -> str:
        if self._matches(name, self.deny):
            return "deny"
        if self._matches(name, self.allow):
            return "allow"
        if self._matches(name, self.ask):
            return "ask"
        if self.block_destructive and is_destructive:
            return "ask"
        return self.default

    def __call__(self, name: str, args: dict, permission_context: Any, request: Any) -> str | dict:
        is_destructive = bool(getattr(permission_context, "is_destructive", False))
        decision = self.decide(name, is_destructive=is_destructive)
        if decision == "allow":
            return "allow"
        return {"decision": decision, "message": f"tool '{name}' {decision} by permission policy"}
