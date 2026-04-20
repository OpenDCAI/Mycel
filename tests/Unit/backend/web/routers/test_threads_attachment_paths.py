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
