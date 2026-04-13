from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from backend.web.core import storage_factory
from core.runtime.registry import ToolRegistry
from core.runtime.runner import ToolRunner
from core.tools.task.service import TaskService
from sandbox.thread_context import set_current_thread_id
from tests.fakes.supabase import FakeSupabaseClient


def _call_tool(runner: ToolRunner, name: str, args: dict, call_id: str) -> dict:
    request = SimpleNamespace(tool_call={"name": name, "args": args, "id": call_id})

    def unexpected_upstream(_request):
        raise AssertionError(f"{name} must be handled by ToolRunner registry dispatch")

    message = runner.wrap_tool_call(request, unexpected_upstream)
    assert isinstance(message, ToolMessage)
    return json.loads(message.content)


def test_task_tools_persist_to_agent_thread_tasks_through_tool_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setenv("LEON_DB_SCHEMA", "staging")
    tables: dict[str, list[dict]] = {}
    monkeypatch.setattr(storage_factory, "_supabase_client", lambda: FakeSupabaseClient(tables))
    set_current_thread_id("thread_02e")

    registry = ToolRegistry()
    TaskService(registry=registry)
    runner = ToolRunner(registry)

    created = _call_tool(
        runner,
        "TaskCreate",
        {
            "subject": "Prove task tool surface",
            "description": "Persist through ToolRunner into agent.thread_tasks",
            "active_form": "Proving task tool surface",
            "metadata": {"checkpoint": "02e"},
        },
        "call-create",
    )
    assert created["id"] == "1"
    assert tables["agent.thread_tasks"] == [
        {
            "thread_id": "thread_02e",
            "task_id": "1",
            "subject": "Prove task tool surface",
            "description": "Persist through ToolRunner into agent.thread_tasks",
            "status": "pending",
            "active_form": "Proving task tool surface",
            "owner": None,
            "blocks": [],
            "blocked_by": [],
            "metadata": {"checkpoint": "02e"},
        }
    ]

    listed = _call_tool(runner, "TaskList", {}, "call-list")
    assert listed["total"] == 1
    assert listed["tasks"][0]["subject"] == "Prove task tool surface"

    detail = _call_tool(runner, "TaskGet", {"task_id": "1"}, "call-get")
    assert detail["metadata"] == {"checkpoint": "02e"}

    updated = _call_tool(
        runner,
        "TaskUpdate",
        {"task_id": "1", "status": "in_progress", "owner": "agent_02e", "metadata": {"verified": True}},
        "call-update",
    )
    assert updated["task"]["status"] == "in_progress"
    assert tables["agent.thread_tasks"][0]["status"] == "in_progress"
    assert tables["agent.thread_tasks"][0]["owner"] == "agent_02e"
    assert tables["agent.thread_tasks"][0]["metadata"] == {"checkpoint": "02e", "verified": True}
