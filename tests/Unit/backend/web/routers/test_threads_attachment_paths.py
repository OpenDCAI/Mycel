from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.routers import threads as threads_router


def test_threads_router_uses_neutral_provider_inventory_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.sandbox_service import destroy_thread_resources_sync, init_providers_and_managers" not in source
    assert "from backend.sandbox_inventory import init_providers_and_managers" in source


def test_threads_router_uses_neutral_provider_factory_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "sandbox_service.build_provider_from_config_name" not in source
    assert "from backend import sandbox_provider_factory" in source
    assert "sandbox_provider_factory.build_provider_from_config_name" in source
    assert "from backend.web.services.sandbox_service import build_provider_from_config_name" not in source


def test_threads_router_uses_neutral_thread_resource_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.sandbox_service import destroy_thread_resources_sync" not in source
    assert "from backend.sandbox_thread_resources import destroy_thread_resources_sync" in source


def test_threads_router_uses_neutral_thread_read_and_state_owners() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.owner_thread_read_service import list_owner_thread_rows_for_auth_burst" not in source
    assert "from backend.web.services.thread_state_service import (" not in source
    assert "from backend.thread_runtime.owner_reads import list_owner_thread_rows_for_auth_burst" in source
    assert "from backend.thread_runtime.state import get_sandbox_info, get_sandbox_status_from_repos" in source


def test_threads_router_uses_neutral_message_interruption_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.thread_message_interruption_service import repair_interrupted_tool_call_messages" not in source
    assert "from backend.thread_runtime.interruption import repair_interrupted_tool_call_messages" in source


def test_threads_router_uses_neutral_thread_event_buffer_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.event_buffer import ThreadEventBuffer" not in source
    assert "from backend.thread_runtime.events.buffer import ThreadEventBuffer" in source


def test_threads_router_uses_neutral_launch_config_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.thread_launch_config_service import resolve_default_config" not in source
    assert "from backend.thread_runtime.launch_config import resolve_default_config" in source


def test_threads_router_uses_neutral_streaming_route_owners() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.streaming_service import (" not in source
    assert "from backend.web.services.streaming_service import prime_sandbox" not in source
    assert "from backend.thread_runtime.run.buffer_wiring import get_or_create_thread_buffer" in source
    assert "from backend.thread_runtime.run.observer import observe_thread_events" in source
    assert "from backend.thread_runtime.run.lifecycle import prime_sandbox" in source


def test_threads_router_uses_neutral_thread_sandbox_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox" not in source
    assert "from backend.web.services.agent_pool import get_or_create_agent" in source
    assert "from backend.thread_runtime.sandbox import resolve_thread_sandbox" in source


def test_threads_router_uses_neutral_file_channel_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.file_channel_service import get_file_channel_binding" not in source
    assert "from backend.file_channel import get_file_channel_binding" in source


def test_threads_router_uses_neutral_resource_cache_owner() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.resource_cache import clear_resource_overview_cache" not in source
    assert "from backend.monitor.infrastructure.resources.resource_overview_cache import clear_resource_overview_cache" in source


def test_threads_router_uses_neutral_event_store_owners() -> None:
    source = inspect.getsource(threads_router)

    assert "from backend.web.services.event_store import get_latest_run_id, read_events_after" not in source
    assert "from backend.web.services.event_store import get_last_seq, get_latest_run_id, get_run_start_seq" not in source
    assert "from backend.thread_runtime.events.store import get_last_seq, get_latest_run_id, get_run_start_seq, read_events_after" in source


@pytest.mark.asyncio
async def test_prepare_attachment_message_uses_binding_local_staging_root(monkeypatch: pytest.MonkeyPatch):
    fake_manager = SimpleNamespace(
        volume=SimpleNamespace(capability=SimpleNamespace(runtime_kind="local")),
        sync_uploads=lambda thread_id, attachments: True,
    )

    monkeypatch.setattr(threads_router, "init_providers_and_managers", lambda: ({}, {"local": fake_manager}))
    monkeypatch.setattr(
        threads_router,
        "get_file_channel_binding",
        lambda thread_id: SimpleNamespace(
            local_staging_root=Path("/tmp/channel-root"),
            workspace_id="workspace-1",
            workspace_path="/workspace/root",
            remote_files_dir="/workspace/files",
        ),
        raising=False,
    )

    message, metadata = await threads_router._prepare_attachment_message(
        thread_id="thread-1",
        sandbox_type="local",
        message="hello",
        attachments=["notes.txt"],
    )

    assert f"{Path('/tmp/channel-root')}/" in message
    assert metadata == {"attachments": ["notes.txt"], "original_message": "hello"}
