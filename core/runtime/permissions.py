from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPermissionContext:
    is_read_only: bool
    is_destructive: bool = False


def can_auto_approve(context: ToolPermissionContext) -> bool:
    return context.is_read_only and not context.is_destructive
