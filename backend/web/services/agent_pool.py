"""Agent pool management service."""

from backend.thread_runtime.pool import registry as _registry
from backend.thread_runtime.pool.factory import create_agent_sync
from backend.thread_runtime.sandbox import resolve_thread_sandbox
from backend.web.services.file_channel_service import get_file_channel_binding
from core.identity.agent_registry import get_or_create_agent_id


async def get_or_create_agent(*args, **kwargs):
    _registry.create_agent_sync = create_agent_sync
    _registry.get_or_create_agent_id = get_or_create_agent_id
    _registry.get_file_channel_binding = get_file_channel_binding
    _registry.resolve_thread_sandbox = resolve_thread_sandbox
    return await _registry.get_or_create_agent(*args, **kwargs)


async def update_agent_config(*args, **kwargs):
    _registry.create_agent_sync = create_agent_sync
    _registry.get_or_create_agent_id = get_or_create_agent_id
    _registry.get_file_channel_binding = get_file_channel_binding
    _registry.resolve_thread_sandbox = resolve_thread_sandbox
    return await _registry.update_agent_config(*args, **kwargs)
