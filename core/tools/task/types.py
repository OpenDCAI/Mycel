"""Type definitions for Todo middleware."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task status enum."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Task(BaseModel):
    """Task model for tracking work items."""

    id: str
    subject: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    active_form: str | None = None  # Present continuous form for spinner
    owner: str | None = None
    blocks: list[str] = Field(default_factory=list)  # Task IDs this task blocks
    blocked_by: list[str] = Field(default_factory=list)  # Task IDs blocking this task
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_blocked(self, all_tasks: dict[str, "Task"]) -> bool:
        """Check if this task is blocked by any incomplete tasks."""
        for task_id in self.blocked_by:
            if task_id in all_tasks:
                blocker = all_tasks[task_id]
                if blocker.status != TaskStatus.COMPLETED:
                    return True
        return False

    def to_summary(self) -> dict:
        """Return summary for TaskList."""
        return {
            "id": self.id,
            "subject": self.subject,
            "status": self.status.value,
            "owner": self.owner,
            "blockedBy": [bid for bid in self.blocked_by],
        }

    def to_detail(self) -> dict:
        """Return full details for TaskGet."""
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status.value,
            "activeForm": self.active_form,
            "owner": self.owner,
            "blocks": self.blocks,
            "blockedBy": self.blocked_by,
            "metadata": self.metadata,
        }
