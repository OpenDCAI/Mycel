"""Tests for TaskBoardMiddleware — agent tools for panel_tasks board."""

import json

import pytest

from backend.web.services import task_service


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Redirect task_service to a temporary SQLite database."""
    from storage.providers.sqlite.panel_task_repo import SQLitePanelTaskRepo

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(task_service, "make_panel_task_repo", lambda: SQLitePanelTaskRepo(db_path=db_path))


@pytest.fixture()
def middleware():
    from backend.taskboard.middleware import TaskBoardMiddleware

    mw = TaskBoardMiddleware(thread_id="test-thread-001")
    return mw


def _make_tool_call(name: str, args: dict, call_id: str = "tc_1") -> dict:
    return {"name": name, "id": call_id, "args": args}


def _parse_result(tool_message) -> dict:
    return json.loads(tool_message.content)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


class TestToolSchemas:
    def test_schemas_registered(self, middleware):
        schemas = middleware._get_tool_schemas()
        names = {s["function"]["name"] for s in schemas}
        expected = {
            "ListBoardTasks",
            "ClaimTask",
            "UpdateTaskProgress",
            "CompleteTask",
            "FailTask",
            "CreateBoardTask",
        }
        assert names == expected

    def test_schema_format(self, middleware):
        schemas = middleware._get_tool_schemas()
        for s in schemas:
            assert s["type"] == "function"
            assert "name" in s["function"]
            assert "description" in s["function"]
            assert "parameters" in s["function"]
            params = s["function"]["parameters"]
            assert params["type"] == "object"
            assert "properties" in params


# ---------------------------------------------------------------------------
# CreateBoardTask
# ---------------------------------------------------------------------------


class TestCreateBoardTask:
    def test_creates_task_with_source_agent(self, middleware):
        call = _make_tool_call("CreateBoardTask", {"Title": "Do something"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert "task" in result
        task = result["task"]
        assert task["title"] == "Do something"
        assert task["source"] == "agent"
        assert task["status"] == "pending"

    def test_creates_with_description_and_priority(self, middleware):
        call = _make_tool_call(
            "CreateBoardTask",
            {"Title": "Important", "Description": "Details here", "Priority": "high"},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        task = result["task"]
        assert task["title"] == "Important"
        assert task["description"] == "Details here"
        assert task["priority"] == "high"

    def test_default_priority_is_medium(self, middleware):
        call = _make_tool_call("CreateBoardTask", {"Title": "Default prio"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)
        assert result["task"]["priority"] == "medium"


# ---------------------------------------------------------------------------
# ClaimTask
# ---------------------------------------------------------------------------


class TestClaimTask:
    def test_sets_running_and_thread_id(self, middleware):
        created = task_service.create_task(title="claim me")
        call = _make_tool_call("ClaimTask", {"TaskId": created["id"]})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        task = result["task"]
        assert task["status"] == "running"
        assert task["thread_id"] == "test-thread-001"
        assert task["started_at"] > 0

    def test_claim_nonexistent_returns_error(self, middleware):
        call = _make_tool_call("ClaimTask", {"TaskId": "ghost"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)
        assert "error" in result


# ---------------------------------------------------------------------------
# CompleteTask
# ---------------------------------------------------------------------------


class TestCompleteTask:
    def test_sets_completed_status_and_result(self, middleware):
        created = task_service.create_task(title="finish me")
        call = _make_tool_call(
            "CompleteTask",
            {"TaskId": created["id"], "Result": "All done, 5 files changed"},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        task = result["task"]
        assert task["status"] == "completed"
        assert task["result"] == "All done, 5 files changed"
        assert task["progress"] == 100
        assert task["completed_at"] > 0

    def test_complete_nonexistent_returns_error(self, middleware):
        call = _make_tool_call("CompleteTask", {"TaskId": "ghost", "Result": "n/a"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)
        assert "error" in result


# ---------------------------------------------------------------------------
# FailTask
# ---------------------------------------------------------------------------


class TestFailTask:
    def test_sets_failed_status_and_reason(self, middleware):
        created = task_service.create_task(title="will fail")
        call = _make_tool_call(
            "FailTask",
            {"TaskId": created["id"], "Reason": "API timeout"},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        task = result["task"]
        assert task["status"] == "failed"
        assert task["result"] == "API timeout"
        assert task["completed_at"] > 0

    def test_fail_nonexistent_returns_error(self, middleware):
        call = _make_tool_call("FailTask", {"TaskId": "ghost", "Reason": "n/a"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)
        assert "error" in result


# ---------------------------------------------------------------------------
# ListBoardTasks
# ---------------------------------------------------------------------------


class TestListBoardTasks:
    def test_returns_all_tasks(self, middleware):
        task_service.create_task(title="task A")
        task_service.create_task(title="task B")
        call = _make_tool_call("ListBoardTasks", {})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert len(result["tasks"]) >= 2
        assert result["total"] >= 2

    def test_filter_by_status(self, middleware):
        _t1 = task_service.create_task(title="pending task")
        t2 = task_service.create_task(title="running task")
        task_service.update_task(t2["id"], status="running")

        call = _make_tool_call("ListBoardTasks", {"Status": "running"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert all(t["status"] == "running" for t in result["tasks"])
        assert any(t["id"] == t2["id"] for t in result["tasks"])

    def test_filter_by_priority(self, middleware):
        task_service.create_task(title="low prio", priority="low")
        task_service.create_task(title="high prio", priority="high")

        call = _make_tool_call("ListBoardTasks", {"Priority": "high"})
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert all(t["priority"] == "high" for t in result["tasks"])


# ---------------------------------------------------------------------------
# UpdateTaskProgress
# ---------------------------------------------------------------------------


class TestUpdateTaskProgress:
    def test_updates_progress(self, middleware):
        created = task_service.create_task(title="progressing")
        call = _make_tool_call(
            "UpdateTaskProgress",
            {"TaskId": created["id"], "Progress": 50},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert result["task"]["progress"] == 50

    def test_appends_note_to_description(self, middleware):
        created = task_service.create_task(title="noted", description="original")
        call = _make_tool_call(
            "UpdateTaskProgress",
            {"TaskId": created["id"], "Progress": 75, "Note": "halfway done"},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)

        assert "halfway done" in result["task"]["description"]

    def test_progress_nonexistent_returns_error(self, middleware):
        call = _make_tool_call(
            "UpdateTaskProgress",
            {"TaskId": "ghost", "Progress": 50},
        )
        msg = middleware._handle_tool_call(call)
        result = _parse_result(msg)
        assert "error" in result


# ---------------------------------------------------------------------------
# wrap_tool_call passthrough
# ---------------------------------------------------------------------------


class TestWrapToolCall:
    def test_unknown_tool_passes_through(self, middleware):
        """Tools not owned by this middleware are forwarded to next handler."""
        from unittest.mock import MagicMock

        call = {"name": "SomeOtherTool", "id": "tc_99", "args": {}}
        request = MagicMock()
        request.tool_call = call
        sentinel = object()
        result = middleware.wrap_tool_call(request, lambda _req: sentinel)
        assert result is sentinel

    def test_owned_tool_is_intercepted(self, middleware):
        """Owned tools are handled internally, not forwarded."""
        from unittest.mock import MagicMock

        task_service.create_task(title="intercepted")
        call = {"name": "ListBoardTasks", "id": "tc_99", "args": {}}
        request = MagicMock()
        request.tool_call = call
        sentinel = object()
        result = middleware.wrap_tool_call(request, lambda _req: sentinel)
        # Should NOT be the sentinel — middleware handled it
        assert result is not sentinel
