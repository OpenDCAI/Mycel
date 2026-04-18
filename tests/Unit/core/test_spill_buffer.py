"""Tests for core.spill_buffer: spill_if_needed() and SpillBufferMiddleware."""

import posixpath
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from core.runtime.middleware import ModelRequest
from core.runtime.middleware.spill_buffer.middleware import SKIP_TOOLS, SpillBufferMiddleware
from core.runtime.middleware.spill_buffer.spill import PREVIEW_BYTES, spill_if_needed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fs_backend():
    """Return a mock FileSystemBackend with write_file as a MagicMock."""
    backend = MagicMock()
    backend.write_file = MagicMock(return_value=None)
    return backend


@dataclass
class _ToolCallRequestHarness:
    tool_call: dict[str, Any]


@dataclass
class _ModelRequestHarness:
    messages: list[Any]


def _make_request(tool_name: str, tool_call_id: str = "call_abc123"):
    """Build a minimal request harness matching the middleware surface."""
    return cast(Any, _ToolCallRequestHarness(tool_call={"name": tool_name, "id": tool_call_id}))


def _make_model_request() -> ModelRequest:
    return cast(ModelRequest, _ModelRequestHarness(messages=[]))


def _require_text_content(message: ToolMessage) -> str:
    assert isinstance(message.content, str)
    return message.content


def _spill(content: Any, *, threshold_bytes: int, tool_call_id: str = "call", fs_backend: Any = None, workspace_root: str = "/w"):
    fs = fs_backend or _make_fs_backend()
    return spill_if_needed(
        content=content,
        threshold_bytes=threshold_bytes,
        tool_call_id=tool_call_id,
        fs_backend=fs,
        workspace_root=workspace_root,
    )


# ===========================================================================
# spill_if_needed()
# ===========================================================================


