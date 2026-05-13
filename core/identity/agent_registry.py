from __future__ import annotations

import hashlib


def get_or_create_agent_id(
    *,
    user_id: str,
    thread_id: str,
    sandbox_type: str,
    user_path: str | None = None,
) -> str:
    # @@@derived-agent-id - runtime identity is already anchored by database rows;
    # do not mint stability by writing a process-local registry file.
    key = f"{user_id}\0{thread_id}\0{sandbox_type}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
