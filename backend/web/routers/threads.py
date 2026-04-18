"""Thread management and execution endpoints."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from backend.web.core.dependencies import (
    get_app,
    get_current_user_id,
    get_thread_agent,
    get_thread_lock,
    verify_thread_owner,
    verify_thread_row_owner,
)
from backend.web.models.requests import (
    CreateThreadRequest,
    ResolveMainThreadRequest,
    ResolvePermissionRequest,
    SendMessageRequest,
    ThreadPermissionRuleRequest,
)
from backend.web.services import account_resource_service, sandbox_service
from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
from backend.web.services.event_buffer import ThreadEventBuffer
from backend.web.services.file_channel_service import get_file_channel_binding
from backend.web.services.owner_thread_read_service import list_owner_thread_rows_for_auth_burst
from backend.web.services.resource_cache import clear_resource_overview_cache
from backend.web.services.sandbox_service import destroy_thread_resources_sync, init_providers_and_managers
from backend.web.services.streaming_service import (
    get_or_create_thread_buffer,
    observe_thread_events,
)
from backend.web.services.thread_launch_config_service import resolve_default_config
from backend.web.services.thread_message_interruption_service import repair_interrupted_tool_call_messages
from backend.web.services.thread_runtime_convergence import converge_owner_thread_runtime, summarize_owner_thread_runtime
from backend.web.services.thread_state_service import (
    get_sandbox_info,
    get_sandbox_status_from_repos,
)
from backend.web.services.thread_visibility import canonical_owner_threads
from backend.web.utils.helpers import delete_thread_in_db
from backend.web.utils.serializers import avatar_url, serialize_message
from core.agents.service import _background_run_cancelled, _background_run_result, request_background_run_stop
from core.runtime.middleware.monitor import AgentState
from sandbox.config import MountSpec
from sandbox.manager import bind_thread_to_existing_sandbox, resolve_existing_sandbox_lease
from sandbox.recipes import default_recipe_id, normalize_recipe_snapshot, provider_type_from_name
from sandbox.thread_context import set_current_thread_id
from storage.contracts import WorkspaceRow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads", tags=["threads"])


def _is_internal_child_thread(thread_id: str) -> bool:
    return thread_id.startswith("subagent-")


def _sidebar_label(*, is_main: bool, branch_index: int) -> str | None:
    if branch_index < 0:
        raise ValueError(f"branch_index must be >= 0, got {branch_index}")
    if is_main and branch_index != 0:
        raise ValueError(f"Default thread must have branch_index=0, got {branch_index}")
    if not is_main and branch_index == 0:
        raise ValueError("Child thread must have branch_index>0")
    return None


def _invalidate_resource_overview_cache() -> None:
    # @@@monitor-resource-overview-invalidation - thread/sandbox mutations change the monitor topology immediately.
    # Clear the overview snapshot so the next /api/monitor/resources read reflects the fresh binding/state.
    clear_resource_overview_cache()


def _find_owned_agent(app: Any, agent_id: str, owner_user_id: str) -> Any | None:
    agent = app.state.user_repo.get_by_id(agent_id)
    if not agent or agent.owner_user_id != owner_user_id:
        return None
    return agent


def _require_owned_agent(app: Any, agent_id: str, owner_user_id: str) -> Any:
    agent = _find_owned_agent(app, agent_id, owner_user_id)
    if agent is None:
        raise HTTPException(403, "Not authorized")
    return agent


def _resolve_default_config_for_owned_agent(app: Any, owner_user_id: str, agent_user_id: str) -> dict[str, Any]:
    _require_owned_agent(app, agent_user_id, owner_user_id)
    return resolve_default_config(app, owner_user_id, agent_user_id)


async def _prepare_attachment_message(
    thread_id: str,
    sandbox_type: str,
    message: str,
    attachments: list[str],
    agent: Any | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Build LLM notification prefix and sync uploads to running sandbox.

    Returns (modified_message, message_metadata).
    When *agent* is supplied, uses its live manager and primes the sandbox
    (resume if paused) before syncing.
    """
    from backend.web.services.streaming_service import prime_sandbox

    message_metadata: dict[str, Any] = {"attachments": attachments, "original_message": message}
    if agent is not None and getattr(agent, "_sandbox", None):
        mgr = agent._sandbox.manager
    else:
        _, managers = init_providers_and_managers()
        mgr = managers.get(sandbox_type)
    # @@@files-dir-hint - tell agent where uploaded files live
    # For local provider: actual host path (agent reads host FS directly)
    # For remote providers: container-side path
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

    # @@@sync-prime-then-upload - resume sandbox if paused, then push files
    if mgr and agent is not None:
        try:
            await prime_sandbox(agent, thread_id)
        except Exception:
            logger.warning("prime_sandbox before sync_uploads failed", exc_info=True)
    if mgr:
        try:
            sync_ok = await asyncio.to_thread(mgr.sync_uploads, thread_id, attachments)
        except Exception:
            logger.error("Failed to sync uploads to sandbox", exc_info=True)
            sync_ok = False

    # @@@sync-fail-honest - don't tell agent files are in sandbox if sync failed
    if sync_ok:
        message = f"[User uploaded {len(attachments)} file(s) to {files_dir}/: {', '.join(attachments)}]\n\n{original_message}"
    else:
        message = (
            f"[User uploaded {len(attachments)} file(s) but sync to sandbox failed. "
            f"Files may not be available in {files_dir}/.]\n\n{original_message}"
        )

    return message, message_metadata