class TestSpillIfNeeded:
    """Unit tests for the core spill function."""

    @pytest.mark.parametrize(
        ("content", "threshold"),
        [
            ("short output", 1000),
            ("0123456789", 10),
            ("\u4e2d" * 10, 30),
        ],
    )
    def test_content_at_or_under_threshold_is_returned_unchanged(self, content: str, threshold: int):
        fs = _make_fs_backend()
        result = _spill(content, threshold_bytes=threshold, fs_backend=fs)

        assert result == content
        fs.write_file.assert_not_called()

    def test_large_output_triggers_spill_and_preview(self):
        """Content exceeding threshold is spilled to disk; preview returned."""
        fs = _make_fs_backend()
        large = "A" * 60_000
        result = _spill(
            large,
            threshold_bytes=50_000,
            tool_call_id="call_big",
            fs_backend=fs,
            workspace_root="/workspace",
        )

        # Verify write_file was called with the correct spill path.
        expected_path = posixpath.join("/workspace", ".leon", "tool-results", "call_big.txt")
        fs.write_file.assert_called_once_with(expected_path, large)

        # Result must mention the file path and include a preview.
        assert expected_path in result
        assert result.startswith("<persisted-output")
        assert f"{len(large.encode('utf-8'))} bytes" in result
        assert f"Preview (first {PREVIEW_BYTES} bytes)" in result
        # Preview text is the first PREVIEW_BYTES chars of the original.
        assert large[:PREVIEW_BYTES] in result

    @pytest.mark.parametrize(
        ("content", "threshold", "expected_bytes"),
        [
            ("0123456789X", 10, None),
            ("\u4e2d" * 10, 25, 30),
        ],
    )
    def test_content_over_threshold_triggers_spill(self, content: str, threshold: int, expected_bytes: int | None):
        fs = _make_fs_backend()
        result = _spill(content, threshold_bytes=threshold, fs_backend=fs)

        assert result != content
        assert result.startswith("<persisted-output")
        if expected_bytes is not None:
            assert f"{expected_bytes} bytes" in result
        fs.write_file.assert_called_once()

    def test_non_string_passthrough(self):
        """Non-string content is returned as-is without any check."""
        fs = _make_fs_backend()
        for value in [42, None, ["a", "b"], {"key": "val"}]:
            result = _spill(value, threshold_bytes=1, tool_call_id="call_ns", fs_backend=fs)
            assert result is value
        fs.write_file.assert_not_called()

    def test_preview_length_capped(self):
        """Preview contains at most PREVIEW_BYTES characters of the original."""
        fs = _make_fs_backend()
        # Create content much larger than PREVIEW_BYTES.
        large = "X" * (PREVIEW_BYTES * 5)
        result = _spill(large, threshold_bytes=100, tool_call_id="call_prev", fs_backend=fs)
        # The preview portion should be exactly PREVIEW_BYTES chars of "X".
        assert ("X" * PREVIEW_BYTES) in result
        # But not the full content.
        assert large not in result

    def test_large_output_uses_persisted_output_wrapper(self):
        """Large spilled output is wrapped as persisted-output, not plain prose."""
        fs = _make_fs_backend()
        large = "A" * 60_000

        result = _spill(
            large,
            threshold_bytes=50_000,
            tool_call_id="call_wrapped",
            fs_backend=fs,
            workspace_root="/workspace",
        )

        assert result.startswith("<persisted-output")
        assert "</persisted-output>" in result
        assert 'path="/workspace/.leon/tool-results/call_wrapped.txt"' in result
        assert f'bytes="{len(large.encode("utf-8"))}"' in result

    def test_image_block_content_bypasses_spill(self):
        """Image-containing blocks should bypass persistence logic."""
        fs = _make_fs_backend()
        content = [
            {"type": "text", "text": "caption"},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
        ]

        result = _spill(
            content,
            threshold_bytes=1,
            tool_call_id="call_image",
            fs_backend=fs,
            workspace_root="/workspace",
        )

        assert result is content
        fs.write_file.assert_not_called()

    def test_mcp_binary_blocks_are_saved_and_rewritten(self):
        fs = _make_fs_backend()
        mw = SpillBufferMiddleware(
            fs_backend=fs,
            workspace_root="/workspace",
            default_threshold=50_000,
        )
        request = _make_request("mcp__server__image_tool", "call_mcp")
        original_msg = ToolMessage(
            content=[
                {"type": "text", "text": "caption"},
                {"type": "image", "base64": "QUJD", "mime_type": "image/png"},
            ],
            tool_call_id="call_mcp",
            additional_kwargs={"tool_result_meta": {"source": "mcp"}},
        )

        result = mw._maybe_spill(request, original_msg)

        expected_path = posixpath.join(
            "/workspace",
            ".leon",
            "tool-results",
            "call_mcp-1.png.base64",
        )
        fs.write_file.assert_called_once_with(expected_path, "QUJD")
        assert isinstance(result.content, str)
        assert "caption" in result.content
        assert expected_path in result.content
        assert "QUJD" not in result.content


# ===========================================================================
# SpillBufferMiddleware
# ===========================================================================


