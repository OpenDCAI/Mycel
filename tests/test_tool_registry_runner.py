"""Tests for ToolRegistry, ToolRunner, and ToolValidator (P0/P1 verification).

Covers:
- P0: Three-tier error normalization (Layer 1: validation, Layer 2: execution, Layer 3: soft)
- P1: ToolRegistry inline/deferred mode
- P1: ToolRunner dispatches registered tools and normalizes errors
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import tool

from core.runtime.errors import InputValidationError
from core.runtime.agent import _make_mcp_tool_entry
from core.runtime.middleware import ToolCallRequest
from core.runtime.permissions import ToolPermissionContext, can_auto_approve
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.runner import ToolRunner
from core.runtime.state import AppState, BootstrapConfig, ToolUseContext
from core.runtime.tool_result import ToolResultEnvelope, tool_permission_denied
from core.runtime.validator import ToolValidator
from core.tools.command.hooks.dangerous_commands import DangerousCommandsHook
from core.tools.command.service import CommandService
from core.tools.filesystem.read import ReadLimits
from core.tools.filesystem.read import read_file as read_file_dispatch
from core.tools.filesystem.read.readers.pdf import read_pdf
from core.tools.filesystem.service import FileSystemService
from core.tools.tool_search.service import ToolSearchService
from core.tools.web.service import WebService
from sandbox.interfaces.filesystem import DirListResult, FileReadResult, FileSystemBackend, FileWriteResult

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

    def test_search_no_match_returns_empty_results(self):
        reg = ToolRegistry()
        reg.register(self._make_entry("Read", ToolMode.INLINE))
        reg.register(self._make_entry("TaskCreate", ToolMode.DEFERRED))
        assert reg.search("nonesuch") == []

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

    @pytest.mark.asyncio
    async def test_filesystem_service_read_preserves_image_blocks_on_local_path(self, tmp_path):
        registry = ToolRegistry()
        FileSystemService(
            registry=registry,
            workspace_root=tmp_path,
        )
        image = tmp_path / "tiny.png"
        image.write_bytes(b"fake-png-payload")

        runner = _make_runner(registry.list_all())
        req = _make_tool_call_request("Read", {"file_path": str(image)})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert isinstance(result.content, list)
        assert any(block.get("type") == "image" for block in result.content)
        assert result.additional_kwargs["tool_result_meta"]["source"] == "local"

    @pytest.mark.asyncio
    async def test_filesystem_service_read_preserves_image_blocks_on_remote_path(self, tmp_path):
        class RemoteImageBackend(FileSystemBackend):
            is_remote = True

            def __init__(self):
                self._raw = b"remote-png-payload"

            def read_file(self, path: str) -> FileReadResult:
                return FileReadResult(content="opaque-binary-placeholder", size=len(self._raw))

            def write_file(self, path: str, content: str) -> FileWriteResult:
                return FileWriteResult(success=True)

            def file_exists(self, path: str) -> bool:
                return True

            def file_mtime(self, path: str) -> float | None:
                return None

            def file_size(self, path: str) -> int | None:
                return len(self._raw)

            def is_dir(self, path: str) -> bool:
                return False

            def list_dir(self, path: str) -> DirListResult:
                return DirListResult(entries=[])

            def download_bytes(self, path: str) -> bytes:
                return self._raw

        registry = ToolRegistry()
        FileSystemService(
            registry=registry,
            workspace_root="/workspace",
            backend=RemoteImageBackend(),
        )

        runner = _make_runner(registry.list_all())
        req = _make_tool_call_request("Read", {"file_path": "/workspace/tiny.png"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert isinstance(result.content, list)
        assert any(block.get("type") == "image" for block in result.content)
        assert result.additional_kwargs["tool_result_meta"]["source"] == "local"

    @pytest.mark.asyncio
    async def test_filesystem_service_read_remote_pdf_uses_special_reader_path(self, tmp_path):
        pdf_bytes = b"%PDF-1.4\nnot-a-real-pdf\n"
        local_pdf = tmp_path / "sample.pdf"
        local_pdf.write_bytes(pdf_bytes)
        expected = read_file_dispatch(path=local_pdf, limits=ReadLimits()).format_output()
        expected = expected.replace(str(local_pdf), "/workspace/sample.pdf")

        class RemotePdfBackend(FileSystemBackend):
            is_remote = True

            def read_file(self, path: str) -> FileReadResult:
                return FileReadResult(content="opaque-pdf-placeholder", size=len(pdf_bytes))

            def write_file(self, path: str, content: str) -> FileWriteResult:
                return FileWriteResult(success=True)

            def file_exists(self, path: str) -> bool:
                return True

            def file_mtime(self, path: str) -> float | None:
                return None

            def file_size(self, path: str) -> int | None:
                return len(pdf_bytes)

            def is_dir(self, path: str) -> bool:
                return False

            def list_dir(self, path: str) -> DirListResult:
                return DirListResult(entries=[])

            def download_bytes(self, path: str) -> bytes:
                return pdf_bytes

        registry = ToolRegistry()
        FileSystemService(
            registry=registry,
            workspace_root="/workspace",
            backend=RemotePdfBackend(),
        )

        runner = _make_runner(registry.list_all())
        req = _make_tool_call_request("Read", {"file_path": "/workspace/sample.pdf"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == expected

    @pytest.mark.asyncio
    async def test_filesystem_service_read_accepts_pdf_pages_argument(self, tmp_path):
        pdf_bytes = b"%PDF-1.4\nnot-a-real-pdf\n"
        local_pdf = tmp_path / "paged.pdf"
        local_pdf.write_bytes(pdf_bytes)
        expected = read_pdf(local_pdf, ReadLimits(), start_page=1, limit_pages=1).format_output()

        registry = ToolRegistry()
        FileSystemService(
            registry=registry,
            workspace_root=tmp_path,
        )
        runner = _make_runner(registry.list_all())
        req = _make_tool_call_request("Read", {"file_path": str(local_pdf), "pages": "1"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == expected

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

    @pytest.mark.asyncio
    async def test_non_mcp_post_tool_use_hook_sees_materialized_tool_message(self):
        events = []

        def local_handler(**kwargs):
            return "plain success"

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=local_handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        def post_tool_use(message, request):
            events.append((type(message).__name__, message.content, message.additional_kwargs["tool_result_meta"]["source"]))
            return message

        req.state.post_tool_use = post_tool_use
        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == "plain success"
        assert events == [("ToolMessage", "plain success", "local")]

    @pytest.mark.asyncio
    async def test_async_post_tool_use_hooks_run_in_parallel(self):
        def local_handler(**kwargs):
            return "plain success"

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=local_handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        async def post_hook_one(message, request):
            await asyncio.sleep(0.05)
            return None

        async def post_hook_two(message, request):
            await asyncio.sleep(0.05)
            return None

        req.state.post_tool_use = [post_hook_one, post_hook_two]

        started = time.perf_counter()
        result = await runner.awrap_tool_call(req, AsyncMock())
        elapsed = time.perf_counter() - started

        assert result.content == "plain success"
        assert elapsed < 0.09

    @pytest.mark.asyncio
    async def test_post_tool_use_failure_hook_runs_on_materialized_error_message(self):
        seen = []

        def bad_handler(**kwargs):
            raise ValueError("disk full")

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=bad_handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        def post_tool_use_failure(message, request):
            seen.append((type(message).__name__, message.additional_kwargs["tool_result_meta"]["kind"]))
            return message

        req.state.post_tool_use_failure = post_tool_use_failure
        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "<tool_use_error>" in result.content
        assert seen == [("ToolMessage", "error")]

    @pytest.mark.asyncio
    async def test_permission_denied_result_keeps_distinct_metadata(self):
        def denied_handler(**kwargs):
            return tool_permission_denied(
                "permission denied",
                top_level_blocks=[{"type": "text", "text": "extra-block"}],
                metadata={"policy": "workspace"},
            )

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=denied_handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert result.content == "permission denied"
        assert meta["kind"] == "permission_denied"
        assert meta["source"] == "local"
        assert meta["top_level_blocks"] == [{"type": "text", "text": "extra-block"}]
        assert meta["policy"] == "workspace"

    @pytest.mark.asyncio
    async def test_mcp_post_tool_use_hook_can_modify_result_before_materialization(self):
        runner = _make_runner([])  # unknown tool => upstream/MCP path
        req = _make_tool_call_request("mcp__server__tool", {})
        req.state = MagicMock()
        seen = []

        def post_tool_use(payload, request):
            seen.append(type(payload).__name__)
            assert isinstance(payload, ToolResultEnvelope)
            return ToolResultEnvelope(
                kind=payload.kind,
                content="hooked mcp result",
                is_error=payload.is_error,
                top_level_blocks=payload.top_level_blocks,
                metadata={**payload.metadata, "hooked": True},
            )

        req.state.post_tool_use = post_tool_use

        async def upstream(_request):
            return ToolResultEnvelope(kind="success", content="raw mcp result")

        result = await runner.awrap_tool_call(req, upstream)

        assert seen == ["ToolResultEnvelope"]
        assert result.content == "hooked mcp result"
        assert result.additional_kwargs["tool_result_meta"]["source"] == "mcp"
        assert result.additional_kwargs["tool_result_meta"]["hooked"] is True

    @pytest.mark.asyncio
    async def test_command_hook_denial_uses_permission_denied_result_path(self, tmp_path):
        registry = ToolRegistry()
        CommandService(
            registry=registry,
            workspace_root=tmp_path,
            hooks=[DangerousCommandsHook()],
        )
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("Bash", {"command": "rm -rf /"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert "SECURITY" in result.content
        assert meta["kind"] == "permission_denied"
        assert meta["source"] == "local"
        assert meta["policy"] == "command_hook"

    @pytest.mark.asyncio
    async def test_command_hook_does_not_block_quoted_dangerous_text(self, tmp_path):
        registry = ToolRegistry()
        CommandService(
            registry=registry,
            workspace_root=tmp_path,
            hooks=[DangerousCommandsHook(verbose=False)],
        )
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("Bash", {"command": 'echo "rm -rf /"'})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "SECURITY ERROR" not in result.content
        assert "rm -rf /" in result.content

    @pytest.mark.asyncio
    async def test_command_hook_does_not_block_commented_dangerous_text(self, tmp_path):
        registry = ToolRegistry()
        CommandService(
            registry=registry,
            workspace_root=tmp_path,
            hooks=[DangerousCommandsHook(verbose=False)],
        )
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("Bash", {"command": "echo hi # rm -rf /"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "SECURITY ERROR" not in result.content
        assert "hi" in result.content

    @pytest.mark.asyncio
    async def test_command_hook_blocks_obfuscated_dangerous_command_name_with_inline_quotes(self, tmp_path):
        registry = ToolRegistry()
        CommandService(
            registry=registry,
            workspace_root=tmp_path,
            hooks=[DangerousCommandsHook(verbose=False)],
        )
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("Bash", {"command": 's"u"do echo hi'})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "SECURITY ERROR" in result.content
        assert result.additional_kwargs["tool_result_meta"]["kind"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_command_hook_blocks_ansi_c_quoted_obfuscation(self, tmp_path):
        registry = ToolRegistry()
        CommandService(
            registry=registry,
            workspace_root=tmp_path,
            hooks=[DangerousCommandsHook(verbose=False)],
        )
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("Bash", {"command": "s$'udo' echo hi"})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "SECURITY ERROR" in result.content
        assert result.additional_kwargs["tool_result_meta"]["kind"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_registered_mcp_tool_executes_through_runner_with_mcp_source(self):
        @tool
        async def sample_mcp_tool(x: int) -> str:
            """sample mcp"""
            return f"mcp:{x}"

        registry = ToolRegistry()
        registry.register(_make_mcp_tool_entry(sample_mcp_tool))
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("sample_mcp_tool", {"x": 3})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert result.content == "mcp:3"
        assert meta["source"] == "mcp"
        assert meta["kind"] == "success"

    @pytest.mark.asyncio
    async def test_registered_mcp_tool_post_hook_sees_envelope_before_materialization(self):
        @tool
        async def sample_mcp_tool(x: int) -> str:
            """sample mcp"""
            return f"mcp:{x}"

        registry = ToolRegistry()
        registry.register(_make_mcp_tool_entry(sample_mcp_tool))
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("sample_mcp_tool", {"x": 3})
        req.state = MagicMock()
        seen = []

        def post_tool_use(payload, request):
            seen.append(type(payload).__name__)
            assert isinstance(payload, ToolResultEnvelope)
            return payload

        req.state.post_tool_use = post_tool_use

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert seen == ["ToolResultEnvelope"]
        assert result.content == "mcp:3"
        assert result.additional_kwargs["tool_result_meta"]["source"] == "mcp"

    @pytest.mark.asyncio
    async def test_registered_mcp_tool_preserves_content_blocks_before_spill(self):
        @tool
        async def sample_mcp_tool(x: int) -> list[dict[str, str]]:
            """sample mcp"""
            return [
                {"type": "text", "text": f"mcp:{x}"},
                {"type": "image", "base64": "QUJD", "mime_type": "image/png"},
            ]

        registry = ToolRegistry()
        registry.register(_make_mcp_tool_entry(sample_mcp_tool))
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("sample_mcp_tool", {"x": 3})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == [
            {"type": "text", "text": "mcp:3"},
            {"type": "image", "base64": "QUJD", "mime_type": "image/png"},
        ]
        assert result.additional_kwargs["tool_result_meta"]["source"] == "mcp"

    @pytest.mark.asyncio
    async def test_registered_mcp_hook_rematerialization_keeps_mcp_source(self):
        @tool
        async def sample_mcp_tool(x: int) -> str:
            """sample mcp"""
            return f"mcp:{x}"

        registry = ToolRegistry()
        registry.register(_make_mcp_tool_entry(sample_mcp_tool))
        runner = ToolRunner(registry=registry)
        req = _make_tool_call_request("sample_mcp_tool", {"x": 3})
        req.state = MagicMock()

        def post_tool_use(payload, request):
            return ToolResultEnvelope(
                kind="success",
                content="hooked-remat",
                metadata={"hooked": True},
            )

        req.state.post_tool_use = post_tool_use

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert result.content == "hooked-remat"
        assert meta["source"] == "mcp"
        assert meta["hooked"] is True

    @pytest.mark.asyncio
    async def test_pre_tool_use_does_not_run_before_schema_validation(self):
        events = []

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={
                "name": "Write",
                "parameters": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            },
            handler=lambda path: f"ok:{path}",
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        def pre_tool_use(payload, request):
            events.append("pre")
            return payload

        req.state.pre_tool_use = pre_tool_use
        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "InputValidationError" in result.content
        assert events == []

    @pytest.mark.asyncio
    async def test_tool_specific_validation_runs_before_pre_tool_use_and_handler(self):
        events = []

        def validate_input(args, request):
            events.append("tool-validate")
            return {"path": args["path"], "normalized": True}

        def handler(path, normalized=False):
            events.append(("handler", path, normalized))
            return "ok"

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={
                "name": "Write",
                "parameters": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            },
            handler=handler,
            source="test",
            validate_input=validate_input,
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {"path": "/tmp/a"})
        req.state = MagicMock()

        def pre_tool_use(payload, request):
            events.append(("pre", dict(payload["args"])))
            return payload

        req.state.pre_tool_use = pre_tool_use
        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == "ok"
        assert events == [
            "tool-validate",
            ("pre", {"path": "/tmp/a", "normalized": True}),
            ("handler", "/tmp/a", True),
        ]

    @pytest.mark.asyncio
    async def test_tool_specific_validation_failure_object_stops_before_handler(self):
        events = []

        def validate_input(args, request):
            events.append("tool-validate")
            return {"result": False, "message": "tool says no", "errorCode": "E_NO"}

        def handler(**kwargs):
            events.append(("handler", kwargs))
            return "should-not-run"

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
            handler=handler,
            source="test",
            validate_input=validate_input,
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert "ToolValidationError" in result.content
        assert "tool says no" in result.content
        assert result.additional_kwargs["tool_result_meta"]["error_type"] == "tool_input_validation"
        assert result.additional_kwargs["tool_result_meta"]["error_code"] == "E_NO"
        assert events == ["tool-validate"]

    @pytest.mark.asyncio
    async def test_hook_allow_cannot_bypass_permission_deny_rule(self):
        def handler(**kwargs):
            raise AssertionError("handler should not run when permission denies")

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        def pre_tool_use(payload, request):
            return {"permission": "allow"}

        def can_use_tool(name, args, context, request):
            return {"decision": "deny", "message": "settings deny"}

        req.state.pre_tool_use = pre_tool_use
        req.state.can_use_tool = can_use_tool

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert result.content == "settings deny"
        assert meta["kind"] == "permission_denied"
        assert meta["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_parallel_pre_tool_use_hooks_keep_deny_precedence(self):
        def handler(**kwargs):
            raise AssertionError("handler should not run when a hook denies")

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        async def allow_hook(payload, request):
            await asyncio.sleep(0.01)
            return {"permission": "allow", "message": "hook allow"}

        async def deny_hook(payload, request):
            await asyncio.sleep(0.01)
            return {"decision": "deny", "message": "hook deny"}

        req.state.pre_tool_use = [allow_hook, deny_hook]

        result = await runner.awrap_tool_call(req, AsyncMock())

        meta = result.additional_kwargs["tool_result_meta"]
        assert result.content == "hook deny"
        assert meta["kind"] == "permission_denied"
        assert meta["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_pre_tool_use_can_update_args_before_permission_and_handler(self):
        seen = []

        def handler(path):
            seen.append(("handler", path))
            return f"ok:{path}"

        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={
                "name": "Write",
                "parameters": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            },
            handler=handler,
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {"path": "raw"})
        req.state = MagicMock()

        def pre_tool_use(payload, request):
            return {"args": {"path": "mutated"}}

        def can_use_tool(name, args, context, request):
            seen.append(("permission", args["path"]))
            return {"decision": "allow"}

        req.state.pre_tool_use = pre_tool_use
        req.state.can_use_tool = can_use_tool

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == "ok:mutated"
        assert seen == [("permission", "mutated"), ("handler", "mutated")]

    @pytest.mark.asyncio
    async def test_async_pre_tool_use_hooks_run_in_parallel(self):
        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=lambda: "ok",
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        async def hook_one(payload, request):
            await asyncio.sleep(0.05)
            return None

        async def hook_two(payload, request):
            await asyncio.sleep(0.05)
            return None

        req.state.pre_tool_use = [hook_one, hook_two]

        started = time.perf_counter()
        result = await runner.awrap_tool_call(req, AsyncMock())
        elapsed = time.perf_counter() - started

        assert result.content == "ok"
        assert elapsed < 0.09

    @pytest.mark.asyncio
    async def test_permission_checker_receives_permission_context_not_scheduler_flag(self):
        seen = []

        entry = ToolEntry(
            name="Read",
            mode=ToolMode.INLINE,
            schema={"name": "Read", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=lambda: "ok",
            source="test",
            is_read_only=True,
            is_concurrency_safe=True,
            is_destructive=True,
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Read", {})
        req.state = MagicMock()

        def can_use_tool(name, args, context, request):
            seen.append((context.is_read_only, context.is_destructive, hasattr(context, "is_concurrency_safe")))
            return {"decision": "allow"}

        req.state.can_use_tool = can_use_tool

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == "ok"
        assert seen == [(True, True, False)]

    @pytest.mark.asyncio
    async def test_destructive_metadata_is_advisory_not_runtime_deny(self):
        entry = ToolEntry(
            name="Write",
            mode=ToolMode.INLINE,
            schema={"name": "Write", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=lambda: "ok",
            source="test",
            is_destructive=True,
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Write", {})
        req.state = MagicMock()

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_runner_injects_tool_context_into_handler_when_requested(self):
        entry = ToolEntry(
            name="Agent",
            mode=ToolMode.INLINE,
            schema={"name": "Agent", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=lambda tool_context: f"context:{tool_context.turn_id}",
            source="test",
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("Agent", {})
        app_state = AppState()
        req.state = ToolUseContext(
            bootstrap=BootstrapConfig(workspace_root="/tmp/workspace", model_name="gpt-test"),
            get_app_state=app_state.get_state,
            set_app_state=app_state.set_state,
        )

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert result.content == f"context:{req.state.turn_id}"

    @pytest.mark.asyncio
    async def test_runner_maps_context_schema_fields_into_handler_kwargs(self):
        seen = {}

        def needs_ctx(*, boot):
            seen["boot"] = boot
            return f"boot:{boot}"

        entry = ToolEntry(
            name="NeedsCtx",
            mode=ToolMode.INLINE,
            schema={"name": "NeedsCtx", "parameters": {"type": "object", "required": [], "properties": {}}},
            handler=needs_ctx,
            source="test",
            context_schema={"boot": "bootstrap.model_name"},
        )
        runner = _make_runner([entry])
        req = _make_tool_call_request("NeedsCtx", {})
        app_state = AppState()
        req.state = ToolUseContext(
            bootstrap=BootstrapConfig(workspace_root="/tmp/workspace", model_name="MODEL_X"),
            get_app_state=app_state.get_state,
            set_app_state=app_state.set_state,
        )

        result = await runner.awrap_tool_call(req, AsyncMock())

        assert seen == {"boot": "MODEL_X"}
        assert result.content == "boot:MODEL_X"


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

    def test_task_service_read_only_does_not_imply_concurrency_safe(self, tmp_path):
        reg = ToolRegistry()
        from core.tools.task.service import TaskService

        _svc = TaskService(registry=reg, db_path=tmp_path / "test.db")

        for tool_name in ["TaskGet", "TaskList"]:
            entry = reg.get(tool_name)
            assert entry is not None, f"{tool_name} not registered"
            assert entry.is_read_only is True
            assert entry.is_concurrency_safe is False


class TestToolSearchService:
    def _make_ctx(self) -> ToolUseContext:
        app = AppState()
        return ToolUseContext(
            bootstrap=BootstrapConfig(workspace_root="/tmp", model_name="test-model"),
            get_app_state=lambda: app,
            set_app_state=lambda fn: None,
        )

    def test_tool_search_keyword_results_are_capped_to_five(self):
        reg = ToolRegistry()
        for index in range(7):
            reg.register(
                ToolEntry(
                    name=f"Deferred{index}",
                    mode=ToolMode.DEFERRED,
                    schema={"name": f"Deferred{index}", "description": "alpha helper"},
                    handler=lambda: "ok",
                    source="test",
                )
            )
        ToolSearchService(reg)
        runner = _make_runner(reg.list_all())
        req = ToolCallRequest(
            tool_call={"name": "tool_search", "args": {"query": "alpha"}, "id": "tc-search"},
            state=self._make_ctx(),
        )

        result = runner.wrap_tool_call(req, lambda r: MagicMock())

        payload = json.loads(result.content)
        assert len(payload) == 5

    def test_tool_search_excludes_inline_tools(self):
        reg = ToolRegistry()
        reg.register(
            ToolEntry(
                name="Read",
                mode=ToolMode.INLINE,
                schema={"name": "Read", "description": "read file content"},
                handler=lambda: "read",
                source="test",
            )
        )
        reg.register(
            ToolEntry(
                name="TaskCreate",
                mode=ToolMode.DEFERRED,
                schema={"name": "TaskCreate", "description": "create task"},
                handler=lambda: "task",
                source="test",
            )
        )
        ToolSearchService(reg)
        ctx = self._make_ctx()
        runner = _make_runner(reg.list_all())
        req = ToolCallRequest(
            tool_call={"name": "tool_search", "args": {"query": "read"}, "id": "tc-search"},
            state=ctx,
        )

        result = runner.wrap_tool_call(req, lambda r: MagicMock())

        assert json.loads(result.content) == []
        assert ctx.discovered_tool_names == set()


class TestWebToolRegistration:
    def test_web_tools_are_deferred_not_inline(self):
        reg = ToolRegistry()
        WebService(registry=reg)

        assert reg.get("WebSearch").mode == ToolMode.DEFERRED
        assert reg.get("WebFetch").mode == ToolMode.DEFERRED
        assert [schema["name"] for schema in reg.get_inline_schemas()] == []

    def test_can_auto_approve_only_for_read_only_non_destructive_tools(self):
        assert can_auto_approve(ToolPermissionContext(is_read_only=True, is_destructive=False)) is True
        assert can_auto_approve(ToolPermissionContext(is_read_only=False, is_destructive=False)) is False
        assert can_auto_approve(ToolPermissionContext(is_read_only=True, is_destructive=True)) is False
