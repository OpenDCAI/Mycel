from __future__ import annotations

import storage.contracts as storage_contracts
from core.tools.task.types import Task, TaskStatus
from core.work_item.types import WorkItem
from storage.contracts import WorkItemRepo
from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_agent_task_uses_work_item_base_without_chat_workflow_fields() -> None:
    task = Task(
        id="1",
        subject="Keep agent todo simple",
        description="Task remains an agent-private todo surface.",
        status=TaskStatus.PENDING,
    )

    assert isinstance(task, WorkItem)
    assert task.to_summary() == {
        "id": "1",
        "subject": "Keep agent todo simple",
        "status": "pending",
        "owner": None,
        "blockedBy": [],
    }
    assert "review_event_id" not in Task.model_fields
    assert "review_rationale" not in Task.model_fields
    assert "evidence" not in Task.model_fields


def test_work_item_repo_protocol_names_scope_without_chat_or_thread_bias() -> None:
    annotations = WorkItemRepo.next_id.__annotations__

    assert "scope_id" in annotations
    assert "thread_id" not in annotations
    assert "chat_id" not in annotations


def test_agent_task_repo_conforms_to_work_item_repo_protocol() -> None:
    repo: WorkItemRepo = SupabaseToolTaskRepo(FakeSupabaseClient(tables={}))

    assert repo.next_id("thread-scope") == "1"


def test_tool_task_repo_protocol_name_is_not_public_alias() -> None:
    assert not hasattr(storage_contracts, "ToolTaskRepo")
