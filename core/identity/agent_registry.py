"""Agent instance identity persistence.

Stores agent identity mappings in ~/.leon/agent_instances.json.
Backend-internal only — agent_id does not leak to SSE events.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from config.user_paths import user_home_path, user_home_read_candidates

logger = logging.getLogger(__name__)

INSTANCES_FILE = user_home_path("agent_instances.json")


def _load() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in user_home_read_candidates("agent_instances.json"):
        if not path.exists():
            continue
        try:
            merged.update(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load agent_instances.json: %s", e)
    return merged


def _save(data: dict[str, Any]) -> None:
    INSTANCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTANCES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_or_create_agent_id(
    *,
    user_id: str,
    thread_id: str,
    sandbox_type: str,
    user_path: str | None = None,
) -> str:
    """Get existing agent_id for this user+thread combo, or create a new one."""
    instances = _load()

    for aid, info in instances.items():
        if info.get("user_id") == user_id and info.get("thread_id") == thread_id and info.get("sandbox_type") == sandbox_type:
            return aid

    import time

    agent_id = uuid.uuid4().hex[:8]
    entry: dict[str, Any] = {
        "user_id": user_id,
        "thread_id": thread_id,
        "sandbox_type": sandbox_type,
        "created_at": int(time.time()),
    }
    if user_path:
        entry["user_path"] = user_path

    instances[agent_id] = entry
    _save(instances)
    logger.info("Created agent identity %s for user_id=%s thread=%s", agent_id, user_id, thread_id)
    return agent_id
