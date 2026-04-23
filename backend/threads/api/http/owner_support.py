"""Shared helper functions for owner-facing thread HTTP routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.identity.avatar.urls import avatar_url
from backend.monitor.application.use_cases.thread_workbench import (
    build_owner_thread_workbench_from_rows,
    sidebar_label,
)
from backend.monitor.infrastructure.read_models.thread_workbench_read_service import build_owner_thread_workbench_reader
from backend.monitor.infrastructure.resources.resource_overview_cache import clear_resource_overview_cache
from backend.sandboxes import account as account_resource_service
from backend.sandboxes import provider_factory as sandbox_provider_factory
from backend.sandboxes.inventory import init_providers_and_managers
from backend.threads.file_channel import get_file_channel_binding
from backend.threads.launch_config import resolve_default_config
from backend.threads.owner_reads import list_owner_thread_rows_for_auth_burst
from backend.threads.run.lifecycle import prime_sandbox
from backend.threads.state import get_sandbox_info
from sandbox.config import MountSpec
from sandbox.manager import bind_thread_to_existing_sandbox, resolve_existing_sandbox_runtime
from sandbox.recipes import default_recipe_id, normalize_recipe_snapshot, provider_type_from_name
from storage.contracts import WorkspaceRow


def format_ask_user_question_followup(
    pending_request: dict[str, Any],
    *,
    answers: list[dict[str, Any]],
    annotations: dict[str, Any] | None,
) -> str:
    import json

    payload: dict[str, Any] = {
        "questions": (pending_request.get("args") or {}).get("questions", []),
        "answers": answers,
    }
    if annotations is not None:
        payload["annotations"] = annotations
    return (
        "The user answered your AskUserQuestion prompt. Continue the task using these answers.\n"
        "<ask_user_question_answers>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</ask_user_question_answers>"
    )


def build_ask_user_question_answered_payload(
    pending_request: dict[str, Any],
    *,
    answers: list[dict[str, Any]],
    annotations: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "questions": (pending_request.get("args") or {}).get("questions", []),
        "answers": answers,
    }
    if annotations is not None:
        payload["annotations"] = annotations
    return payload


def serialize_permission_answers(payload: Any) -> list[dict[str, Any]] | None:
    raw_answers = getattr(payload, "answers", None)
    if raw_answers is None:
        return None
    serialized: list[dict[str, Any]] = []
    for item in raw_answers:
        if hasattr(item, "model_dump"):
            serialized.append(item.model_dump(exclude_none=True))
        elif isinstance(item, dict):
            serialized.append({key: value for key, value in item.items() if value is not None})
        else:
            serialized.append({key: value for key, value in vars(item).items() if value is not None})
    return serialized


def find_owned_agent(app: Any, agent_id: str, owner_user_id: str) -> Any | None:
    agent = app.state.auth_runtime_state.user_directory.get_by_id(agent_id)
    if not agent or agent.owner_user_id != owner_user_id:
        return None
    return agent


def require_owned_agent(app: Any, agent_id: str, owner_user_id: str) -> Any:
    agent = find_owned_agent(app, agent_id, owner_user_id)
    if agent is None:
        raise HTTPException(403, "Not authorized")
    return agent


def resolve_default_config_for_owned_agent(app: Any, owner_user_id: str, agent_user_id: str) -> dict[str, Any]:
    require_owned_agent(app, agent_user_id, owner_user_id)
    from backend.library.service import list_library
    from backend.sandboxes import service as sandbox_service
    from backend.threads import launch_config as launch_config_owner

    launch_config_owner.available_sandbox_types = sandbox_service.available_sandbox_types
    launch_config_owner.list_library = list_library
    return resolve_default_config(app, owner_user_id, agent_user_id)


def thread_payload(app: Any, thread_id: str, sandbox_type: str) -> dict[str, Any]:
    thread = app.state.threads_runtime_state.thread_repo.get_by_id(thread_id)
    if thread is None:
        raise HTTPException(404, "Thread not found")
    agent_user = app.state.auth_runtime_state.user_directory.get_by_id(thread["agent_user_id"])
    if agent_user is None:
        raise HTTPException(500, f"Thread {thread_id} missing agent user")
    return {
        "thread_id": thread_id,
        "sandbox": sandbox_type,
        "agent_user_id": agent_user.id,
        "agent_name": agent_user.display_name,
        "branch_index": thread["branch_index"],
        "sidebar_label": sidebar_label(is_main=thread["is_main"], branch_index=thread["branch_index"]),
        "avatar_url": avatar_url(agent_user.id, bool(agent_user.avatar)),
        "is_main": thread["is_main"],
    }


def invalidate_resource_overview_cache() -> None:
    clear_resource_overview_cache()


def thread_sandbox_info(app: Any, thread_id: str, sandbox_type: str) -> dict[str, Any] | None:
    return get_sandbox_info(app, thread_id, sandbox_type)


async def prepare_attachment_message(
    thread_id: str,
    sandbox_type: str,
    message: str,
    attachments: list[str],
    agent: Any | None = None,
) -> tuple[str, dict[str, Any] | None]:
    message_metadata: dict[str, Any] = {"attachments": attachments, "original_message": message}
    if agent is not None and getattr(agent, "_sandbox", None):
        mgr = agent._sandbox.manager
    else:
        _, managers = init_providers_and_managers()
        mgr = managers.get(sandbox_type)

    if mgr and mgr.volume.capability.runtime_kind == "local":
        try:
            binding = get_file_channel_binding(thread_id)
            files_dir = str(binding.local_staging_root) if binding.local_staging_root is not None else binding.workspace_path
        except ValueError:
            files_dir = "/workspace/files"
    else:
        files_dir = mgr.volume.resolve_mount_path() if mgr else "/workspace/files"

    original_message = message
    sync_ok = True

    if mgr and agent is not None:
        try:
            await prime_sandbox(agent, thread_id)
        except Exception:
            pass
    if mgr:
        try:
            sync_ok = await asyncio.to_thread(mgr.sync_uploads, thread_id, attachments)
        except Exception:
            sync_ok = False

    if sync_ok:
        message = f"[User uploaded {len(attachments)} file(s) to {files_dir}/: {', '.join(attachments)}]\n\n{original_message}"
    else:
        message = (
            f"[User uploaded {len(attachments)} file(s) but sync to sandbox failed. "
            f"Files may not be available in {files_dir}/.]\n\n{original_message}"
        )

    return message, message_metadata


async def list_owned_threads_payload(app: Any, user_id: str) -> dict[str, Any]:
    raw = await list_owner_thread_rows_for_auth_burst(app, user_id)
    reader = build_owner_thread_workbench_reader(app)

    return await asyncio.to_thread(build_owner_thread_workbench_from_rows, raw, reader=reader)


async def validate_mount_capability_gate(
    sandbox_type: str,
    requested_mounts: list[MountSpec],
) -> Any:
    if not requested_mounts:
        return None

    providers, _ = await asyncio.to_thread(init_providers_and_managers)
    provider_obj = providers.get(sandbox_type)
    if provider_obj is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "sandbox_provider_unavailable",
                "provider": sandbox_type,
            },
        )

    capability = provider_obj.get_capability()
    capability_dict = capability.mount.to_dict()
    mode_handlers = capability_dict.get("mode_handlers", {})
    for mount in requested_mounts:
        requested = {"mode": mount.mode, "read_only": mount.read_only}
        mode_supported = bool(mode_handlers.get(mount.mode, False)) if mode_handlers else False
        if not mode_supported or (mount.read_only and not capability_dict["supports_read_only"]):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "sandbox_capability_mismatch",
                    "provider": sandbox_type,
                    "requested": requested,
                    "capability": capability_dict,
                },
            )
    return None


def validate_sandbox_provider_gate(app: Any, owner_user_id: str, payload: Any) -> Any:
    sandbox_type = payload.sandbox or "local"
    if getattr(payload, "existing_sandbox_id", None):
        lower_runtime_row = app.state.sandbox_repo.get_by_id(payload.existing_sandbox_id)
        if lower_runtime_row is not None:
            sandbox_type = str(lower_runtime_row.get("provider_name") or sandbox_type)
    if sandbox_type == "local":
        return None
    provider = sandbox_provider_factory.build_provider_from_config_name(sandbox_type)
    if provider is not None:
        return None

    return JSONResponse(
        status_code=400,
        content={
            "error": "sandbox_provider_unavailable",
            "provider": sandbox_type,
        },
    )


def validate_sandbox_quota_gate(app: Any, owner_user_id: str, payload: Any) -> Any:
    if getattr(payload, "existing_sandbox_id", None):
        return None
    sandbox_type = payload.sandbox or "local"
    try:
        account_resource_service.assert_can_create_sandbox(app, owner_user_id, sandbox_type)
    except account_resource_service.AccountResourceLimitExceededError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "error": "sandbox_quota_exceeded",
                "message": str(exc),
                "resource": exc.resource,
            },
        )
    return None


def request_row_text(row: Any, key: str, *, label: str) -> str:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        raise RuntimeError(f"{label}.{key} is required")
    return str(value)


class ExistingSandboxThreadBinding:
    def __init__(self, *, sandbox_id: str, sandbox_type: str, workspace_path: str | None, thread_cwd: str) -> None:
        self.sandbox_id = sandbox_id
        self.sandbox_type = sandbox_type
        self.workspace_path = workspace_path
        self.thread_cwd = thread_cwd


def resolve_owned_existing_sandbox_request_lease(
    app: Any,
    owner_user_id: str,
    existing_sandbox_id: str,
) -> dict[str, Any] | None:
    normalized_id = str(existing_sandbox_id or "").strip()
    if not normalized_id:
        return None

    sandbox_repo = getattr(app.state, "sandbox_repo", None)
    sandbox_get_by_id = getattr(sandbox_repo, "get_by_id", None)
    if not callable(sandbox_get_by_id):
        return None
    sandbox = sandbox_get_by_id(normalized_id)
    if sandbox is None:
        return None

    sandbox_owner_user_id = request_row_text(sandbox, "owner_user_id", label="sandbox")
    if sandbox_owner_user_id != owner_user_id:
        raise HTTPException(403, "Not authorized")
    return resolve_existing_sandbox_runtime(
        sandbox,
        lease_repo=getattr(app.state, "lease_repo", None),
    )


def materialize_workspace_for_sandbox(
    workspace_repo: Any,
    *,
    sandbox_id: str,
    owner_user_id: str,
    workspace_path: str | None,
) -> str:
    import time
    import uuid

    normalized_path = str(workspace_path or "").strip() or "/workspace"
    for row in workspace_repo.list_by_sandbox_id(sandbox_id):
        if row.owner_user_id == owner_user_id and row.workspace_path == normalized_path:
            return row.id

    workspace_id = f"workspace-{uuid.uuid4().hex}"
    now = time.time()
    workspace_repo.create(
        WorkspaceRow(
            id=workspace_id,
            sandbox_id=sandbox_id,
            owner_user_id=owner_user_id,
            workspace_path=normalized_path,
            name=None,
            created_at=now,
            updated_at=now,
        )
    )
    return workspace_id


def resolve_existing_sandbox_bind_cwd(
    workspace_repo: Any,
    *,
    sandbox_id: str,
    owner_user_id: str,
    requested_cwd: str | None,
) -> str | None:
    normalized_requested = str(requested_cwd or "").strip()
    if normalized_requested:
        return normalized_requested

    owned_rows = [row for row in workspace_repo.list_by_sandbox_id(sandbox_id) if row.owner_user_id == owner_user_id]
    if len(owned_rows) != 1:
        return None
    return str(owned_rows[0].workspace_path or "").strip() or None


def bind_existing_sandbox_for_thread(
    app: Any,
    owner_user_id: str,
    thread_id: str,
    existing_sandbox_id: str,
    requested_cwd: str | None,
) -> ExistingSandboxThreadBinding:
    sandbox_id = str(existing_sandbox_id or "").strip()
    sandbox = app.state.sandbox_repo.get_by_id(sandbox_id)
    if sandbox is None:
        raise HTTPException(403, "Sandbox not authorized")

    resolved_lease = resolve_owned_existing_sandbox_request_lease(
        app,
        owner_user_id,
        sandbox_id,
    )
    if resolved_lease is None:
        raise HTTPException(403, "Sandbox not authorized")

    bind_cwd = resolve_existing_sandbox_bind_cwd(
        app.state.workspace_repo,
        sandbox_id=sandbox_id,
        owner_user_id=owner_user_id,
        requested_cwd=requested_cwd,
    )
    bound_cwd, bound_lease = bind_thread_to_existing_sandbox(
        thread_id,
        sandbox,
        cwd=bind_cwd,
        lease_repo=getattr(app.state, "lease_repo", None),
    )
    if bound_lease is None:
        raise HTTPException(403, "Sandbox not authorized")

    return ExistingSandboxThreadBinding(
        sandbox_id=sandbox_id,
        sandbox_type=str(bound_lease["provider_name"] or ""),
        workspace_path=bind_cwd or bound_cwd,
        thread_cwd=bound_cwd,
    )


def resolve_owned_recipe_snapshot(
    app: Any,
    owner_user_id: str,
    sandbox_type: str,
    recipe_id: str | None,
) -> dict[str, Any]:
    resolved_recipe_id = str(recipe_id or default_recipe_id(sandbox_type)).strip()
    if not resolved_recipe_id:
        raise HTTPException(400, "Recipe id is required")

    runtime_storage = getattr(app.state, "runtime_storage_state", None)
    recipe_repo = getattr(runtime_storage, "recipe_repo", None)
    if recipe_repo is None:
        raise RuntimeError("recipe_repo is required for thread recipe resolution")

    row = recipe_repo.get(owner_user_id, resolved_recipe_id)
    if row is None:
        raise HTTPException(400, "Recipe not found")

    data = row.get("data")
    if not isinstance(data, dict):
        raise HTTPException(400, "Recipe is malformed")

    snapshot = normalize_recipe_snapshot(provider_type_from_name(sandbox_type), data)
    if snapshot.get("provider_name") != sandbox_type:
        raise HTTPException(400, "Recipe provider mismatch")
    return snapshot


def create_thread_sandbox_resources(
    thread_id: str,
    sandbox_type: str,
    recipe: dict[str, Any] | None,
    cwd: str | None = None,
    *,
    workspace_repo: Any,
    owner_user_id: str,
) -> str:
    import json
    import uuid

    from sandbox.control_plane_repos import make_terminal_repo
    from storage.runtime import build_lease_repo as make_lease_repo

    lease_repo = make_lease_repo()
    try:
        lease_id = f"lease-{uuid.uuid4().hex[:12]}"
        normalized_recipe = normalize_recipe_snapshot(provider_type_from_name(sandbox_type), recipe, provider_name=sandbox_type)
        created_lease = lease_repo.create(
            lease_id,
            sandbox_type,
            recipe_id=normalized_recipe["id"],
            recipe_json=json.dumps(normalized_recipe, ensure_ascii=False),
            owner_user_id=owner_user_id,
        )
    finally:
        lease_repo.close()

    sandbox_id = str((created_lease or {}).get("sandbox_id") or "").strip()
    if not sandbox_id:
        raise RuntimeError("lease_repo.create must return sandbox_id for thread sandbox resources")

    terminal_repo = make_terminal_repo()
    if terminal_repo is None:
        raise RuntimeError("terminal_repo is required for thread sandbox resources")
    try:
        terminal_id = f"term-{uuid.uuid4().hex[:12]}"
        from backend.web.core.config import LOCAL_WORKSPACE_ROOT

        if sandbox_type == "local":
            initial_cwd = cwd or str(LOCAL_WORKSPACE_ROOT)
        else:
            from sandbox.manager import resolve_provider_cwd

            provider = sandbox_provider_factory.build_provider_from_config_name(sandbox_type)
            initial_cwd = resolve_provider_cwd(provider) if provider else "/home/user"
        terminal_repo.create(
            terminal_id=terminal_id,
            thread_id=thread_id,
            lease_id=lease_id,
            initial_cwd=initial_cwd,
        )
    finally:
        terminal_repo.close()

    return materialize_workspace_for_sandbox(
        workspace_repo,
        sandbox_id=sandbox_id,
        owner_user_id=owner_user_id,
        workspace_path=initial_cwd,
    )


def create_owned_thread(
    app: Any,
    owner_user_id: str,
    payload: Any,
    *,
    is_main: bool,
) -> dict[str, Any]:
    import time

    sandbox_type = payload.sandbox or "local"
    agent_user_id = payload.agent_user_id
    agent_user = app.state.auth_runtime_state.user_directory.get_by_id(agent_user_id)
    if not agent_user or agent_user.owner_user_id != owner_user_id:
        raise HTTPException(403, "Not authorized")

    seq = app.state.auth_runtime_state.user_directory.increment_thread_seq(agent_user_id)
    new_thread_id = f"{agent_user_id}-{seq}"
    thread_repo = app.state.threads_runtime_state.thread_repo
    has_main = thread_repo.get_default_thread(agent_user_id) is not None
    resolved_is_main = is_main or not has_main
    branch_index = 0 if resolved_is_main else thread_repo.get_next_branch_index(agent_user_id)

    existing_binding: ExistingSandboxThreadBinding | None = None
    if payload.existing_sandbox_id:
        existing_binding = bind_existing_sandbox_for_thread(
            app,
            owner_user_id,
            new_thread_id,
            payload.existing_sandbox_id,
            payload.cwd,
        )
        sandbox_type = existing_binding.sandbox_type or sandbox_type
    selected_recipe = None
    if existing_binding is None:
        selected_recipe = resolve_owned_recipe_snapshot(app, owner_user_id, sandbox_type, payload.sandbox_template_id)

    if existing_binding is not None:
        current_workspace_id = materialize_workspace_for_sandbox(
            app.state.workspace_repo,
            sandbox_id=existing_binding.sandbox_id,
            owner_user_id=owner_user_id,
            workspace_path=existing_binding.workspace_path,
        )
    else:
        current_workspace_id = create_thread_sandbox_resources(
            new_thread_id,
            sandbox_type,
            selected_recipe,
            payload.cwd,
            workspace_repo=app.state.workspace_repo,
            owner_user_id=owner_user_id,
        )

    thread_repo.create(
        thread_id=new_thread_id,
        agent_user_id=agent_user_id,
        sandbox_type=sandbox_type,
        cwd=payload.cwd,
        created_at=time.time(),
        model=payload.model,
        is_main=resolved_is_main,
        branch_index=branch_index,
        owner_user_id=owner_user_id,
        current_workspace_id=current_workspace_id,
    )

    app.state.thread_sandbox[new_thread_id] = sandbox_type
    if payload.cwd:
        app.state.thread_cwd[new_thread_id] = payload.cwd
    if existing_binding is not None:
        app.state.thread_cwd[new_thread_id] = existing_binding.thread_cwd

    return {
        "thread_id": new_thread_id,
        "sandbox": sandbox_type,
        "agent_user_id": agent_user_id,
        "agent_name": agent_user.display_name,
        "branch_index": branch_index,
        "sidebar_label": sidebar_label(is_main=resolved_is_main, branch_index=branch_index),
        "avatar_url": avatar_url(agent_user_id, bool(agent_user.avatar)),
        "is_main": resolved_is_main,
    }


def thread_messages_payload(
    *,
    thread_id: str,
    entries: list[dict[str, Any]],
    display_builder: Any,
    sandbox_info: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "entries": entries,
        "display_seq": display_builder.get_display_seq(thread_id),
        "sandbox": sandbox_info,
    }
