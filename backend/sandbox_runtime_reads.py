"""Shared sandbox runtime read helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


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
                    "lease_id": row.get("lease_id"),
                    "instance_id": row.get("instance_id"),
                    "chat_session_id": row.get("chat_session_id"),
                    "source": row.get("source", "unknown"),
                    "inspect_visible": row.get("inspect_visible", True),
                }
            )

    # @@@stable-runtime-order - Keep deterministic ordering across refreshes/providers.
    def _to_ts(value: Any) -> float:
        if not value or not isinstance(value, str):
            return 0.0
        try:
            return datetime.fromisoformat(value).timestamp()
        except Exception:
            return 0.0

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
