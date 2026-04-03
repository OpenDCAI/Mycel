from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PERMISSION_RULE_SOURCES = (
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "session",
)


@dataclass(frozen=True)
class ToolPermissionContext:
    is_read_only: bool
    is_destructive: bool = False
    alwaysAllowRules: dict[str, list[str]] | None = None
    alwaysDenyRules: dict[str, list[str]] | None = None
    alwaysAskRules: dict[str, list[str]] | None = None
    allowManagedPermissionRulesOnly: bool = False


def can_auto_approve(context: ToolPermissionContext) -> bool:
    return context.is_read_only and not context.is_destructive


def _active_sources(context: ToolPermissionContext) -> tuple[str, ...]:
    if context.allowManagedPermissionRulesOnly:
        return ("policySettings",)
    return PERMISSION_RULE_SOURCES


def _extract_tool_name(rule: str) -> str:
    rule = rule.strip()
    open_paren = rule.find("(")
    return rule if open_paren == -1 else rule[:open_paren]


def _find_matching_rule(
    rule_buckets: dict[str, list[str]] | None,
    tool_name: str,
    *,
    sources: tuple[str, ...],
) -> str | None:
    if not rule_buckets:
        return None
    for source in sources:
        for rule in rule_buckets.get(source, []):
            if _extract_tool_name(rule) == tool_name:
                return rule
    return None


def evaluate_permission_rules(
    tool_name: str,
    context: ToolPermissionContext,
) -> dict[str, Any] | None:
    sources = _active_sources(context)

    deny_rule = _find_matching_rule(context.alwaysDenyRules, tool_name, sources=sources)
    if deny_rule is not None:
        return {"decision": "deny", "message": f"Permission denied by rule: {deny_rule}"}

    ask_rule = _find_matching_rule(context.alwaysAskRules, tool_name, sources=sources)
    if ask_rule is not None:
        return {"decision": "ask", "message": f"Permission required by rule: {ask_rule}"}

    allow_rule = _find_matching_rule(context.alwaysAllowRules, tool_name, sources=sources)
    if allow_rule is not None:
        return {"decision": "allow", "message": f"Permission allowed by rule: {allow_rule}"}

    return None
