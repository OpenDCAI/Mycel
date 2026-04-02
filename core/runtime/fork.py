"""Context fork for sub-agent spawning.

When a sub-agent is spawned, it inherits workspace/model/permission configuration
from the parent but gets its own isolated messages and session identity.

Aligned with CC createSubagentContext() field-by-field fork table.
"""

from __future__ import annotations

import copy
import uuid

from .state import BootstrapConfig, ToolUseContext


def fork_context(parent: BootstrapConfig) -> BootstrapConfig:
    """Create a child BootstrapConfig for a sub-agent.

    Inherits all workspace identity, model settings, and security flags
    from parent. Generates a fresh session_id and sets parent_session_id.
    Messages, cost, and turn_count live in AppState — not here.
    """
    return BootstrapConfig(
        workspace_root=parent.workspace_root,
        original_cwd=parent.original_cwd,
        project_root=parent.project_root,
        cwd=parent.cwd,
        model_name=parent.model_name,
        api_key=parent.api_key,
        block_dangerous_commands=parent.block_dangerous_commands,
        block_network_commands=parent.block_network_commands,
        enable_audit_log=parent.enable_audit_log,
        enable_web_tools=parent.enable_web_tools,
        allowed_file_extensions=parent.allowed_file_extensions,
        extra_allowed_paths=parent.extra_allowed_paths,
        max_turns=parent.max_turns,
        # Fresh session identity
        session_id=uuid.uuid4().hex,
        parent_session_id=parent.session_id,
        total_cost_usd=parent.total_cost_usd,
        total_tool_duration_ms=parent.total_tool_duration_ms,
        # Model settings
        model_provider=parent.model_provider,
        base_url=parent.base_url,
        context_limit=parent.context_limit,
    )


def create_subagent_context(
    parent: ToolUseContext,
    *,
    share_set_app_state: bool = False,
) -> ToolUseContext:
    """Create a minimally isolated ToolUseContext for sub-agents.

    Default contract:
    - bootstrap: fresh fork
    - set_app_state: NO-OP
    - set_app_state_for_tasks: always reaches the root/session store
    - turn-local refs: fresh
    - file cache/messages: cloned snapshots
    """
    read_file_state = parent.read_file_state
    if hasattr(read_file_state, "clone") and callable(read_file_state.clone):
        cloned_read_file_state = read_file_state.clone()
    else:
        # @@@sa-04-read-file-state-clone
        # Subagent fork boundaries must isolate nested file cache state too;
        # a shallow dict copy leaks child edits back into the parent cache.
        cloned_read_file_state = copy.deepcopy(read_file_state)
    return ToolUseContext(
        bootstrap=fork_context(parent.bootstrap),
        get_app_state=parent.get_app_state,
        set_app_state=parent.set_app_state if share_set_app_state else (lambda updater: None),
        set_app_state_for_tasks=parent.set_app_state_for_tasks or parent.set_app_state,
        refresh_tools=parent.refresh_tools,
        read_file_state=cloned_read_file_state,
        loaded_nested_memory_paths=set(),
        discovered_skill_names=set(),
        nested_memory_attachment_triggers=set(),
        messages=list(parent.messages),
    )
