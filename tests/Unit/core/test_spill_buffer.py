"""Tests for core.spill_buffer: spill_if_needed() and SpillBufferMiddleware."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage

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


def _make_request(tool_name: str, tool_call_id: str = "call_abc123"):
    """Build a fake ToolCallRequest with a .tool_call dict."""
    return SimpleNamespace(tool_call={"name": tool_name, "id": tool_call_id})


# ===========================================================================
# spill_if_needed()
# ===========================================================================


class TestSpillIfNeeded:
    """Unit tests for the core spill function."""

    def test_small_output_not_triggered(self):
        """Content under threshold is returned unchanged."""
        fs = _make_fs_backend()
        content = "short output"
        result = spill_if_needed(
            content=content,
            threshold_bytes=1000,
            tool_call_id="call_1",
            fs_backend=fs,
            workspace_root="/workspace",
        )
        assert result == content
        fs.write_file.assert_not_called()

    def test_large_output_triggers_spill_and_preview(self):
        """Content exceeding threshold is spilled to disk; preview returned."""
        fs = _make_fs_backend()
        large = "A" * 60_000
        result = spill_if_needed(
            content=large,
            threshold_bytes=50_000,
            tool_call_id="call_big",
            fs_backend=fs,
            workspace_root="/workspace",
        )

        # Verify write_file was called with the correct spill path.
        expected_path = os.path.join("/workspace", ".leon", "tool-results", "call_big.txt")
        fs.write_file.assert_called_once_with(expected_path, large)

        # Result must mention the file path and include a preview.
        assert expected_path in result
        assert result.startswith("<persisted-output")
        assert f"{len(large.encode('utf-8'))} bytes" in result
        assert f"Preview (first {PREVIEW_BYTES} bytes)" in result
        # Preview text is the first PREVIEW_BYTES chars of the original.
        assert large[:PREVIEW_BYTES] in result

    def test_threshold_boundary_equal_no_trigger(self):
        """Content whose byte length exactly equals threshold is NOT spilled."""
        fs = _make_fs_backend()
        # 10 ASCII bytes
        content = "0123456789"
        assert len(content.encode("utf-8")) == 10

        result = spill_if_needed(
            content=content,
            threshold_bytes=10,
            tool_call_id="call_edge",
            fs_backend=fs,
            workspace_root="/w",
        )
        assert result == content
        fs.write_file.assert_not_called()

    def test_threshold_boundary_one_byte_over_triggers(self):
        """Content one byte over threshold IS spilled."""
        fs = _make_fs_backend()
        content = "0123456789X"  # 11 bytes
        result = spill_if_needed(
            content=content,
            threshold_bytes=10,
            tool_call_id="call_over",
            fs_backend=fs,
            workspace_root="/w",
        )
        assert result != content
        assert result.startswith("<persisted-output")
        fs.write_file.assert_called_once()

    def test_unicode_byte_counting(self):
        """Byte size is measured via UTF-8, not character count."""
        fs = _make_fs_backend()
        # Each CJK character is 3 bytes in UTF-8.
        content = "\u4e2d" * 10  # 10 chars, 30 bytes
        assert len(content) == 10
        assert len(content.encode("utf-8")) == 30

        # Threshold 25 < 30 bytes => should spill.
        result = spill_if_needed(
            content=content,
            threshold_bytes=25,
            tool_call_id="call_uni",
            fs_backend=fs,
            workspace_root="/w",
        )
        assert result.startswith("<persisted-output")
        assert "30 bytes" in result
        fs.write_file.assert_called_once()

    def test_unicode_under_threshold_no_spill(self):
        """Same chars, higher threshold => no spill."""
        fs = _make_fs_backend()
        content = "\u4e2d" * 10  # 30 bytes
        result = spill_if_needed(
            content=content,
            threshold_bytes=30,
            tool_call_id="call_uni2",
            fs_backend=fs,
            workspace_root="/w",
        )
        assert result == content
        fs.write_file.assert_not_called()

    def test_non_string_passthrough(self):
        """Non-string content is returned as-is without any check."""
        fs = _make_fs_backend()
        for value in [42, None, ["a", "b"], {"key": "val"}]:
            result = spill_if_needed(
                content=value,
                threshold_bytes=1,
                tool_call_id="call_ns",
                fs_backend=fs,
                workspace_root="/w",
            )
            assert result is value
        fs.write_file.assert_not_called()

    def test_write_failure_graceful_degradation(self):
        """If write_file raises, a warning is included but no crash."""
        fs = _make_fs_backend()
        fs.write_file.side_effect = OSError("disk full")

        large = "B" * 60_000
        result = spill_if_needed(
            content=large,
            threshold_bytes=50_000,
            tool_call_id="call_fail",
            fs_backend=fs,
            workspace_root="/workspace",
        )

        # Should still return a preview, not raise.
        assert result.startswith("<persisted-output")
        assert "Preview" in result
        # Must include the warning note about write failure.
        assert "Warning: failed to save full output to disk" in result
        assert "disk full" in result
        # Path should indicate write failure.
        assert "<write failed>" in result

    def test_preview_length_capped(self):
        """Preview contains at most PREVIEW_BYTES characters of the original."""
        fs = _make_fs_backend()
        # Create content much larger than PREVIEW_BYTES.
        large = "X" * (PREVIEW_BYTES * 5)
        result = spill_if_needed(
            content=large,
            threshold_bytes=100,
            tool_call_id="call_prev",
            fs_backend=fs,
            workspace_root="/w",
        )
        # The preview portion should be exactly PREVIEW_BYTES chars of "X".
        assert ("X" * PREVIEW_BYTES) in result
        # But not the full content.
        assert large not in result

    def test_large_output_uses_persisted_output_wrapper(self):
        """Large spilled output is wrapped as persisted-output, not plain prose."""
        fs = _make_fs_backend()
        large = "A" * 60_000

        result = spill_if_needed(
            content=large,
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

        result = spill_if_needed(
            content=content,
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

        expected_path = os.path.join(
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
        request = _make_request("run_command", "call_1")
        original_msg = ToolMessage(content="small", tool_call_id="call_1")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result is original_msg
        assert result.content == "small"

    def test_large_output_gets_spilled(self):
        """Tool output exceeding default threshold is replaced."""
        mw, fs = self._make_middleware(default_threshold=100)
        request = _make_request("run_command", "call_2")
        large_content = "Z" * 200
        original_msg = ToolMessage(content=large_content, tool_call_id="call_2")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result.content != large_content
        assert result.content.startswith("<persisted-output")
        assert result.tool_call_id == "call_2"
        fs.write_file.assert_called_once()

    def test_per_tool_threshold(self):
        """Per-tool threshold overrides the default."""
        mw, fs = self._make_middleware(
            thresholds={"grep_search": 100},
            default_threshold=1_000_000,
        )
        request = _make_request("grep_search", "call_grep")
        large_content = "G" * 200  # 200 bytes > 100 per-tool threshold
        original_msg = ToolMessage(content=large_content, tool_call_id="call_grep")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result.content.startswith("<persisted-output")
        fs.write_file.assert_called_once()

    def test_per_tool_threshold_not_triggered(self):
        """Per-tool threshold allows content under its limit."""
        mw, fs = self._make_middleware(
            thresholds={"grep_search": 500},
            default_threshold=10,  # very low default
        )
        request = _make_request("grep_search", "call_grep2")
        content = "G" * 200  # 200 bytes < 500 per-tool threshold
        original_msg = ToolMessage(content=content, tool_call_id="call_grep2")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result is original_msg
        fs.write_file.assert_not_called()

    def test_default_threshold_for_unlisted_tool(self):
        """Tools not in thresholds dict use the default threshold."""
        mw, fs = self._make_middleware(
            thresholds={"grep_search": 1_000_000},
            default_threshold=100,
        )
        request = _make_request("run_command", "call_cmd")
        content = "C" * 200  # 200 > default 100
        original_msg = ToolMessage(content=content, tool_call_id="call_cmd")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result.content.startswith("<persisted-output")

    def test_read_file_is_skipped(self):
        """read_file is in SKIP_TOOLS and must never be spilled."""
        assert "read_file" in SKIP_TOOLS

        mw, fs = self._make_middleware(default_threshold=10)
        request = _make_request("read_file", "call_rf")
        large_content = "R" * 1000
        original_msg = ToolMessage(content=large_content, tool_call_id="call_rf")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result is original_msg
        assert result.content == large_content
        fs.write_file.assert_not_called()

    def test_non_toolmessage_passthrough(self):
        """If handler returns something other than ToolMessage, pass through."""
        mw, _fs = self._make_middleware()
        request = _make_request("custom_tool", "call_custom")
        non_tool_result = "plain string result"
        handler = MagicMock(return_value=non_tool_result)

        result = mw.wrap_tool_call(request, handler)

        assert result == non_tool_result

    def test_wrap_model_call_passthrough(self):
        """wrap_model_call simply delegates to handler."""
        mw, _fs = self._make_middleware()
        sentinel = object()
        handler = MagicMock(return_value=sentinel)
        request = {"messages": []}

        result = mw.wrap_model_call(request, handler)

        handler.assert_called_once_with(request)
        assert result is sentinel

    def test_awrap_tool_call_delegates_to_maybe_spill(self):
        """awrap_tool_call uses the same _maybe_spill logic (sync mock)."""
        mw, fs = self._make_middleware(default_threshold=50)
        request = _make_request("run_command", "call_async")
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

        assert result.content.startswith("<persisted-output")
        assert result.tool_call_id == "call_async"
        fs.write_file.assert_called_once()

    def test_awrap_model_call_passthrough(self):
        """awrap_model_call simply awaits handler."""
        import asyncio

        mw, _fs = self._make_middleware()
        sentinel = object()

        async def async_handler(req):
            return sentinel

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(mw.awrap_model_call({"messages": []}, async_handler))
        finally:
            loop.close()
        assert result is sentinel

    def test_spill_path_uses_tool_call_id(self):
        """Verify the spill file name is derived from tool_call_id."""
        mw, fs = self._make_middleware(default_threshold=10)
        unique_id = "call_unique_xyz_789"
        request = _make_request("run_command", unique_id)
        content = "D" * 100
        original_msg = ToolMessage(content=content, tool_call_id=unique_id)
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        expected_path = os.path.join("/workspace", ".leon", "tool-results", f"{unique_id}.txt")
        fs.write_file.assert_called_once_with(expected_path, content)
        assert expected_path in result.content

    def test_whitespace_output_is_normalized(self):
        """Whitespace-only tool output becomes an explicit no-output marker."""
        mw, fs = self._make_middleware(default_threshold=10)
        request = _make_request("run_command", "call_empty")
        original_msg = ToolMessage(content="   \n\t", tool_call_id="call_empty", name="run_command")
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result.content == "(run_command completed with no output)"
        fs.write_file.assert_not_called()

    def test_spilled_tool_message_preserves_name_and_metadata(self):
        """Spill replacement must not discard tool name or additional metadata."""
        mw, _fs = self._make_middleware(default_threshold=10)
        request = _make_request("run_command", "call_meta")
        original_msg = ToolMessage(
            content="M" * 100,
            tool_call_id="call_meta",
            name="run_command",
            additional_kwargs={"tool_result_meta": {"kind": "success", "source": "local"}},
        )
        handler = MagicMock(return_value=original_msg)

        result = mw.wrap_tool_call(request, handler)

        assert result.name == "run_command"
        assert result.additional_kwargs == original_msg.additional_kwargs
