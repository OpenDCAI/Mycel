"""Three-layer state models aligned with CC architecture.

Layer 1: BootstrapConfig — survives /clear, process-level constants
Layer 2: AppState — per-session mutable state (Zustand-style store)
Layer 3: ToolUseContext — per-turn, holds live closures to AppState
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .abort import AbortController
from .permissions import ToolPermissionContext


class ToolPermissionState(BaseModel):
    # @@@camelcase-permission-surface - persisted/thread API surface already uses camelCase keys.
    alwaysAllowRules: dict[str, list[str]] = Field(default_factory=dict)  # noqa: N815
    alwaysDenyRules: dict[str, list[str]] = Field(default_factory=dict)  # noqa: N815
    alwaysAskRules: dict[str, list[str]] = Field(default_factory=dict)  # noqa: N815
    allowManagedPermissionRulesOnly: bool = False  # noqa: N815


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
    sandbox_type: str = "local"
    permission_resolver_scope: str = "none"

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
    tool_permission_context: ToolPermissionState = Field(default_factory=ToolPermissionState)
    pending_permission_requests: dict[str, dict[str, Any]] = Field(default_factory=dict)
    resolved_permission_requests: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # @@@session-hooks-not-watchers - keep this surface local and lifecycle-scoped.
    # File watching remains a later outer-layer concern so Leon keeps the
    # filesystem + terminal core decoupled.
    session_hooks: dict[str, list[Any]] = Field(default_factory=dict)

    def get_state(self) -> AppState:
        return self

    def set_state(self, updater: Callable[[AppState], AppState]) -> AppState:
        updated = updater(self)
        # Mutate in place (Python idiom — no immutable constraint needed here)
        for field_name in AppState.model_fields:
            setattr(self, field_name, getattr(updated, field_name))
        return self

    def add_session_hook(self, event: str, hook: Any) -> None:
        hooks = list(self.session_hooks.get(event, []))
        hooks.append(hook)
        self.session_hooks[event] = hooks

    def remove_session_hook(self, event: str, hook: Any) -> None:
        hooks = [candidate for candidate in self.session_hooks.get(event, []) if candidate != hook]
        if hooks:
            self.session_hooks[event] = hooks
        else:
            self.session_hooks.pop(event, None)

    def get_session_hooks(self, event: str) -> list[Any]:
        return list(self.session_hooks.get(event, []))


AppStateUpdater = Callable[[AppState], AppState]
AppStateGetter = Callable[[], AppState]
AppStateSetter = Callable[[AppStateUpdater], AppState | None]
RefreshToolsHook = Callable[[], Awaitable[None] | None]
PermissionDecision = dict[str, Any] | None
PermissionChecker = Callable[
    [str, dict[str, Any], ToolPermissionContext, object],
    PermissionDecision | Awaitable[PermissionDecision],
]
PermissionRequester = Callable[
    [str, dict[str, Any], ToolPermissionContext, object, str | None],
    str | dict[str, Any] | None | Awaitable[str | dict[str, Any] | None],
]
PermissionResolutionConsumer = Callable[
    [str, dict[str, Any], ToolPermissionContext, object],
    PermissionDecision | Awaitable[PermissionDecision],
]


class ToolUseContext(BaseModel):
    """Per-turn context bag. Analogous to CC ToolUseContext.

    Carries live closures to AppState so tools can read/mutate session state.
    Sub-agents receive a NO-OP set_app_state to prevent write-through.
    """

    bootstrap: BootstrapConfig
    get_app_state: AppStateGetter = Field(exclude=True)
    set_app_state: AppStateSetter = Field(exclude=True)
    set_app_state_for_tasks: AppStateSetter | None = Field(default=None, exclude=True)
    refresh_tools: RefreshToolsHook | None = Field(default=None, exclude=True)
    can_use_tool: PermissionChecker | None = Field(default=None, exclude=True)
    request_permission: PermissionRequester | None = Field(default=None, exclude=True)
    consume_permission_resolution: PermissionResolutionConsumer | None = Field(default=None, exclude=True)
    read_file_state: Any = Field(default_factory=dict, exclude=True)
    loaded_nested_memory_paths: Any = Field(default_factory=set, exclude=True)
    discovered_skill_names: Any = Field(default_factory=set, exclude=True)
    discovered_tool_names: Any = Field(default_factory=set, exclude=True)
    nested_memory_attachment_triggers: Any = Field(default_factory=set, exclude=True)
    abort_controller: AbortController = Field(default_factory=AbortController, exclude=True)
    messages: list = Field(default_factory=list)
    thread_id: str = "default"
    turn_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])

    model_config = ConfigDict(arbitrary_types_allowed=True)
