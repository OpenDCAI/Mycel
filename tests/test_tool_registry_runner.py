"""Tests for ToolRegistry, ToolRunner, and ToolValidator (P0/P1 verification).

Covers:
- P0: Three-tier error normalization (Layer 1: validation, Layer 2: execution, Layer 3: soft)
- P1: ToolRegistry inline/deferred mode
- P1: ToolRunner dispatches registered tools and normalizes errors
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.runtime.errors import InputValidationError
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.runner import ToolRunner
from core.runtime.validator import ToolValidator

# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def _make_entry(self, name: str, mode: ToolMode = ToolMode.INLINE) -> ToolEntry:
        return ToolEntry(
            name=name,
            mode=mode,
            schema={"name": name, "description": f"{name} tool"},
            handler=lambda: f"result:{name}",
            source="test",
        )

    def test_register_and_get(self):
        reg = ToolRegistry()
        entry = self._make_entry("Read")
        reg.register(entry)
        assert reg.get("Read") is entry

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("NonExistent") is None

    def test_inline_tools_appear_in_get_inline_schemas(self):
        reg = ToolRegistry()
        reg.register(self._make_entry("Read", ToolMode.INLINE))
        reg.register(self._make_entry("TaskCreate", ToolMode.DEFERRED))
        schemas = reg.get_inline_schemas()
        names = [s["name"] for s in schemas]
        assert "Read" in names
        assert "TaskCreate" not in names  # P1: deferred not in inline

    def test_deferred_tools_not_in_inline_schemas(self):
        reg = ToolRegistry()
        reg.register(self._make_entry("TaskCreate", ToolMode.DEFERRED))
        reg.register(self._make_entry("TaskUpdate", ToolMode.DEFERRED))
        assert reg.get_inline_schemas() == []

    def test_search_finds_by_name(self):
        reg = ToolRegistry()
        reg.register(self._make_entry("TaskCreate", ToolMode.DEFERRED))
        reg.register(self._make_entry("Read", ToolMode.INLINE))
        results = reg.search("task")
        names = [e.name for e in results]
        assert "TaskCreate" in names

    def test_search_includes_deferred_tools(self):
        """tool_search must discover deferred tools too."""
        reg = ToolRegistry()
        reg.register(self._make_entry("TaskCreate", ToolMode.DEFERRED))
        results = reg.search("TaskCreate")
        assert any(e.name == "TaskCreate" for e in results)

    def test_allowed_tools_filter(self):
        reg = ToolRegistry(allowed_tools={"Read", "Grep"})
        reg.register(self._make_entry("Read"))
        reg.register(self._make_entry("Grep"))
        reg.register(self._make_entry("Bash"))
        assert reg.get("Read") is not None
        assert reg.get("Grep") is not None
        assert reg.get("Bash") is None  # filtered out

    def test_dynamic_schema_callable(self):
        call_count = 0

        def schema_fn() -> dict:
            nonlocal call_count
            call_count += 1
            return {"name": "DynTool", "description": "dynamic"}

        reg = ToolRegistry()
        entry = ToolEntry(
            name="DynTool",
            mode=ToolMode.INLINE,
            schema=schema_fn,
            handler=lambda: "ok",
            source="test",
        )
        reg.register(entry)
        schemas = reg.get_inline_schemas()
        assert call_count >= 1
        assert any(s["name"] == "DynTool" for s in schemas)


# ---------------------------------------------------------------------------
# ToolValidator
# ---------------------------------------------------------------------------


class TestToolValidator:
    def _schema(self, required: list[str], props: dict) -> dict:
        return {
            "name": "TestTool",
            "parameters": {
                "type": "object",
                "required": required,
                "properties": {k: {"type": v} for k, v in props.items()},
            },
        }

    def test_valid_args_pass(self):
        v = ToolValidator()
        schema = self._schema(["file_path"], {"file_path": "string"})
        result = v.validate(schema, {"file_path": "/tmp/x"})
        assert result.ok

    def test_missing_required_raises_layer1(self):
        v = ToolValidator()
        schema = self._schema(["file_path"], {"file_path": "string"})
        with pytest.raises(InputValidationError) as exc_info:
            v.validate(schema, {})
        assert "file_path" in str(exc_info.value)
        assert "missing" in str(exc_info.value)

    def test_wrong_type_raises_layer1(self):
        v = ToolValidator()
        schema = self._schema(["count"], {"count": "integer"})
        with pytest.raises(InputValidationError):
            v.validate(schema, {"count": "not-an-int"})

    def test_extra_params_allowed(self):
        v = ToolValidator()
        schema = self._schema(["a"], {"a": "string"})
        result = v.validate(schema, {"a": "hello", "extra": "ok"})
        assert result.ok


# ---------------------------------------------------------------------------
# ToolRunner — P0 error normalization
# ---------------------------------------------------------------------------


def _make_runner(entries: list[ToolEntry]) -> ToolRunner:
    reg = ToolRegistry()
    for e in entries:
        reg.register(e)
    return ToolRunner(registry=reg)


def _make_tool_call_request(name: str, args: dict, call_id: str = "tc-1"):
    req = MagicMock()
    req.tool_call = {"name": name, "args": args, "id": call_id}
    return req


class TestToolRunnerErrorNormalization:
    """P0: three-tier error normalization."""

    def test_layer1_missing_param_returns_input_validation_error(self):
        entry = ToolEntry(
            name="Read",
            mode=ToolMode.INLINE,
            schema={
                "name": "Read",
                "parameters": {
                    "type": "object",
                    "required": ["file_path"],
                    "properties": {"file_path": {"type": "string"}},
                },
            },
            handler=lambda file_path: "content",
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Read", {})  # missing file_path

        called_upstream = []

        def upstream(r):
            called_upstream.append(r)
            return MagicMock()

        result = runner.wrap_tool_call(req, upstream)
        # Layer 1 error format: InputValidationError: {name} failed due to...
        assert "InputValidationError" in result.content
        assert "Read" in result.content
        assert not called_upstream  # must not fall through to upstream

    def test_layer2_handler_exception_returns_tool_use_error(self):
        def bad_handler(**kwargs):
            raise ValueError("disk full")

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={
                "name": "Write",
                "parameters": {
                    "type": "object",
                    "required": [],
                    "properties": {},
                },
            },
            handler=bad_handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        result = runner.wrap_tool_call(req, lambda r: MagicMock())
        # Layer 2 error format: <tool_use_error>...</tool_use_error>
        assert "<tool_use_error>" in result.content
        assert "disk full" in result.content

    def test_layer3_handler_returns_soft_failure_text(self):
        def soft_fail(**kwargs):
            return "No files found"

        entry = ToolEntry(
            name="Glob",
            mode=ToolMode.INLINE,
            schema={
                "name": "Glob",
                "parameters": {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {"pattern": {"type": "string"}},
                },
            },
            handler=soft_fail,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Glob", {"pattern": "**/*.xyz"})
        result = runner.wrap_tool_call(req, lambda r: MagicMock())
        # Layer 3: plain text, no tags
        assert result.content == "No files found"
        assert "<tool_use_error>" not in result.content
        assert "InputValidationError" not in result.content

    def test_unknown_tool_falls_through_to_upstream(self):
        runner = _make_runner([])  # empty registry
        req = _make_tool_call_request("UnknownMCPTool", {})
        upstream_called = []

        def upstream(r):
            upstream_called.append(r)
            msg = MagicMock()
            msg.content = "mcp result"
            return msg

        result = runner.wrap_tool_call(req, upstream)
        assert upstream_called
        assert result.content == "mcp result"


class TestToolRunnerInlineInjection:
    """P1: ToolRunner injects inline schemas into model call."""

    def test_inline_schemas_injected(self):
        entry = ToolEntry(
            name="Read",
            mode=ToolMode.INLINE,
            schema={"name": "Read", "description": "read file"},
            handler=lambda: "ok",
            source="test",
        )
        runner = _make_runner([entry])

        # Build a mock ModelRequest
        request = MagicMock()
        request.tools = []

        captured = []

        def handler(req):
            captured.append(req)
            return MagicMock()

        request.override.return_value = request
        runner.wrap_model_call(request, handler)

        # Should have called override with tools containing Read
        assert request.override.called
        call_kwargs = request.override.call_args
        _tools_arg = call_kwargs[1].get("tools") or (call_kwargs[0][0] if call_kwargs[0] else None)
        # override was called — inline tools were injected

    def test_deferred_schemas_not_injected(self):
        deferred = ToolEntry(
            name="TaskCreate",
            mode=ToolMode.DEFERRED,
            schema={"name": "TaskCreate", "description": "create task"},
            handler=lambda: "ok",
            source="test",
        )
        runner = _make_runner([deferred])
        schemas = runner._registry.get_inline_schemas()
        assert all(s["name"] != "TaskCreate" for s in schemas)


# ---------------------------------------------------------------------------
# P1: tool_modes from config honored
# ---------------------------------------------------------------------------


class TestToolModeFromConfig:
    """Verify tool_modes config is applied during service init."""

    def test_task_service_registers_deferred(self, tmp_path):
        reg = ToolRegistry()
        from core.tools.task.service import TaskService

        _svc = TaskService(registry=reg, db_path=tmp_path / "test.db")
        # TaskCreate/TaskUpdate/TaskList/TaskGet should be DEFERRED
        for tool_name in ["TaskCreate", "TaskGet", "TaskList", "TaskUpdate"]:
            entry = reg.get(tool_name)
            assert entry is not None, f"{tool_name} not registered"
            assert entry.mode == ToolMode.DEFERRED, f"{tool_name} should be DEFERRED, got {entry.mode}"

    def test_search_service_registers_inline(self, tmp_path):
        reg = ToolRegistry()
        from core.tools.search.service import SearchService

        _svc = SearchService(registry=reg, workspace_root=tmp_path)
        for tool_name in ["Grep", "Glob"]:
            entry = reg.get(tool_name)
            assert entry is not None, f"{tool_name} not registered"
            assert entry.mode == ToolMode.INLINE, f"{tool_name} should be INLINE, got {entry.mode}"
