from __future__ import annotations

from dataclasses import asdict
from inspect import signature
from pathlib import Path

import pytest

from backend.web.services.thread_runtime_binding_service import (
    ThreadRuntimeBindingError,
    resolve_thread_runtime_binding,
)


class _Repo:
    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    def get_by_id(self, row_id: str):
        return self.rows.get(row_id)


def _repos(
    *,
    thread: dict | None = None,
    workspace: dict | None = None,
    sandbox: dict | None = None,
):
    return {
        "thread_repo": _Repo({"thread-1": thread} if thread is not None else {}),
        "workspace_repo": _Repo({"workspace-1": workspace} if workspace is not None else {}),
        "sandbox_repo": _Repo({"sandbox-1": sandbox} if sandbox is not None else {}),
    }


def _thread(**overrides):
    return {
        "id": "thread-1",
        "owner_user_id": "owner-1",
        "agent_user_id": "agent-1",
        "current_workspace_id": "workspace-1",
        "model": "large",
        "cwd": "/legacy-cwd",
        **overrides,
    }


def _workspace(**overrides):
    return {
        "id": "workspace-1",
        "owner_user_id": "owner-1",
        "sandbox_id": "sandbox-1",
        "workspace_path": "/workspace",
        "status": "ready",
        "desired_state": "running",
        "observed_state": "running",
        **overrides,
    }


def _sandbox(**overrides):
    return {
        "id": "sandbox-1",
        "owner_user_id": "owner-1",
        "device_id": "device-1",
        "provider_name": "daytona",
        "provider_env_id": "provider-env-1",
        "status": "ready",
        "desired_state": "running",
        "observed_state": "running",
        "template_id": "template-1",
        "config": {"sdk": "preinstalled"},
        **overrides,
    }


def test_resolves_thread_workspace_sandbox_binding_without_legacy_runtime_ids() -> None:
    binding = resolve_thread_runtime_binding(
        **_repos(thread=_thread(), workspace=_workspace(), sandbox=_sandbox()),
        thread_id="thread-1",
        owner_user_id="owner-1",
    )

    assert binding.thread_id == "thread-1"
    assert binding.owner_user_id == "owner-1"
    assert binding.agent_user_id == "agent-1"
    assert binding.workspace_id == "workspace-1"
    assert binding.workspace_path == "/workspace"
    assert binding.workspace_status == "ready"
    assert binding.workspace_desired_state == "running"
    assert binding.workspace_observed_state == "running"
    assert binding.sandbox_id == "sandbox-1"
    assert binding.device_id == "device-1"
    assert binding.provider_name == "daytona"
    assert binding.provider_env_id == "provider-env-1"
    assert binding.sandbox_status == "ready"
    assert binding.sandbox_desired_state == "running"
    assert binding.sandbox_observed_state == "running"
    assert binding.sandbox_template_id == "template-1"
    assert binding.sandbox_config == {"sdk": "preinstalled"}
    assert binding.model == "large"
    assert binding.legacy_cwd == "/legacy-cwd"

    payload = asdict(binding)
    assert "terminal_id" not in payload
    assert "active_terminal_id" not in payload
    assert "chat_session_id" not in payload
    assert "lease_id" not in payload
    assert "volume_id" not in payload


def test_missing_workspace_pointer_fails_loudly() -> None:
    with pytest.raises(ThreadRuntimeBindingError) as excinfo:
        resolve_thread_runtime_binding(
            **_repos(thread=_thread(current_workspace_id=None), workspace=_workspace(), sandbox=_sandbox()),
            thread_id="thread-1",
            owner_user_id="owner-1",
        )

    assert "current_workspace_id" in str(excinfo.value)


def test_owner_mismatch_fails_loudly() -> None:
    with pytest.raises(PermissionError) as excinfo:
        resolve_thread_runtime_binding(
            **_repos(thread=_thread(), workspace=_workspace(), sandbox=_sandbox()),
            thread_id="thread-1",
            owner_user_id="other-owner",
        )

    assert "owner mismatch" in str(excinfo.value)


def test_missing_workspace_row_fails_loudly() -> None:
    with pytest.raises(ThreadRuntimeBindingError) as excinfo:
        resolve_thread_runtime_binding(
            **_repos(thread=_thread(), workspace=None, sandbox=_sandbox()),
            thread_id="thread-1",
            owner_user_id="owner-1",
        )

    assert "workspace-1" in str(excinfo.value)


def test_workspace_without_sandbox_fails_loudly() -> None:
    with pytest.raises(ThreadRuntimeBindingError) as excinfo:
        resolve_thread_runtime_binding(
            **_repos(thread=_thread(), workspace=_workspace(sandbox_id=None), sandbox=_sandbox()),
            thread_id="thread-1",
            owner_user_id="owner-1",
        )

    assert "sandbox_id" in str(excinfo.value)


def test_service_signature_does_not_expose_unused_purpose_dimension() -> None:
    assert "purpose" not in signature(resolve_thread_runtime_binding).parameters


def test_service_does_not_import_legacy_runtime_glue() -> None:
    source = Path("backend/web/services/thread_runtime_binding_service.py").read_text()

    assert "terminal_repo" not in source
    assert "lease_repo" not in source
    assert "chat_session" not in source
    assert "sandbox_volume" not in source
    assert "sync_file" not in source
