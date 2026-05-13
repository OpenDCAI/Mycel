from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from core.runtime.registry import ToolRegistry
from core.runtime.runner import ToolRunner
from core.tools.task.service import TaskService
from sandbox.thread_context import set_current_thread_id
from storage.runtime import build_tool_task_repo
from tests.fakes.supabase import FakeSupabaseClient


def _call_tool(runner: ToolRunner, name: str, args: dict, call_id: str) -> dict:
    request = SimpleNamespace(tool_call={"name": name, "args": args, "id": call_id})

    def unexpected_upstream(_request):
        raise AssertionError(f"{name} must be handled by ToolRunner registry dispatch")

    message = runner.wrap_tool_call(request, unexpected_upstream)
    assert isinstance(message, ToolMessage)
    return json.loads(message.content)


def test_task_service_persists_through_tool_runner_to_agent_thread_tasks() -> None:
    tables: dict[str, list[dict]] = {}
    repo = build_tool_task_repo(supabase_client=FakeSupabaseClient(tables=tables))
    set_current_thread_id("thread-04")

    registry = ToolRegistry()
    TaskService(registry=registry, repo=repo)
    runner = ToolRunner(registry)

    created = _call_tool(
        runner,
        "TaskCreate",
        {
            "subject": "Route runtime",
            "description": "Persist task through agent.thread_tasks",
            "metadata": {"checkpoint": "04"},
        },
        "call-create",
    )

    assert created["id"] == "1"
    assert tables["agent.thread_tasks"] == [
        {
            "thread_id": "thread-04",
            "task_id": "1",
            "subject": "Route runtime",
            "description": "Persist task through agent.thread_tasks",
            "status": "pending",
            "active_form": None,
            "owner": None,
            "blocks": [],
            "blocked_by": [],
            "metadata": {"checkpoint": "04"},
        }
    ]

    listed = _call_tool(runner, "TaskList", {}, "call-list")
    assert listed["total"] == 1
    assert listed["tasks"][0]["subject"] == "Route runtime"
