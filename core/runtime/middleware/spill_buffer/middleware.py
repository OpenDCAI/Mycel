"""SpillBuffer middleware - intercepts oversized tool outputs."""

from __future__ import annotations

import json
import mimetypes
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from core.runtime.middleware import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest

from core.tools.filesystem.backend import FileSystemBackend

from .spill import spill_if_needed

# Tools whose output must never be silently replaced.
SKIP_TOOLS: set[str] = {"read_file"}


class SpillBufferMiddleware(AgentMiddleware):
    """Catches tool outputs that exceed a byte threshold.

    Oversized content is written to disk under
    ``{workspace_root}/.leon/tool-results/{tool_call_id}.txt``
    and replaced with a preview + file path so the model can
    use ``read_file`` to inspect specific sections.
    """

    def __init__(
        self,
        fs_backend: FileSystemBackend | None = None,
        workspace_root: str | Path = "",
        thresholds: dict[str, int] | None = None,
        default_threshold: int = 50_000,
    ) -> None:
        if fs_backend is None:
            from core.tools.filesystem.local_backend import LocalBackend

            fs_backend = LocalBackend()
        self.fs_backend = fs_backend
        self.workspace_root = str(workspace_root)
        self.thresholds: dict[str, int] = thresholds or {}
        self.default_threshold = default_threshold

    def _rewrite_mcp_blocks(self, content: Any, *, tool_call_id: str) -> Any:
        if not isinstance(content, list):
            return content

        lines: list[str] = []
        saw_mcp_blocks = False

        for index, block in enumerate(content):
            if not isinstance(block, dict):
                return content

            kind = block.get("type")
            if kind == "text":
                lines.append(str(block.get("text", "")))
                continue

            saw_mcp_blocks = True
            mime_type = str(block.get("mime_type") or "application/octet-stream")
            guessed_ext = mimetypes.guess_extension(mime_type.split(";", 1)[0].strip()) or ".bin"

            if isinstance(block.get("base64"), str):
                payload_path = os.path.join(
                    self.workspace_root,
                    ".leon",
                    "tool-results",
                    f"{tool_call_id}-{index}{guessed_ext}.base64",
                )
                # @@@mcp-binary-handoff - api-04 keeps Leon's sandbox/file
                # abstraction by persisting encoded payloads through fs_backend
                # instead of writing host-local bytes behind the sandbox's back.
                write_result = self.fs_backend.write_file(payload_path, block["base64"])
                if hasattr(write_result, "success") and not write_result.success:
                    raise RuntimeError(write_result.error or f"failed to persist MCP payload to {payload_path}")
                lines.append(
                    f"MCP binary content ({mime_type}) saved to {payload_path} as base64 payload."
                )
                continue

            if isinstance(block.get("url"), str):
                lines.append(f"MCP {kind} content available at {block['url']} ({mime_type})")
                continue

            lines.append(json.dumps(block, ensure_ascii=False, default=str))

        if not saw_mcp_blocks:
            text_only = "\n".join(line for line in lines if line)
            return text_only if text_only else content
        return "\n".join(line for line in lines if line)

    # -- model call: pass-through ------------------------------------------

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(request)

    # -- tool call: spill if needed ----------------------------------------

    def _maybe_spill(self, request: ToolCallRequest, result: ToolMessage) -> ToolMessage:
        """Shared logic for sync/async tool-call wrappers."""
        tool_name = request.tool_call.get("name", "")
        if tool_name in SKIP_TOOLS:
            return result

        source = result.additional_kwargs.get("tool_result_meta", {}).get("source")
        normalized_content = result.content
        if source == "mcp":
            normalized_content = self._rewrite_mcp_blocks(
                normalized_content,
                tool_call_id=request.tool_call.get("id", "unknown"),
            )
            if normalized_content is not result.content:
                result = result.model_copy(update={"content": normalized_content})

        if isinstance(result.content, str) and not result.content.strip():
            return result.model_copy(update={"content": f"({tool_name} completed with no output)"})

        threshold = self.thresholds.get(tool_name, self.default_threshold)
        tool_call_id = request.tool_call.get("id", "unknown")

        spilled = spill_if_needed(
            content=result.content,
            threshold_bytes=threshold,
            tool_call_id=tool_call_id,
            fs_backend=self.fs_backend,
            workspace_root=self.workspace_root,
        )

        if spilled is not result.content:
            # @@@spill-message-preservation - replacing content must not discard
            # metadata/name/id; te-03 is about persisted handoff, not rebuilding
            # a thinner ToolMessage shell.
            return result.model_copy(update={"content": spilled})
        return result

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        result = handler(request)
        if isinstance(result, ToolMessage):
            return self._maybe_spill(request, result)
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        result = await handler(request)
        if isinstance(result, ToolMessage):
            return self._maybe_spill(request, result)
        return result
