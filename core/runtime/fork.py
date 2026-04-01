"""Context fork for sub-agent spawning.

When a sub-agent is spawned, it inherits workspace/model/permission configuration
from the parent but gets its own isolated messages and session identity.

Aligned with CC createSubagentContext() field-by-field fork table.
"""

from __future__ import annotations

import uuid

from .state import BootstrapConfig


def fork_context(parent: BootstrapConfig) -> BootstrapConfig:
    """Create a child BootstrapConfig for a sub-agent.

    Inherits all workspace identity, model settings, and security flags
    from parent. Generates a fresh session_id and sets parent_session_id.
    Messages, cost, and turn_count live in AppState — not here.
    """
    return BootstrapConfig(
        workspace_root=parent.workspace_root,
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
        # Model settings
        model_provider=parent.model_provider,
        base_url=parent.base_url,
        context_limit=parent.context_limit,
    )
