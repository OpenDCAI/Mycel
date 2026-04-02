"""Three-layer state models aligned with CC architecture.

Layer 1: BootstrapConfig — survives /clear, process-level constants
Layer 2: AppState — per-session mutable state (Zustand-style store)
Layer 3: ToolUseContext — per-turn, holds live closures to AppState
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


class BootstrapConfig(BaseModel):
    """Process-level configuration that survives /clear.

    Analogous to CC Bootstrap State (~85 fields). Contains workspace
    identity, model config, security flags, and API credentials.
    """

    workspace_root: Path
    original_cwd: Path | None = None
    project_root: Path | None = None
    cwd: Path | None = None
    model_name: str
    api_key: str | None = None

    # Security flags (fail-closed defaults)
    block_dangerous_commands: bool = True
    block_network_commands: bool = False
    enable_audit_log: bool = True
    enable_web_tools: bool = False

    # File access
    allowed_file_extensions: list[str] | None = None
    extra_allowed_paths: list[str] | None = None

    # Turn limits
    max_turns: int | None = None

    # Session identity
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_session_id: str | None = None

    # Session accumulators that survive turn-level resets
    total_cost_usd: float = 0.0
    total_tool_duration_ms: int = 0

    # Model settings
    model_provider: str | None = None
    base_url: str | None = None
    context_limit: int | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        self.workspace_root = Path(self.workspace_root)
        self.original_cwd = Path(self.original_cwd) if self.original_cwd is not None else self.workspace_root
        self.project_root = Path(self.project_root) if self.project_root is not None else self.workspace_root
        self.cwd = Path(self.cwd) if self.cwd is not None else self.project_root


class AppState(BaseModel):
    """Per-session mutable state. Analogous to CC AppState store.

    Implements a minimal Zustand-style store with getState/setState.
    Not reactive — no subscriptions needed for Python backend.
    """

    messages: list = Field(default_factory=list)
    turn_count: int = 0
    total_cost: float = 0.0
    compact_boundary_index: int = 0
    # Map of tool_name -> is_enabled (runtime overrides)
    tool_overrides: dict[str, bool] = Field(default_factory=dict)

    def get_state(self) -> "AppState":
        return self

    def set_state(self, updater: Callable[["AppState"], "AppState"]) -> "AppState":
        updated = updater(self)
        # Mutate in place (Python idiom — no immutable constraint needed here)
        for field_name in AppState.model_fields:
            setattr(self, field_name, getattr(updated, field_name))
        return self


class ToolUseContext(BaseModel):
    """Per-turn context bag. Analogous to CC ToolUseContext.

    Carries live closures to AppState so tools can read/mutate session state.
    Sub-agents receive a NO-OP set_app_state to prevent write-through.
    """

    bootstrap: BootstrapConfig
    get_app_state: Any = Field(exclude=True)  # Callable[[], AppState]
    set_app_state: Any = Field(exclude=True)  # Callable[[AppState], None] | NO-OP
    set_app_state_for_tasks: Any = Field(default=None, exclude=True)
    refresh_tools: Any = Field(default=None, exclude=True)  # Callable[[], Awaitable[None] | None]
    read_file_state: Any = Field(default_factory=dict, exclude=True)
    loaded_nested_memory_paths: Any = Field(default_factory=set, exclude=True)
    discovered_skill_names: Any = Field(default_factory=set, exclude=True)
    nested_memory_attachment_triggers: Any = Field(default_factory=set, exclude=True)
    messages: list = Field(default_factory=list)
    turn_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])

    model_config = ConfigDict(arbitrary_types_allowed=True)
