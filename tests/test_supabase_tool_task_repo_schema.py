from __future__ import annotations

import pytest

from core.tools.task.types import Task, TaskStatus
from storage.providers.supabase.tool_task_repo import SupabaseToolTaskRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_tool_task_repo_uses_agent_thread_tasks_under_staging_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    client = FakeSupabaseClient(
        tables={
            "agent.thread_tasks": [
                {
                    "thread_id": "thread_1",
                    "task_id": "1",
                    "subject": "Route runtime",
                    "description": "Use domain table",
                    "status": "pending",
                    "active_form": None,
                    "owner": "agent",
                    "blocks": [],
                    "blocked_by": [],
                    "metadata": {},
                }
            ],
        }
    )

    tasks = SupabaseToolTaskRepo(client).list_all("thread_1")

    assert tasks == [
        Task(
            id="1",
            subject="Route runtime",
            description="Use domain table",
            status=TaskStatus.PENDING,
            owner="agent",
        )
    ]


def test_tool_task_repo_rejects_unknown_runtime_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_DB_SCHEMA", "identity")

    with pytest.raises(RuntimeError):
        SupabaseToolTaskRepo(FakeSupabaseClient()).list_all("thread_1")
