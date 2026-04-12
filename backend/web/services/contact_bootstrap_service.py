"""Small contact bootstrap helpers for owner-created agents."""

from __future__ import annotations

import time
from typing import Any

from storage.contracts import ContactEdgeRow


def ensure_owner_agent_contact(contact_repo: Any, owner_user_id: str, agent_user_id: str, *, now: float | None = None) -> None:
    if contact_repo is None:
        raise RuntimeError("contact_repo is required for owner-agent contact bootstrap")
    timestamp = time.time() if now is None else now
    contact_repo.upsert(
        ContactEdgeRow(
            source_user_id=owner_user_id,
            target_user_id=agent_user_id,
            kind="normal",
            state="active",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
