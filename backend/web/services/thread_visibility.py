"""User-visible thread projection helpers."""

from __future__ import annotations

from typing import Any


def _branch_index(row: dict[str, Any]) -> int:
    return int(row.get("branch_index") or 0)


def _is_better_canonical_thread(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    if bool(candidate.get("is_main")) != bool(current.get("is_main")):
        return bool(candidate.get("is_main"))
    return _branch_index(candidate) < _branch_index(current)


def canonical_owner_threads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one user-visible thread per agent user, preserving first agent order."""
    order: list[str] = []
    by_agent: dict[str, dict[str, Any]] = {}
    for row in rows:
        agent_user_id = str(row.get("agent_user_id") or "").strip()
        if not agent_user_id:
            raise RuntimeError(f"Owner-visible thread {row.get('id')} is missing agent_user_id")
        if agent_user_id not in by_agent:
            order.append(agent_user_id)
            by_agent[agent_user_id] = row
            continue
        if _is_better_canonical_thread(row, by_agent[agent_user_id]):
            by_agent[agent_user_id] = row
    return [by_agent[agent_user_id] for agent_user_id in order]
