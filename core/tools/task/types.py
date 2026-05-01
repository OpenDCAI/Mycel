from enum import StrEnum

from core.work_item.types import WorkItem


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Task(WorkItem):
    status: TaskStatus = TaskStatus.PENDING