def _find_mount_capability_mismatch(
    requested_mounts: list[MountSpec],
    mount_capability: Any,
) -> dict[str, Any] | None:
    capability = mount_capability.to_dict()
    mode_handlers = capability.get("mode_handlers", {})
    for mount in requested_mounts:
        requested = {"mode": mount.mode, "read_only": mount.read_only}
        # @@@mode-handler-gate - check provider supports the requested mount mode
        mode_supported = bool(mode_handlers.get(mount.mode, False)) if mode_handlers else False

        if not mode_supported:
            return {"requested": requested, "capability": capability}
        if mount.read_only and not capability["supports_read_only"]:
            return {"requested": requested, "capability": capability}
    return None


async def _validate_mount_capability_gate(
    sandbox_type: str,
    requested_mounts: list[MountSpec],
) -> JSONResponse | None:
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
    mismatch = _find_mount_capability_mismatch(requested_mounts, capability.mount)
    if mismatch is None:
        return None

    # @@@request-stage-capability-gate - Fail at create-thread request stage so unsupported mount semantics never enter runtime lifecycle.
    return JSONResponse(
        status_code=400,
        content={
            "error": "sandbox_capability_mismatch",
            "provider": sandbox_type,
            "requested": mismatch["requested"],
            "capability": mismatch["capability"],
        },
    )


def _provider_unavailable_response(sandbox_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "sandbox_provider_unavailable",
            "provider": sandbox_type,
        },
    )


def _format_ask_user_question_followup(
    pending_request: dict[str, Any],
    *,
    answers: list[dict[str, Any]],
    annotations: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "questions": (pending_request.get("args") or {}).get("questions", []),
        "answers": answers,
    }
    if annotations is not None:
        payload["annotations"] = annotations
    # @@@ask-user-followup-payload - keep this as one narrow, structured owner reply
    # so the resumed run can continue from the user's choices without inventing
    # a bespoke second continuation channel.
    return (
        "The user answered your AskUserQuestion prompt. Continue the task using these answers.\n"
        "<ask_user_question_answers>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</ask_user_question_answers>"
    )


