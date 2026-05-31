"""agent_core — a clean, minimal, multi-agent agent runtime.

Extracted and refactored from Mycel's ``core/runtime``. The foundation layer
(state, tool registry, tool runner, middleware contract, ports) depends only on
``langchain_core.messages`` + ``pydantic`` + the stdlib — no DB, no web server,
no message bus. Concrete adapters (checkpoint stores, event emitters, executors)
are provided separately under ``agent_core.adapters`` and selected at assembly
time, so the core never imports the monolith.

See ARCHITECTURE.md for the module map and the extraction roadmap.
"""

from __future__ import annotations

from agent_core.agent import Agent
from agent_core.loop import QueryLoop, TerminalReason, TerminalState
from agent_core.policy import PermissionPolicy
from agent_core.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from agent_core.registry import (
    ToolEntry,
    ToolMode,
    ToolRegistry,
    make_tool_schema,
)
from agent_core.runner import ToolRunner
from agent_core.state import (
    AppState,
    BootstrapConfig,
    ToolUseContext,
)
from agent_core.tool_result import (
    ToolResultEnvelope,
    tool_error,
    tool_success,
)

__all__ = [
    "Agent",
    "AgentMiddleware",
    "AppState",
    "BootstrapConfig",
    "ModelRequest",
    "ModelResponse",
    "PermissionPolicy",
    "QueryLoop",
    "TerminalReason",
    "TerminalState",
    "ToolCallRequest",
    "ToolEntry",
    "ToolMode",
    "ToolRegistry",
    "ToolResultEnvelope",
    "ToolRunner",
    "ToolUseContext",
    "make_tool_schema",
    "tool_error",
    "tool_success",
]
