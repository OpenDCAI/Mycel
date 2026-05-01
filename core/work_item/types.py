from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    id: str
    subject: str
    description: str
    status: Any
    active_form: str | None = None
    owner: str | None = None
    blocks: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_blocked(self, all_items: dict[str, WorkItem]) -> bool:
        for item_id in self.blocked_by:
            if item_id in all_items:
                blocker = all_items[item_id]
                if _status_value(blocker.status) != "completed":
                    return True
        return False

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "status": _status_value(self.status),
            "owner": self.owner,
            "blockedBy": [item_id for item_id in self.blocked_by],
        }

    def to_detail(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": _status_value(self.status),
            "activeForm": self.active_form,
            "owner": self.owner,
            "blocks": self.blocks,
            "blockedBy": self.blocked_by,
            "metadata": self.metadata,
        }


def _status_value(status: Any) -> str:
    value = getattr(status, "value", status)
    return str(value)