def _build_ask_user_question_answered_payload(
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


def _serialize_permission_answers(payload: Any) -> list[dict[str, Any]] | None:
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


def _validate_sandbox_provider_gate(app: Any, owner_user_id: str, payload: CreateThreadRequest) -> JSONResponse | None:
    sandbox_type = payload.sandbox or "local"
    if payload.existing_sandbox_id:
        lower_runtime_row = _resolve_owned_existing_sandbox_request_lease(app, owner_user_id, payload.existing_sandbox_id)
        if lower_runtime_row is not None:
            sandbox_type = str(lower_runtime_row["provider_name"] or sandbox_type)
    if sandbox_type == "local":
        return None
    provider = sandbox_service.build_provider_from_config_name(sandbox_type)
    if provider is not None:
        return None
    return _provider_unavailable_response(sandbox_type)


def _validate_sandbox_quota_gate(app: Any, owner_user_id: str, payload: CreateThreadRequest) -> JSONResponse | None:
    if payload.existing_sandbox_id:
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


def _request_row_text(row: Any, key: str, *, label: str) -> str:
    value = row.get(key) if isinstance(row, dict) else getattr(row, key, None)
    if isinstance(value, str):
        value = value.strip()
    if value is None or value == "":
        raise RuntimeError(f"{label}.{key} is required")
    return str(value)


@dataclass(frozen=True)
class _ExistingSandboxThreadBinding:
    sandbox_id: str
    sandbox_type: str
    workspace_path: str | None
    thread_cwd: str


def _resolve_owned_existing_sandbox_request_lease(
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

    # @@@existing-sandbox-request-cutover - incoming existing_sandbox_id is sandbox-shaped;
    # lower runtime identity is resolved only behind the row.
    sandbox_owner_user_id = _request_row_text(sandbox, "owner_user_id", label="sandbox")
    if sandbox_owner_user_id != owner_user_id:
        raise HTTPException(403, "Not authorized")
    return resolve_existing_sandbox_lease(
        sandbox,
        lease_repo=getattr(app.state, "lease_repo", None),
    )


def _get_agent_for_thread(app: Any, thread_id: str) -> Any | None:
    """Get agent instance for a thread from the agent pool."""
    pool = getattr(app.state, "agent_pool", None)
    if pool is None:
        return None
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"
    return pool.get(pool_key)


def _thread_payload(app: Any, thread_id: str, sandbox_type: str) -> dict[str, Any]:
    thread = app.state.thread_repo.get_by_id(thread_id)
    if thread is None:
        raise HTTPException(404, "Thread not found")
    agent_user = app.state.user_repo.get_by_id(thread["agent_user_id"])
    if agent_user is None:
        raise HTTPException(500, f"Thread {thread_id} missing agent user")
    return {
        "thread_id": thread_id,
        "sandbox": sandbox_type,
        "agent_user_id": agent_user.id,
        "agent_name": agent_user.display_name,
        "branch_index": thread["branch_index"],
        "sidebar_label": _sidebar_label(is_main=thread["is_main"], branch_index=thread["branch_index"]),
        "avatar_url": avatar_url(agent_user.id, bool(agent_user.avatar)),
        "is_main": thread["is_main"],
    }


_IDLE_REPLAYABLE_RUN_EVENTS = frozenset({"error", "cancelled", "retry"})


def _checkpoint_tail_is_pending_owner_turn(messages: list[dict[str, Any]]) -> bool:
    if not messages:
        return False
    tail = messages[-1]
    if tail.get("type") != "HumanMessage":
        return False
    meta = tail.get("metadata") or {}
    return meta.get("source") not in {"system", "external"}


async def _get_thread_display_entries(app: Any, thread_id: str) -> list[dict[str, Any]]:
    display_builder = app.state.display_builder
    entries = display_builder.get_entries(thread_id)
    if entries is not None:
        _normalize_blocking_subagent_terminal_status(entries)
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    if entries is not None and getattr(agent.runtime, "current_state", None) != AgentState.IDLE:
        return entries

    set_current_thread_id(thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent.agent.aget_state(config)
    values = getattr(state, "values", {}) if state else {}
    messages = values.get("messages", []) if isinstance(values, dict) else []
    messages = repair_interrupted_tool_call_messages(list(messages))
    serialized = [serialize_message(msg) for msg in messages]

    from core.runtime.visibility import annotate_owner_visibility

    annotated, _ = annotate_owner_visibility(serialized)
    if entries is not None and not _display_entries_need_idle_rebuild(entries, annotated):
        return entries
    entries = display_builder.build_from_checkpoint(thread_id, annotated)
    if _checkpoint_tail_is_pending_owner_turn(annotated):
        await _replay_latest_run_failure_events(
            thread_id=thread_id,
            display_builder=display_builder,
        )
        entries = display_builder.get_entries(thread_id) or entries
    _normalize_blocking_subagent_terminal_status(entries)
    return entries


def _display_entries_need_idle_rebuild(entries: list[dict[str, Any]], messages: list[dict[str, Any]]) -> bool:
    if not messages:
        return bool(entries)
    if not entries:
        return True
    # @@@idle-cache-honesty - idle detail must not trust cached assistant shells after
    # clear/restart. Rebuild only when cache is visibly impossible for the persisted checkpoint.
    return any(entry.get("role") == "assistant" and not entry.get("segments") for entry in entries)


def _normalize_blocking_subagent_terminal_status(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        if entry.get("role") != "assistant":
            continue
        for seg in entry.get("segments", []):
            if seg.get("type") != "tool":
                continue
            step = seg.get("step") or {}
            if step.get("name") != "Agent" or step.get("status") != "done":
                continue
            stream = step.get("subagent_stream")
            if not isinstance(stream, dict):
                continue
            result_text = step.get("result")
            existing_status = str(stream.get("status") or "").lower()
            terminal_status = (
                existing_status
                if existing_status in {"completed", "error", "cancelled"}
                else ("error" if isinstance(result_text, str) and result_text.startswith("<tool_use_error>") else "completed")
            )
            if stream.get("status") != terminal_status:
                # @@@blocking-subagent-terminal-honesty - a finished blocking Agent tool
                # must not keep exposing a stale running child status on refresh/detail/tasks.
                stream["status"] = terminal_status
            if terminal_status == "error" and not stream.get("error") and isinstance(result_text, str):
                stream["error"] = result_text


def _collect_display_subagent_tasks(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("role") != "assistant":
            continue
        for seg in entry.get("segments", []):
            if seg.get("type") != "tool":
                continue
            step = seg.get("step") or {}
            if step.get("name") != "Agent":
                continue
            stream = step.get("subagent_stream")
            if not isinstance(stream, dict) or not stream.get("task_id"):
                continue
            task_id = str(stream["task_id"])
            raw_args = step.get("args")
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            description = stream.get("description") or args.get("description") or args.get("prompt")
            status = str(stream.get("status") or ("completed" if step.get("status") == "done" else "running"))
            result_text = step.get("result") or stream.get("text")
            # @@@dual-source-task-surface - blocking Agent subagents never enter parent _background_runs,
            # so /tasks must also project persisted subagent_stream state from display history.
            tasks[task_id] = {
                "task_id": task_id,
                "task_type": "agent",
                "status": status,
                "command_line": None,
                "description": description,
                "exit_code": None,
                "error": stream.get("error"),
                "result": result_text,
                "text": result_text,
                "thread_id": stream.get("thread_id"),
            }
    return tasks


async def _replay_latest_run_failure_events(
    *,
    thread_id: str,
    display_builder: Any,
) -> None:
    from backend.web.services.event_store import get_latest_run_id, read_events_after

    run_id = await get_latest_run_id(thread_id)
    if not run_id or run_id.startswith("activity_"):
        return

    events = await read_events_after(thread_id, run_id, 0)
    if not any(event.get("event") in _IDLE_REPLAYABLE_RUN_EVENTS for event in events):
        return

    # @@@idle-run-error-replay - checkpoint can stop at the owner's input when
    # the run dies before first persisted AI/Tool message. Rebuild must replay
    # the latest run-level failure events so refresh/detail stays honest.
    for event in events:
        event_type = event.get("event", "")
        if event_type not in {"run_start", "run_done", *_IDLE_REPLAYABLE_RUN_EVENTS}:
            continue
        raw_data = event.get("data", "{}")
        try:
            payload = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        display_builder.apply_event(thread_id, event_type, payload)


def _create_thread_sandbox_resources(
    thread_id: str,
    sandbox_type: str,
    recipe: dict[str, Any] | None,
    cwd: str | None = None,
    *,
    workspace_repo: Any,
    owner_user_id: str,
) -> str:
    """Create lease and terminal resources without pre-provisioning file-channel storage."""
    from storage.runtime import build_lease_repo as make_lease_repo
    from storage.runtime import build_terminal_repo as make_terminal_repo

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
        # @@@initial-cwd - local threads own their requested cwd; remote threads start from provider defaults.
        from backend.web.core.config import LOCAL_WORKSPACE_ROOT

        if sandbox_type == "local":
            initial_cwd = cwd or str(LOCAL_WORKSPACE_ROOT)
        else:
            from backend.web.services.sandbox_service import build_provider_from_config_name
            from sandbox.manager import resolve_provider_cwd

            provider = build_provider_from_config_name(sandbox_type)
            initial_cwd = resolve_provider_cwd(provider) if provider else "/home/user"
        terminal_repo.create(
            terminal_id=terminal_id,
            thread_id=thread_id,
            lease_id=lease_id,
            initial_cwd=initial_cwd,
        )
    finally:
        terminal_repo.close()
    return _materialize_workspace_for_sandbox(
        workspace_repo,
        sandbox_id=sandbox_id,
        owner_user_id=owner_user_id,
        workspace_path=initial_cwd,
    )


def _materialize_workspace_for_sandbox(
    workspace_repo: Any,
    *,
    sandbox_id: str,
    owner_user_id: str,
    workspace_path: str | None,
) -> str:
    normalized_path = str(workspace_path or "").strip() or "/workspace"
    for row in workspace_repo.list_by_sandbox_id(sandbox_id):
        if row.owner_user_id == owner_user_id and row.workspace_path == normalized_path:
            return row.id

    workspace_id = f"workspace-{uuid.uuid4().hex}"
    now = time.time()
    # @@@workspace-binding-write - Phase 2 cuts thread create writes to a real
    # workspace row; lower lease_id remains terminal/runtime internals, not workspace authority.
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


def _resolve_existing_sandbox_bind_cwd(
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

    # @@@existing-sandbox-workspace-cwd-candidate - only reuse workspace truth when
    # caller side can point at one unambiguous owned workspace row for this sandbox.
    return str(owned_rows[0].workspace_path or "").strip() or None


def _bind_existing_sandbox_for_thread(
    app: Any,
    owner_user_id: str,
    thread_id: str,
    existing_sandbox_id: str,
    requested_cwd: str | None,
) -> _ExistingSandboxThreadBinding:
    sandbox_id = str(existing_sandbox_id or "").strip()
    sandbox = app.state.sandbox_repo.get_by_id(sandbox_id)
    if sandbox is None:
        raise HTTPException(403, "Sandbox not authorized")

    resolved_lease = _resolve_owned_existing_sandbox_request_lease(
        app,
        owner_user_id,
        sandbox_id,
    )
    if resolved_lease is None:
        raise HTTPException(403, "Sandbox not authorized")

    bind_cwd = _resolve_existing_sandbox_bind_cwd(
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

    # @@@existing-sandbox-binding-boundary - lower lease identity is only the
    # mechanism used by sandbox.manager to attach a terminal; router control
    # flow should stay sandbox/workspace-shaped after this point.
    return _ExistingSandboxThreadBinding(
        sandbox_id=sandbox_id,
        sandbox_type=str(bound_lease["provider_name"] or ""),
        workspace_path=bind_cwd or bound_cwd,
        thread_cwd=bound_cwd,
    )


def _resolve_owned_recipe_snapshot(
    app: Any,
    owner_user_id: str,
    sandbox_type: str,
    recipe_id: str | None,
) -> dict[str, Any]:
    resolved_recipe_id = str(recipe_id or default_recipe_id(sandbox_type)).strip()
    if not resolved_recipe_id:
        raise HTTPException(400, "Recipe id is required")

    recipe_repo = getattr(app.state, "recipe_repo", None)
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


def _create_owned_thread(
    app: Any,
    owner_user_id: str,
    payload: CreateThreadRequest,
    *,
    is_main: bool,
) -> dict[str, Any]:
    import time

    sandbox_type = payload.sandbox or "local"
    agent_user_id = payload.agent_user_id
    agent_user = app.state.user_repo.get_by_id(agent_user_id)
    if not agent_user or agent_user.owner_user_id != owner_user_id:
        raise HTTPException(403, "Not authorized")

    # @@@non-atomic-create - these 3 steps (seq++, thread) are not atomic.
    # @@@user-owned-thread-seq - thread ids are now allocated from the unified
    # user identity root, so create-path sequencing must fail loudly through
    # user_repo instead of inventing a second agent identity source.
    seq = app.state.user_repo.increment_thread_seq(agent_user_id)
    new_thread_id = f"{agent_user_id}-{seq}"
    has_main = app.state.thread_repo.get_default_thread(agent_user_id) is not None
    resolved_is_main = is_main or not has_main
    branch_index = 0 if resolved_is_main else app.state.thread_repo.get_next_branch_index(agent_user_id)

    existing_binding: _ExistingSandboxThreadBinding | None = None
    if payload.existing_sandbox_id:
        existing_binding = _bind_existing_sandbox_for_thread(
            app,
            owner_user_id,
            new_thread_id,
            payload.existing_sandbox_id,
            payload.cwd,
        )
        sandbox_type = existing_binding.sandbox_type or sandbox_type
    selected_recipe = None
    if existing_binding is None:
        selected_recipe = _resolve_owned_recipe_snapshot(app, owner_user_id, sandbox_type, payload.sandbox_template_id)

    if existing_binding is not None:
        current_workspace_id = _materialize_workspace_for_sandbox(
            app.state.workspace_repo,
            sandbox_id=existing_binding.sandbox_id,
            owner_user_id=owner_user_id,
            workspace_path=existing_binding.workspace_path,
        )
    else:
        # @@@create-write-workspace-first - replay-13 requires supported create paths
        # to persist the concrete workspace row at thread-row creation time,
        # not bind runtime truth after a workspace-blind row already exists.
        current_workspace_id = _create_thread_sandbox_resources(
            new_thread_id,
            sandbox_type,
            selected_recipe,
            payload.cwd,
            workspace_repo=app.state.workspace_repo,
            owner_user_id=owner_user_id,
        )

    app.state.thread_repo.create(
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

    # Set thread state
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
        "sidebar_label": _sidebar_label(is_main=resolved_is_main, branch_index=branch_index),
        "avatar_url": avatar_url(agent_user_id, bool(agent_user.avatar)),
        "is_main": resolved_is_main,
    }


@router.post("", response_model=None)
async def create_thread(
    payload: CreateThreadRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any] | JSONResponse:
    """Create a new child thread for an agent user."""
    provider_error = _validate_sandbox_provider_gate(app, user_id, payload)
    if provider_error is not None:
        return provider_error
    # Validate bind_mounts capability before creating thread
    sandbox_type = payload.sandbox or "local"
    requested_mounts = payload.bind_mounts or []
    capability_error = await _validate_mount_capability_gate(sandbox_type, requested_mounts)
    if capability_error is not None:
        return capability_error
    quota_error = _validate_sandbox_quota_gate(app, user_id, payload)
    if quota_error is not None:
        return quota_error

    result = _create_owned_thread(app, user_id, payload, is_main=False)
    _invalidate_resource_overview_cache()

    return result


@router.post("/main")
async def resolve_main_thread(
    payload: ResolveMainThreadRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Return the default representative thread for an agent user."""
    agent_user_id = payload.agent_user_id
    agent_user = _find_owned_agent(app, agent_user_id, user_id)
    if agent_user is None:
        # Return null instead of 403 — agent user may not exist yet (stale client state)
        # or belong to another user (harmless to reveal "no thread")
        return {
            "agent_user_id": agent_user_id,
            "default_thread_id": None,
            "thread": None,
        }

    default_thread = app.state.thread_repo.get_default_thread(agent_user_id)
    if default_thread is None:
        return {
            "agent_user_id": agent_user_id,
            "default_thread_id": None,
            "thread": None,
        }
    try:
        return {
            "agent_user_id": agent_user_id,
            "default_thread_id": default_thread["id"],
            "thread": _thread_payload(app, default_thread["id"], default_thread.get("sandbox_type", "local")),
        }
    except HTTPException as exc:
        # @@@orphan-default-thread - stale bootstrap data can leave the agent user pointing at a thread whose
        # user rows are gone. Treat that as "no resolvable default thread" instead of surfacing a 500.
        if exc.status_code == 500 and "missing agent user" in str(exc.detail):
            logger.warning(
                "resolve_main_thread ignored orphaned default thread %s for agent user %s",
                default_thread["id"],
                agent_user_id,
            )
            return {
                "agent_user_id": agent_user_id,
                "default_thread_id": None,
                "thread": None,
            }
        raise


@router.get("/default-config")
async def get_default_thread_config(
    agent_user_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    config = await asyncio.to_thread(_resolve_default_config_for_owned_agent, app, user_id, agent_user_id)
    return config


def build_owner_thread_workbench(app: Any, user_id: str) -> dict[str, Any]:
    raw = app.state.thread_repo.list_by_owner_user_id(user_id)
    return build_owner_thread_workbench_from_rows(app, raw)


def build_owner_thread_workbench_from_rows(app: Any, raw: list[dict[str, Any]]) -> dict[str, Any]:
    from core.runtime.middleware.monitor import AgentState

    pool = app.state.agent_pool
    runtime_states = summarize_owner_thread_runtime(app, [str(thread.get("id") or "") for thread in raw if thread.get("id")])
    visible_threads = []
    for t in raw:
        tid = t["id"]
        runtime_state = runtime_states.get(tid) or converge_owner_thread_runtime(app, tid)
        if runtime_state in {"missing", "purged"}:
            continue
        if _is_internal_child_thread(tid):
            continue
        visible_threads.append(t)

    threads = []
    for t in canonical_owner_threads(visible_threads):
        tid = t["id"]
        sandbox_type = t.get("sandbox_type", "local")
        running = False
        agent = pool.get(f"{tid}:{sandbox_type}")
        if agent and hasattr(agent, "runtime"):
            running = agent.runtime.current_state == AgentState.ACTIVE
        last_active = app.state.thread_last_active.get(tid)
        from datetime import datetime

        updated_at = datetime.fromtimestamp(last_active, tz=UTC).isoformat() if last_active else None

        threads.append(
            {
                "thread_id": tid,
                "sandbox": t.get("sandbox_type", "local"),
                "agent_name": t.get("agent_name"),
                "agent_user_id": t.get("agent_user_id"),
                "branch_index": t.get("branch_index"),
                "sidebar_label": _sidebar_label(
                    is_main=bool(t.get("is_main", False)),
                    branch_index=int(t.get("branch_index", 0)),
                ),
                "avatar_url": avatar_url(t.get("agent_user_id"), bool(t.get("agent_avatar"))),
                "is_main": t.get("is_main", False),
                "running": running,
                "updated_at": updated_at,
            }
        )
    return {"threads": threads}


@router.get("")
async def list_threads(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """List threads owned by the current user."""
    raw = await list_owner_thread_rows_for_auth_burst(app, user_id)
    return await asyncio.to_thread(build_owner_thread_workbench_from_rows, app, raw)


@router.get("/{thread_id}")
async def get_thread_messages(
    thread_id: str,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Get display entries and sandbox info for a thread.

    @@@display-builder — returns pre-computed ChatEntry[] from DisplayBuilder.
    Hot path: return in-memory state.  Cold path: rebuild from checkpoint.
    """
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    display_builder = app.state.display_builder
    entries = await _get_thread_display_entries(app, thread_id)
    sandbox_info = get_sandbox_info(app, thread_id, sandbox_type)
    return {
        "thread_id": thread_id,
        "entries": entries,
        "display_seq": display_builder.get_display_seq(thread_id),
        "sandbox": sandbox_info,
    }


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Delete a thread and its resources."""
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"

    lock = await get_thread_lock(app, thread_id)
    async with lock:
        agent = app.state.agent_pool.get(pool_key)
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            raise HTTPException(status_code=409, detail="Cannot delete thread while run is in progress")
        # Clear per-thread handlers before removing agent
        if agent and hasattr(agent, "runtime") and agent.runtime:
            agent.runtime.unbind_thread()
        # Unregister wake handler
        app.state.queue_manager.unregister_wake(thread_id)
        await asyncio.to_thread(destroy_thread_resources_sync, thread_id, sandbox_type, app.state.agent_pool)
        await asyncio.to_thread(delete_thread_in_db, thread_id)
        # Also delete from threads table.
        app.state.thread_repo.delete(thread_id)

    # Clean up thread-specific state
    app.state.thread_sandbox.pop(thread_id, None)
    app.state.thread_cwd.pop(thread_id, None)
    app.state.thread_event_buffers.pop(thread_id, None)
    app.state.queue_manager.clear_all(thread_id)

    # Remove per-thread Agent from pool
    app.state.agent_pool.pop(pool_key, None)
    _invalidate_resource_overview_cache()

    return {"ok": True, "thread_id": thread_id}


@router.post("/{thread_id}/messages")
async def send_message(
    thread_id: str,
    payload: SendMessageRequest,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Send a message to agent — thin wrapper around route_message_to_brain."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    from backend.web.services.agent_pool import get_or_create_agent, resolve_thread_sandbox
    from backend.web.services.message_routing import route_message_to_brain

    message = payload.message
    # @@@attachment-wire - sync files to sandbox and prepend paths
    if payload.attachments:
        sandbox_type = resolve_thread_sandbox(app, thread_id)
        agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
        message, _ = await _prepare_attachment_message(
            thread_id,
            sandbox_type,
            message,
            payload.attachments,
            agent=agent,
        )

    return await route_message_to_brain(
        app,
        thread_id,
        message,
        source="owner",
        enable_trajectory=payload.enable_trajectory,
        attachments=payload.attachments or None,
    )


@router.post("/{thread_id}/queue")
async def queue_message(
    thread_id: str,
    payload: SendMessageRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Enqueue a followup message. Will be consumed when agent reaches IDLE."""
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    app.state.queue_manager.enqueue(payload.message, thread_id, notification_type="steer")
    return {"status": "queued", "thread_id": thread_id}


@router.get("/{thread_id}/queue")
async def get_queue(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """List pending followup messages in the queue."""
    messages = app.state.queue_manager.list_queue(thread_id)
    return {"messages": messages, "thread_id": thread_id}


@router.get("/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    limit: int = 20,
    truncate: int = 300,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Compact conversation history for debugging — no raw LangChain noise.

    Args:
        limit: Max messages to return, from the end (default 20)
        truncate: Truncate content to this many chars (default 300, 0 = no limit)
    """
    from backend.web.services.thread_history_service import get_thread_history_payload

    return await get_thread_history_payload(
        app=app,
        thread_id=thread_id,
        limit=limit,
        truncate=truncate,
    )


@router.get("/{thread_id}/permissions")
async def get_thread_permissions(
    thread_id: str,
    thread_lock: Annotated[asyncio.Lock, Depends(get_thread_lock)],
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    # @@@permission-state-lock - owner polling and resolve can race on idle
    # threads. Serialize the lightweight /permissions read with resolve/persist
    # so stale checkpoint hydration cannot resurrect an already-resolved request.
    async with thread_lock:
        await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
        rule_state = agent.get_thread_permission_rules(thread_id)
        return {
            "thread_id": thread_id,
            "requests": agent.get_pending_permission_requests(thread_id),
            "session_rules": rule_state["rules"],
            "managed_only": rule_state["managed_only"],
        }


@router.post("/{thread_id}/permissions/{request_id}/resolve")
async def resolve_thread_permission_request(
    thread_id: str,
    request_id: str,
    payload: ResolvePermissionRequest,
    thread_lock: Annotated[asyncio.Lock, Depends(get_thread_lock)],
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    async with thread_lock:
        await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
        pending_requests = {
            item.get("request_id"): item
            for item in agent.get_pending_permission_requests(thread_id)
            if isinstance(item, dict) and item.get("request_id")
        }
        pending_request = pending_requests.get(request_id)
        is_ask_user_question = bool(pending_request and pending_request.get("tool_name") == "AskUserQuestion")
        answers = _serialize_permission_answers(payload)
        if is_ask_user_question and payload.decision == "allow" and not answers:
            raise HTTPException(status_code=400, detail="AskUserQuestion answers are required when approving the request")
        ok = agent.resolve_permission_request(
            request_id,
            decision=payload.decision,
            message=payload.message,
            answers=answers,
            annotations=getattr(payload, "annotations", None),
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Permission request not found")
        await agent.agent.apersist_state(thread_id)
        if is_ask_user_question and payload.decision == "allow" and answers is not None:
            # @@@ask-user-lifecycle - the owner's answer is about to become a
            # real follow-up user message. Clear the old request before that
            # run starts so checkpoint replay cannot resurrect the popup.
            agent.drop_permission_request(request_id)
            await agent.agent.apersist_state(thread_id)

    followup: dict[str, Any] | None = None
    if is_ask_user_question and payload.decision == "allow" and pending_request is not None and answers is not None:
        from backend.web.services.message_routing import route_message_to_brain

        answered_payload = _build_ask_user_question_answered_payload(
            pending_request,
            answers=answers,
            annotations=getattr(payload, "annotations", None),
        )

        followup = await route_message_to_brain(
            app,
            thread_id,
            _format_ask_user_question_followup(
                pending_request,
                answers=answers,
                annotations=getattr(payload, "annotations", None),
            ),
            source="internal",
            message_metadata={"ask_user_question_answered": answered_payload},
        )

    response = {"ok": True, "thread_id": thread_id, "request_id": request_id}
    if followup is not None:
        response["followup"] = followup
    return response


@router.post("/{thread_id}/permissions/rules")
async def add_thread_permission_rule(
    thread_id: str,
    payload: ThreadPermissionRuleRequest,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
    rule_state = agent.get_thread_permission_rules(thread_id)
    if rule_state["managed_only"]:
        raise HTTPException(status_code=409, detail="Managed permission rules only; session overrides are disabled")
    ok = agent.add_thread_permission_rule(
        thread_id,
        behavior=payload.behavior,
        tool_name=payload.tool_name,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Could not add thread permission rule")
    await agent.agent.apersist_state(thread_id)
    updated = agent.get_thread_permission_rules(thread_id)
    return {
        "ok": True,
        "thread_id": thread_id,
        "scope": "session",
        "rules": updated["rules"],
        "managed_only": updated["managed_only"],
    }


@router.delete("/{thread_id}/permissions/rules/{behavior}/{tool_name}")
async def delete_thread_permission_rule(
    thread_id: str,
    behavior: str,
    tool_name: str,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    agent: Annotated[Any, Depends(get_thread_agent)] = None,
) -> dict[str, Any]:
    await agent.agent.aget_state({"configurable": {"thread_id": thread_id}})
    ok = agent.remove_thread_permission_rule(
        thread_id,
        behavior=behavior,
        tool_name=tool_name,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Thread permission rule not found")
    await agent.agent.apersist_state(thread_id)
    updated = agent.get_thread_permission_rules(thread_id)
    return {
        "ok": True,
        "thread_id": thread_id,
        "scope": "session",
        "rules": updated["rules"],
        "managed_only": updated["managed_only"],
    }


@router.get("/{thread_id}/runtime")
async def get_thread_runtime(
    thread_id: str,
    stream: bool = False,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    """Get runtime status for a thread."""
    from backend.web.services.event_store import get_last_seq, get_latest_run_id, get_run_start_seq

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    agent = await get_or_create_agent(app, sandbox_type, thread_id=thread_id)
    if not hasattr(agent, "runtime"):
        raise HTTPException(status_code=404, detail="Agent has no runtime monitor")

    last_seq = await get_last_seq(thread_id)
    thread_data = app.state.thread_repo.get_by_id(thread_id)
    model = thread_data["model"] if thread_data and thread_data.get("model") else None

    status = agent.runtime.get_status_dict()
    if model is not None:
        status["model"] = model
    status["last_seq"] = last_seq
    if status.get("state", {}).get("state") == "active":
        run_id = await get_latest_run_id(thread_id)
        if run_id:
            status["run_start_seq"] = await get_run_start_seq(thread_id, run_id)
    return status


# Sandbox status endpoint
@router.get("/{thread_id}/sandbox")
async def get_thread_sandbox_status(
    thread_id: str,
    user_id: Annotated[str | None, Depends(verify_thread_row_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any] | None:
    """Get sandbox status for a thread."""
    return await get_sandbox_status_from_repos(
        app.state.thread_repo,
        app.state.workspace_repo,
        app.state.sandbox_repo,
        app.state.lease_repo,
        thread_id,
    )


# SSE response headers: disable proxy buffering for real-time streaming
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# Persistent thread event stream (replaces /runs/events + /activity/events)
# ---------------------------------------------------------------------------


@router.get("/{thread_id}/events")
async def stream_thread_events(
    thread_id: str,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    after: int = 0,
    app: Annotated[Any, Depends(get_app)] = None,
) -> EventSourceResponse:
    """Persistent SSE event stream over the standard Authorization header."""
    thread = app.state.thread_repo.get_by_id(thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    agent_user = app.state.user_repo.get_by_id(thread["agent_user_id"])
    if not agent_user or agent_user.owner_user_id != user_id:
        raise HTTPException(403, "Not authorized")

    last_id = request.headers.get("Last-Event-ID")
    if last_id:
        try:
            after = max(after, int(last_id))
        except ValueError:
            pass

    thread_buf = app.state.thread_event_buffers.get(thread_id)

    if isinstance(thread_buf, ThreadEventBuffer):
        return EventSourceResponse(
            observe_thread_events(thread_buf, after=after),
            headers=SSE_HEADERS,
        )

    # No buffer yet — create one and optionally replay from SQLite
    thread_buf = get_or_create_thread_buffer(app, thread_id)

    if after > 0:
        # Replay from SQLite for reconnection
        from backend.web.services.event_store import get_latest_run_id, read_events_after

        run_id = await get_latest_run_id(thread_id)
        if run_id:
            events = await read_events_after(thread_id, run_id, after)
            for ev in events:
                seq = ev.get("seq", 0)
                data_str = ev.get("data", "{}")
                try:
                    data = json.loads(data_str) if isinstance(data_str, str) else data_str
                except (json.JSONDecodeError, TypeError):
                    data = {}
                if isinstance(data, dict):
                    data["_seq"] = seq
                    data_str = json.dumps(data, ensure_ascii=False)
                await thread_buf.put({"event": ev["event"], "data": data_str})

    return EventSourceResponse(
        observe_thread_events(thread_buf, after=after),
        headers=SSE_HEADERS,
    )


@router.post("/{thread_id}/runs/cancel")
async def cancel_run(
    thread_id: str,
    user_id: Annotated[str | None, Depends(verify_thread_owner)] = None,
    app: Annotated[Any, Depends(get_app)] = None,
):
    """Cancel an active run for the given thread."""
    task = app.state.thread_tasks.get(thread_id)
    if not task:
        return {"ok": False, "message": "No active run found"}
    task.cancel()
    return {"ok": True, "message": "Run cancellation requested"}


# ---------------------------------------------------------------------------
# Background Run API - exposes agent._background_runs to the frontend
# ---------------------------------------------------------------------------


def _get_background_runs(app: Any, thread_id: str) -> dict:
    agent = _get_agent_for_thread(app, thread_id)
    return getattr(agent, "_background_runs", {}) if agent else {}


def _background_run_type(run: Any) -> str:
    return "bash" if run.__class__.__name__ == "_BashBackgroundRun" else "agent"


def _serialize_background_run(task_id: str, run: Any, *, include_result: bool) -> dict[str, Any]:
    run_type = _background_run_type(run)
    result_text = _background_run_result(run) if include_result and run.is_done else None
    if _background_run_cancelled(run):
        status = "cancelled"
    else:
        status = "completed" if run.is_done else "running"
    payload = {
        "task_id": task_id,
        "task_type": run_type,
        "status": status,
        "command_line": getattr(run, "command", None) if run_type == "bash" else None,
    }
    if include_result:
        payload["result"] = result_text
        payload["text"] = result_text
        return payload
    payload["description"] = getattr(run, "description", None)
    payload["exit_code"] = getattr(getattr(run, "_cmd", None), "exit_code", None) if run_type == "bash" else None
    payload["error"] = None
    return payload


async def _get_display_task_map(app: Any, thread_id: str) -> dict[str, dict[str, Any]]:
    return _collect_display_subagent_tasks(await _get_thread_display_entries(app, thread_id))


@router.get("/{thread_id}/tasks")
async def list_tasks(
    thread_id: str,
    request: Request,
) -> list[dict]:
    """列出线程的所有后台 run（bash + agent）"""
    runs = _get_background_runs(request.app, thread_id)
    result = [_serialize_background_run(task_id, run, include_result=False) for task_id, run in runs.items()]
    seen_task_ids = set(runs)
    for task_id, task in (await _get_display_task_map(request.app, thread_id)).items():
        if task_id in seen_task_ids:
            continue
        result.append(
            {
                "task_id": task["task_id"],
                "task_type": task["task_type"],
                "status": task["status"],
                "command_line": task["command_line"],
                "description": task["description"],
                "exit_code": task["exit_code"],
                "error": task["error"],
            }
        )
    return result


@router.get("/{thread_id}/tasks/{task_id}")
async def get_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """获取 background run 详情（含完整输出）"""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        task = (await _get_display_task_map(request.app, thread_id)).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "status": task["status"],
            "command_line": task["command_line"],
            "result": task["result"],
            "text": task["text"],
        }

    return _serialize_background_run(task_id, run, include_result=True)


@router.post("/{thread_id}/tasks/{task_id}/cancel")
async def cancel_task(
    thread_id: str,
    task_id: str,
    request: Request,
) -> dict:
    """取消 background run（bash + agent 统一）"""
    runs = _get_background_runs(request.app, thread_id)
    run = runs.get(task_id)
    if not run:
        task = (await _get_display_task_map(request.app, thread_id)).get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] != "running":
            raise HTTPException(status_code=400, detail="Task is not running")
        thread_task = request.app.state.thread_tasks.get(thread_id)
        if thread_task is None or thread_task.done():
            raise HTTPException(status_code=400, detail="Task is not independently cancellable")
        thread_task.cancel()
        return {"ok": True, "message": "Run cancellation requested", "task_id": task_id}
    if run.is_done:
        raise HTTPException(status_code=400, detail="Task is not running")

    await request_background_run_stop(run)

    # Emit task_done SSE and notify main agent once cancellation completes
    asyncio.create_task(_notify_task_cancelled(request.app, thread_id, task_id, run))

    return {"success": True}


async def _notify_task_cancelled(app: Any, thread_id: str, task_id: str, run: Any) -> None:
    """Wait for run to finish, then emit task_done SSE and enqueue cancellation notice."""
    # Wait up to 5s for the task to actually stop
    for _ in range(50):
        if run.is_done:
            break
        await asyncio.sleep(0.1)

    if not run.is_done:
        logger.warning("Cancelled task %s never reached a terminal state; skipping cancellation surface", task_id)
        return

    # Emit task_done so the frontend indicator updates
    try:
        from backend.web.event_bus import get_event_bus

        event_bus = get_event_bus()
        emit_fn = event_bus.make_emitter(
            thread_id=thread_id,
            agent_id=task_id,
            agent_name=f"cancel-{task_id[:8]}",
        )
        emission = emit_fn(
            {
                "event": "task_done",
                "data": json.dumps(
                    {
                        "task_id": task_id,
                        "background": True,
                        "cancelled": True,
                    },
                    ensure_ascii=False,
                ),
            }
        )
        if asyncio.iscoroutine(emission):
            await emission
    except Exception:
        logger.warning("Failed to emit task_done for cancelled task %s", task_id, exc_info=True)

    # Notify the main agent so it knows the user cancelled this task
    try:
        agent = _get_agent_for_thread(app, thread_id)
        qm = getattr(agent, "queue_manager", None) if agent else None
        if qm:
            description = getattr(run, "description", "") or ""
            command = getattr(run, "command", "") or ""
            label = description or command[:80] or f"Task {task_id}"
            notification = (
                f'<CommandNotification task_id="{task_id}" status="cancelled">'
                f"<Status>cancelled</Status>"
                f"<Description>{label}</Description>"
                + (f"<CommandLine>{command[:200]}</CommandLine>" if command else "")
                + "</CommandNotification>"
            )
            qm.enqueue(notification, thread_id, notification_type="command")
    except Exception:
        logger.warning("Failed to enqueue cancellation notice for task %s", task_id, exc_info=True)
