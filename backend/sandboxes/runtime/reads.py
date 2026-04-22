"""Shared sandbox runtime read helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _is_visible_owner_thread(thread_id: Any) -> bool:
    raw = str(thread_id or "").strip()
    return bool(raw) and not raw.startswith("subagent-") and raw not in {"(orphan)", "(untracked)"}


def _runtime_row_rank(row: dict[str, Any]) -> tuple[int, float]:
    return (
        1 if _is_visible_owner_thread(row.get("thread_id")) else 0,
        _to_ts(row.get("last_active")) or _to_ts(row.get("created_at")),
    )


def _runtime_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("provider") or ""),
        str(row.get("session_id") or ""),
    )


def _collapse_owner_runtime_rows(runtimes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: dict[tuple[str, str], dict[str, Any]] = {}
    ordered_keys: list[tuple[str, str]] = []
    for row in runtimes:
        key = _runtime_identity(row)
        current = collapsed.get(key)
        if current is None:
            collapsed[key] = row
            ordered_keys.append(key)
            continue
        # @@@owner-runtime-collapse - owner-facing runtime surfaces should expose
        # one row per provider/runtime identity, not one row per subagent thread
        # that happens to reuse the same lower runtime handle.
        if _runtime_row_rank(row) > _runtime_row_rank(current):
            collapsed[key] = row
    return [collapsed[key] for key in ordered_keys]


def _to_ts(value: Any) -> float:
    if not value or not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return 0.0


def load_all_sandbox_runtimes(managers: dict) -> list[dict]:
    """Load sandbox runtime rows from all managers in parallel."""
    runtimes: list[dict] = []
    if not managers:
        return runtimes
    for provider_name, manager in managers.items():
        rows = manager.list_sessions()
        for row in rows:
            runtimes.append(
                {
                    "session_id": row["session_id"],
                    "thread_id": row["thread_id"],
                    "provider": row.get("provider", provider_name),
                    "status": row.get("status", "running"),
                    "created_at": row.get("created_at"),
                    "last_active": row.get("last_active"),
                    "sandbox_runtime_id": row.get("sandbox_runtime_id"),
                    "instance_id": row.get("instance_id"),
                    "chat_session_id": row.get("chat_session_id"),
                    "source": row.get("source", "unknown"),
                    "inspect_visible": row.get("inspect_visible", True),
                }
            )

    runtimes = _collapse_owner_runtime_rows(runtimes)

    # @@@stable-runtime-order - Keep deterministic ordering across refreshes/providers.
    runtimes.sort(
        key=lambda row: (
            -_to_ts(row.get("created_at")),
            -_to_ts(row.get("last_active")),
            str(row.get("provider") or ""),
            str(row.get("thread_id") or ""),
            str(row.get("session_id") or ""),
        )
    )
    return runtimes


def find_runtime_and_manager(
    runtimes: list[dict],
    managers: dict,
    runtime_id: str,
    provider_name: str | None = None,
) -> tuple[dict | None, Any | None]:
    """Find sandbox runtime by external ID/prefix (+optional provider), return (runtime, manager)."""
    candidates: list[dict] = []
    for runtime in runtimes:
        if provider_name and runtime.get("provider") != provider_name:
            continue
        sid = str(runtime.get("session_id") or "")
        if sid == runtime_id or sid.startswith(runtime_id):
            candidates.append(runtime)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        chosen = candidates[0]
        return chosen, managers.get(chosen["provider"])
    exact = [runtime for runtime in candidates if str(runtime.get("session_id") or "") == runtime_id]
    if len(exact) == 1:
        chosen = exact[0]
        return chosen, managers.get(chosen["provider"])
    raise RuntimeError(f"Ambiguous runtime id '{runtime_id}'. Specify provider query param.")
