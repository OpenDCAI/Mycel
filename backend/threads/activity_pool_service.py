"""Agent pool management service."""

from backend.chat.runtime_access import get_optional_messaging_service
from backend.threads.file_channel import get_file_channel_binding
from backend.threads.pool import registry as _registry
from backend.threads.pool.factory import create_agent_sync
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from core.identity.agent_registry import get_or_create_agent_id


async def get_or_create_agent(*args, **kwargs):
    app = args[0] if args else kwargs.get("app_obj")
    _registry.create_agent_sync = create_agent_sync
    _registry.get_or_create_agent_id = get_or_create_agent_id
    _registry.get_file_channel_binding = get_file_channel_binding
    _registry.resolve_thread_sandbox = resolve_thread_sandbox
    if "messaging_service" not in kwargs and app is not None:
        # @@@agent-pool-chat-borrow - registry owns thread-runtime lifecycle,
        # but chat-owned messaging_service is still needed when chat_repos are
        # constructed. Borrow it here so registry does not reach back through
        # app state for chat truth on its own.
        messaging_service = get_optional_messaging_service(app)
        if messaging_service is not None:
            kwargs["messaging_service"] = messaging_service
    return await _registry.get_or_create_agent(*args, **kwargs)


async def update_agent_config(*args, **kwargs):
    _registry.create_agent_sync = create_agent_sync
    _registry.get_or_create_agent_id = get_or_create_agent_id
    _registry.get_file_channel_binding = get_file_channel_binding
    _registry.resolve_thread_sandbox = resolve_thread_sandbox
    return await _registry.update_agent_config(*args, **kwargs)
