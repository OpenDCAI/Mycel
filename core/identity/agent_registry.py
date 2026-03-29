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
    member: str,
    thread_id: str,
    sandbox_type: str,
    member_path: str | None = None,
) -> str:
    """Get existing agent_id for this member+thread combo, or create a new one."""
    instances = _load()

    for aid, info in instances.items():
        if info.get("member") == member and info.get("thread_id") == thread_id and info.get("sandbox_type") == sandbox_type:
            return aid

    import time
    agent_id = uuid.uuid4().hex[:8]
    entry: dict[str, Any] = {
        "member": member,
        "thread_id": thread_id,
        "sandbox_type": sandbox_type,
        "created_at": int(time.time()),
    }
    if member_path:
        entry["member_path"] = member_path

    instances[agent_id] = entry
    _save(instances)
    logger.info("Created agent identity %s for member=%s thread=%s", agent_id, member, thread_id)
    return agent_id
