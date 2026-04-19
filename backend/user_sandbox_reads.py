"""Shared user-scoped sandbox read helpers."""

from __future__ import annotations

import json
from typing import Any

from backend.avatar_urls import avatar_url
from backend.thread_projection import canonical_owner_threads
from backend.virtual_threads import is_virtual_thread_id
from sandbox.recipes import default_recipe_id, normalize_recipe_snapshot, provider_type_from_name
from storage.models import map_sandbox_state_to_display_status
from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo


def _sandbox_agent_payload(
    thread_id: str,
    agent_user_id: str,
    agent_user: Any,
    *,
    avatar_url_fn=avatar_url,
) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "agent_user_id": agent_user_id,
        "agent_name": agent_user.display_name,
        "avatar_url": avatar_url_fn(agent_user.id, bool(agent_user.avatar)),
    }


def _apply_sandbox_recipe(sandbox_row: dict[str, Any], provider_name: str, raw_recipe: Any) -> None:
    provider_type = provider_type_from_name(provider_name)
    recipe_snapshot = (
        normalize_recipe_snapshot(provider_type, json.loads(str(raw_recipe)), provider_name=provider_name)
        if raw_recipe
        else normalize_recipe_snapshot(provider_type, provider_name=provider_name)
    )
    sandbox_row["recipe_id"] = recipe_snapshot["id"] or sandbox_row.get("recipe_id") or default_recipe_id(provider_name)
    sandbox_row["recipe"] = recipe_snapshot
    sandbox_row["recipe_name"] = recipe_snapshot["name"]


def _is_user_visible_sandbox_thread(
    thread_id: str | None,
    *,
    is_virtual_thread_id_fn=is_virtual_thread_id,
) -> bool:
    raw = str(thread_id or "").strip()
    return bool(raw) and not raw.startswith("subagent-") and not is_virtual_thread_id_fn(raw)


def _is_user_visible_sandbox_state(sandbox_row: dict[str, Any]) -> bool:
    status = map_sandbox_state_to_display_status(sandbox_row.get("observed_state"), sandbox_row.get("desired_state"))
    return status in {"running", "paused"}


def _list_user_runtime_rows(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
    include_runtime_session_id: bool = False,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    canonical_owner_threads_fn=canonical_owner_threads,
    avatar_url_fn=avatar_url,
    is_virtual_thread_id_fn=is_virtual_thread_id,
) -> list[dict[str, Any]]:
    monitor_repo = make_sandbox_monitor_repo_fn()
    if thread_repo is None or user_repo is None:
        raise RuntimeError("thread_repo and user_repo are required for user sandbox runtime rows")
    try:
        threads_by_id = {str(thread.get("id") or ""): thread for thread in thread_repo.list_by_owner_user_id(user_id) if thread.get("id")}
        users_by_id = {str(user.id): user for user in user_repo.list_by_owner_user_id(user_id)}
        rows = monitor_repo.query_sandboxes()
        grouped: dict[str, dict[str, Any]] = {}
        runtime_session_ids: dict[str, str | None] = {}
        for row in rows:
            sandbox_id = str(row.get("sandbox_id") or "").strip()
            if not sandbox_id:
                continue
            runtime_session_id = runtime_session_ids.get(sandbox_id)
            if sandbox_id not in runtime_session_ids:
                runtime_session_id = str(row.get("current_instance_id") or "").strip() or None
                if include_runtime_session_id and runtime_session_id is None:
                    runtime_session_id = monitor_repo.query_sandbox_instance_id(sandbox_id)
                runtime_session_ids[sandbox_id] = runtime_session_id
            group = grouped.setdefault(
                sandbox_id,
                {
                    "sandbox_id": sandbox_id,
                    "provider_name": str(row.get("provider_name") or "local"),
                    "recipe_id": str(row.get("recipe_id") or "") or None,
                    "recipe": row.get("recipe_json"),
                    "observed_state": row.get("observed_state"),
                    "desired_state": row.get("desired_state"),
                    "created_at": row.get("created_at"),
                    "cwd": row.get("cwd"),
                    "_visible_threads": [],
                },
            )
            if include_runtime_session_id and runtime_session_id and not group.get("runtime_session_id"):
                group["runtime_session_id"] = runtime_session_id
            thread_id = str(row.get("thread_id") or "").strip()
            if not _is_user_visible_sandbox_thread(thread_id, is_virtual_thread_id_fn=is_virtual_thread_id_fn):
                continue
            thread = threads_by_id.get(thread_id)
            if thread is None:
                continue
            agent_user_id = str(thread.get("agent_user_id") or "").strip()
            if not agent_user_id:
                continue
            agent_user = users_by_id.get(agent_user_id)
            if agent_user is None:
                continue
            group["_visible_threads"].append({"id": thread_id, **thread})
            if not group["cwd"] and row.get("cwd"):
                group["cwd"] = row.get("cwd")

        sandbox_rows: list[dict[str, Any]] = []
        for sandbox_row in grouped.values():
            visible_threads = canonical_owner_threads_fn(sandbox_row.pop("_visible_threads"))
            if not visible_threads:
                continue
            if not _is_user_visible_sandbox_state(sandbox_row):
                continue
            thread_ids: list[str] = []
            agents: list[dict[str, Any]] = []
            for thread in visible_threads:
                thread_id = str(thread.get("id") or "").strip()
                agent_user_id = str(thread.get("agent_user_id") or "").strip()
                agent_user = users_by_id.get(agent_user_id)
                if not thread_id or not agent_user_id or agent_user is None:
                    continue
                thread_ids.append(thread_id)
                agents.append(
                    _sandbox_agent_payload(
                        thread_id,
                        agent_user_id,
                        agent_user,
                        avatar_url_fn=avatar_url_fn,
                    )
                )
            if not thread_ids:
                continue
            sandbox_row["thread_ids"] = thread_ids
            sandbox_row["agents"] = agents
            provider_name = sandbox_row["provider_name"]
            _apply_sandbox_recipe(sandbox_row, provider_name, sandbox_row["recipe"])
            sandbox_rows.append(sandbox_row)
        return sandbox_rows
    finally:
        monitor_repo.close()


def _sandbox_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "lease_id"}


def list_user_sandboxes(
    user_id: str,
    *,
    thread_repo: Any = None,
    user_repo: Any = None,
    make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo,
    canonical_owner_threads_fn=canonical_owner_threads,
    avatar_url_fn=avatar_url,
    is_virtual_thread_id_fn=is_virtual_thread_id,
) -> list[dict[str, Any]]:
    rows = _list_user_runtime_rows(
        user_id,
        thread_repo=thread_repo,
        user_repo=user_repo,
        make_sandbox_monitor_repo_fn=make_sandbox_monitor_repo_fn,
        canonical_owner_threads_fn=canonical_owner_threads_fn,
        avatar_url_fn=avatar_url_fn,
        is_virtual_thread_id_fn=is_virtual_thread_id_fn,
    )
    return [_sandbox_summary(row) for row in rows]
