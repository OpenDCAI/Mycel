from __future__ import annotations

from typing import Any

from storage.runtime import build_thread_repo, build_user_repo


def canonical_owner_threads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        current = by_agent[agent_user_id]
        if bool(row.get("is_main")) != bool(current.get("is_main")):
            if bool(row.get("is_main")):
                by_agent[agent_user_id] = row
            continue
        if int(row.get("branch_index") or 0) < int(current.get("branch_index") or 0):
            by_agent[agent_user_id] = row
    return [by_agent[agent_user_id] for agent_user_id in order]


def thread_owners(thread_ids: list[str], user_repo: Any = None, thread_repo: Any = None) -> dict[str, dict[str, str | None]]:
    unique = sorted({tid for tid in thread_ids if tid})
    if not unique:
        return {}

    repo = thread_repo
    own_thread_repo = False
    if repo is None:
        repo = build_thread_repo()
        own_thread_repo = True
    try:
        refs: dict[str, str] = {}
        for data in repo.list_by_ids(unique):
            tid = str(data.get("id") or "").strip()
            if not tid:
                continue
            agent_ref = str(data.get("agent_user_id") or "").strip() if data else ""
            if agent_ref:
                refs[tid] = agent_ref
    finally:
        if own_thread_repo:
            repo.close()

    agent_user_meta: dict[str, dict[str, str | None]] = {}
    if refs:
        repo = user_repo
        own_user_repo = False
        if repo is None:
            repo = build_user_repo()
            own_user_repo = True
        try:
            agent_user_meta = {
                user.id: {
                    "agent_name": user.display_name,
                    "avatar_url": f"/api/users/{user.id}/avatar" if user.id and user.avatar else None,
                }
                for user in repo.list_all()
                if user.id and user.display_name
            }
        finally:
            if own_user_repo:
                repo.close()

    owners: dict[str, dict[str, str | None]] = {}
    for thread_id in thread_ids:
        agent_ref = refs.get(thread_id)
        if not agent_ref:
            owners[thread_id] = {"agent_user_id": None, "agent_name": "未绑定Agent", "avatar_url": None}
            continue
        owners[thread_id] = {
            "agent_user_id": agent_ref,
            "agent_name": (agent_user_meta.get(agent_ref) or {}).get("agent_name") or agent_ref,
            "avatar_url": (agent_user_meta.get(agent_ref) or {}).get("avatar_url"),
        }
    return owners
