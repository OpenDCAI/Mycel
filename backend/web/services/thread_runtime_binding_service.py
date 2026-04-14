"""Target-style thread runtime binding read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ThreadRuntimeBindingError(RuntimeError):
    """Raised when a thread cannot satisfy the target runtime binding contract."""


@dataclass(frozen=True)
class ThreadRuntimeBinding:
    thread_id: str
    owner_user_id: str
    agent_user_id: str
    workspace_id: str
    workspace_path: str
    workspace_status: str | None
    workspace_desired_state: str | None
    workspace_observed_state: str | None
    sandbox_id: str
    device_id: str | None
    provider_name: str
    provider_env_id: str | None
    sandbox_status: str | None
    sandbox_desired_state: str | None
    sandbox_observed_state: str | None
    sandbox_template_id: str | None
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    legacy_cwd: str | None = None


def resolve_thread_runtime_binding(
    *,
    thread_repo: Any,
    workspace_repo: Any,
    sandbox_repo: Any,
    thread_id: str,
    owner_user_id: str | None = None,
) -> ThreadRuntimeBinding:
    thread = _load_row(thread_repo, thread_id, "thread")
    thread_owner_user_id = _required_text(thread, "owner_user_id", "thread")
    if owner_user_id is not None and owner_user_id != thread_owner_user_id:
        raise PermissionError(f"thread owner mismatch: expected {owner_user_id}, got {thread_owner_user_id}")

    workspace_id = _required_text(thread, "current_workspace_id", "thread")
    workspace = _load_row(workspace_repo, workspace_id, "workspace")
    _require_same_owner(workspace, thread_owner_user_id, "workspace")

    sandbox_id = _required_text(workspace, "sandbox_id", "workspace")
    sandbox = _load_row(sandbox_repo, sandbox_id, "sandbox")
    _require_same_owner(sandbox, thread_owner_user_id, "sandbox")

    return ThreadRuntimeBinding(
        thread_id=thread_id,
        owner_user_id=thread_owner_user_id,
        agent_user_id=_required_text(thread, "agent_user_id", "thread"),
        workspace_id=workspace_id,
        workspace_path=_required_text(workspace, "workspace_path", "workspace"),
        workspace_status=_optional_text(workspace, "status"),
        workspace_desired_state=_optional_text(workspace, "desired_state"),
        workspace_observed_state=_optional_text(workspace, "observed_state"),
        sandbox_id=sandbox_id,
        device_id=_optional_text(sandbox, "device_id"),
        provider_name=_required_text(sandbox, "provider_name", "sandbox"),
        provider_env_id=_optional_text(sandbox, "provider_env_id"),
        sandbox_status=_optional_text(sandbox, "status"),
        sandbox_desired_state=_optional_text(sandbox, "desired_state"),
        sandbox_observed_state=_optional_text(sandbox, "observed_state"),
        sandbox_template_id=_optional_text(sandbox, "sandbox_template_id"),
        sandbox_config=_config_dict(sandbox),
        model=_optional_text(thread, "model"),
        legacy_cwd=_optional_text(thread, "cwd"),
    )


def _load_row(repo: Any, row_id: str, label: str) -> Any:
    get_by_id = getattr(repo, "get_by_id", None)
    if not callable(get_by_id):
        raise ThreadRuntimeBindingError(f"{label}_repo must support get_by_id")
    row = get_by_id(row_id)
    if row is None:
        raise ThreadRuntimeBindingError(f"{label} not found: {row_id}")
    return row


def _require_same_owner(row: Any, owner_user_id: str, label: str) -> None:
    row_owner_user_id = _required_text(row, "owner_user_id", label)
    if row_owner_user_id != owner_user_id:
        raise PermissionError(f"{label} owner mismatch: expected {owner_user_id}, got {row_owner_user_id}")


def _required_text(row: Any, key: str, label: str) -> str:
    value = _value(row, key)
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        raise ThreadRuntimeBindingError(f"{label}.{key} is required")
    return str(value)


def _optional_text(row: Any, key: str) -> str | None:
    value = _value(row, key)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _config_dict(sandbox: Any) -> dict[str, Any]:
    config = _value(sandbox, "config")
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ThreadRuntimeBindingError("sandbox.config must be an object")
    return dict(config)


def _value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)