class TestSpillBufferMiddleware:
    """Tests for the middleware that wraps tool calls."""

    def _make_middleware(self, thresholds=None, default_threshold=50_000):
        fs = _make_fs_backend()
        mw = SpillBufferMiddleware(
            fs_backend=fs,
            workspace_root="/workspace",
            thresholds=thresholds,
            default_threshold=default_threshold,
        )
        return mw, fs

    def test_small_output_passes_through(self):
        """Tool output under threshold is not modified."""
        mw, _fs = self._make_middleware()
        request = _make_request("Bash", "call_1")
        original_msg = ToolMessage(content="small", tool_call_id="call_1")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result is original_msg
        assert _require_text_content(result) == "small"

    def test_large_output_gets_spilled(self):
        """Tool output exceeding default threshold is replaced."""
        mw, fs = self._make_middleware(default_threshold=100)
        request = _make_request("Bash", "call_2")
        large_content = "Z" * 200
        original_msg = ToolMessage(content=large_content, tool_call_id="call_2")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        content = _require_text_content(result)
        assert content != large_content
        assert content.startswith("<persisted-output")
        assert result.tool_call_id == "call_2"
        fs.write_file.assert_called_once()

    def test_per_tool_threshold(self):
        """Per-tool threshold overrides the default."""
        mw, fs = self._make_middleware(
            thresholds={"Grep": 100},
            default_threshold=1_000_000,
        )
        request = _make_request("Grep", "call_grep")
        large_content = "G" * 200  # 200 bytes > 100 per-tool threshold
        original_msg = ToolMessage(content=large_content, tool_call_id="call_grep")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert _require_text_content(result).startswith("<persisted-output")
        fs.write_file.assert_called_once()

    def test_per_tool_threshold_not_triggered(self):
        """Per-tool threshold allows content under its limit."""
        mw, fs = self._make_middleware(
            thresholds={"Grep": 500},
            default_threshold=10,  # very low default
        )
        request = _make_request("Grep", "call_grep2")
        content = "G" * 200  # 200 bytes < 500 per-tool threshold
        original_msg = ToolMessage(content=content, tool_call_id="call_grep2")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result is original_msg
        fs.write_file.assert_not_called()

    def test_default_threshold_for_unlisted_tool(self):
        """Tools not in thresholds dict use the default threshold."""
        mw, fs = self._make_middleware(
            thresholds={"Grep": 1_000_000},
            default_threshold=100,
        )
        request = _make_request("Bash", "call_cmd")
        content = "C" * 200  # 200 > default 100
        original_msg = ToolMessage(content=content, tool_call_id="call_cmd")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert _require_text_content(result).startswith("<persisted-output")

    def test_read_tool_is_skipped(self):
        """Read is in SKIP_TOOLS and must never be spilled."""
        assert "Read" in SKIP_TOOLS

        mw, fs = self._make_middleware(default_threshold=10)
        request = _make_request("Read", "call_rf")
        large_content = "R" * 1000
        original_msg = ToolMessage(content=large_content, tool_call_id="call_rf")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result is original_msg
        assert _require_text_content(result) == large_content
        fs.write_file.assert_not_called()

    def test_non_toolmessage_passthrough(self):
        """If handler returns something other than ToolMessage, pass through."""
        mw, _fs = self._make_middleware()
        request = _make_request("custom_tool", "call_custom")
        non_tool_result = "plain string result"
        handler = MagicMock(return_value=non_tool_result)

        result = mw.wrap_tool_call(request, handler)

        assert result == non_tool_result

    def test_awrap_tool_call_delegates_to_maybe_spill(self):
        """awrap_tool_call uses the same _maybe_spill logic (sync mock)."""
        mw, fs = self._make_middleware(default_threshold=50)
        request = _make_request("Bash", "call_async")
        large_content = "A" * 100
        original_msg = ToolMessage(content=large_content, tool_call_id="call_async")

        # Create a mock coroutine-returning handler.
        import asyncio

        async def async_handler(req):
            return original_msg

        # Run the async method synchronously via a fresh event loop.
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(mw.awrap_tool_call(request, async_handler))
        finally:
            loop.close()

        assert _require_text_content(result).startswith("<persisted-output")
        assert result.tool_call_id == "call_async"
        fs.write_file.assert_called_once()

    def test_spill_path_uses_tool_call_id(self):
        """Verify the spill file name is derived from tool_call_id."""
        mw, fs = self._make_middleware(default_threshold=10)
        unique_id = "call_unique_xyz_789"
        request = _make_request("Bash", unique_id)
        content = "D" * 100
        original_msg = ToolMessage(content=content, tool_call_id=unique_id)
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        expected_path = posixpath.join("/workspace", ".leon", "tool-results", f"{unique_id}.txt")
        fs.write_file.assert_called_once_with(expected_path, content)
        assert expected_path in _require_text_content(result)

    def test_whitespace_output_is_normalized(self):
        """Whitespace-only tool output becomes an explicit no-output marker."""
        mw, fs = self._make_middleware(default_threshold=10)
        request = _make_request("Bash", "call_empty")
        original_msg = ToolMessage(content="   \n\t", tool_call_id="call_empty", name="Bash")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert _require_text_content(result) == "(Bash completed with no output)"
        fs.write_file.assert_not_called()

    def test_spilled_tool_message_preserves_name_and_metadata(self):
        """Spill replacement must not discard tool name or additional metadata."""
        mw, _fs = self._make_middleware(default_threshold=10)
        request = _make_request("Bash", "call_meta")
        original_msg = ToolMessage(
            content="M" * 100,
            tool_call_id="call_meta",
            name="Bash",
            additional_kwargs={"tool_result_meta": {"kind": "success", "source": "local"}},
        )
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result.name == "Bash"
        assert result.additional_kwargs == original_msg.additional_kwargs
