"""Primary owner-facing thread HTTP routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from backend.sandboxes.thread_resources import destroy_thread_resources_sync
from backend.threads.activity_pool_service import get_or_create_agent
from backend.threads.api.http.owner_support import (
    build_ask_user_question_answered_payload,
    create_owned_thread,
    find_owned_agent,
    format_ask_user_question_followup,
    invalidate_resource_overview_cache,
    list_owned_threads_payload,
    prepare_attachment_message,
    resolve_default_config_for_owned_agent,
    serialize_permission_answers,
    thread_messages_payload,
    thread_payload,
    thread_sandbox_info,
    validate_mount_capability_gate,
    validate_sandbox_provider_gate,
    validate_sandbox_quota_gate,
)
from backend.threads.api.http.runtime_support import get_agent_for_thread, get_thread_display_entries
from backend.threads.chat_adapters.port import get_thread_input_transport
from backend.threads.convergence import delete_thread_in_db
from backend.threads.history import (
    build_thread_history_transport,
    get_thread_history_payload,
    get_thread_history_payload_from_display_entries,
)
from backend.threads.runtime_access import get_optional_messaging_service
from backend.threads.sandbox_resolution import resolve_thread_sandbox
from backend.web.core.dependencies import (
    _get_thread_repo,
    get_app,
    get_current_user_id,
    get_thread_agent,
    get_thread_lock,
    verify_thread_owner,
)
from backend.web.models.requests import (
    CreateThreadRequest,
    ResolveMainThreadRequest,
    ResolvePermissionRequest,
    SendMessageRequest,
    ThreadPermissionRuleRequest,
)
from core.runtime.middleware.monitor import AgentState
from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope
from sandbox.thread_context import set_current_thread_id

router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.post("", response_model=None)
async def create_thread(
    payload: CreateThreadRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    provider_error = validate_sandbox_provider_gate(app, user_id, payload)
    if provider_error is not None:
        return provider_error

    sandbox_type = payload.sandbox or "local"
    requested_mounts = payload.bind_mounts or []
    capability_error = await validate_mount_capability_gate(sandbox_type, requested_mounts)
    if capability_error is not None:
        return capability_error

    quota_error = validate_sandbox_quota_gate(app, user_id, payload)
    if quota_error is not None:
        return quota_error

    result = create_owned_thread(app, user_id, payload, is_main=False)
    invalidate_resource_overview_cache()
    return result


@router.post("/main")
async def resolve_main_thread(
    payload: ResolveMainThreadRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    agent_user_id = payload.agent_user_id
    agent_user = find_owned_agent(app, agent_user_id, user_id)
    if agent_user is None:
        return {
            "agent_user_id": agent_user_id,
            "default_thread_id": None,
            "thread": None,
        }

    default_thread = _get_thread_repo(app).get_default_thread(agent_user_id)
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
            "thread": thread_payload(app, default_thread["id"], default_thread.get("sandbox_type", "local")),
        }
    except HTTPException as exc:
        if exc.status_code == 500 and "missing agent user" in str(exc.detail):
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
    return await asyncio.to_thread(resolve_default_config_for_owned_agent, app, user_id, agent_user_id)


@router.get("")
async def list_threads(
    user_id: Annotated[str, Depends(get_current_user_id)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    return await list_owned_threads_payload(app, user_id)


@router.get("/{thread_id}")
async def get_thread_messages(
    thread_id: str,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    from backend.threads.sandbox_resolution import resolve_thread_sandbox

    sandbox_type = resolve_thread_sandbox(app, thread_id)
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    display_builder = getattr(runtime_state, "display_builder", None)
    if display_builder is None:
        raise RuntimeError("display_builder is required for thread runtime surface")
    entries = await get_thread_display_entries(app, thread_id)
    sandbox_info = thread_sandbox_info(app, thread_id, sandbox_type)
    return thread_messages_payload(
        thread_id=thread_id,
        entries=entries,
        display_builder=display_builder,
        sandbox_info=sandbox_info,
    )


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    sandbox_type = resolve_thread_sandbox(app, thread_id)
    pool_key = f"{thread_id}:{sandbox_type}"

    lock = await get_thread_lock(app, thread_id)
    async with lock:
        agent = app.state.agent_pool.get(pool_key)
        if agent and hasattr(agent, "runtime") and agent.runtime.current_state == AgentState.ACTIVE:
            raise HTTPException(status_code=409, detail="Cannot delete thread while run is in progress")
        if agent and hasattr(agent, "runtime") and agent.runtime:
            agent.runtime.unbind_thread()
        app.state.queue_manager.unregister_wake(thread_id)
        await asyncio.to_thread(destroy_thread_resources_sync, thread_id, sandbox_type, app.state.agent_pool)
        await asyncio.to_thread(delete_thread_in_db, thread_id)
        _get_thread_repo(app).delete(thread_id)

    app.state.thread_sandbox.pop(thread_id, None)
    app.state.thread_cwd.pop(thread_id, None)
    app.state.thread_event_buffers.pop(thread_id, None)
    app.state.queue_manager.clear_all(thread_id)
    app.state.agent_pool.pop(pool_key, None)
    invalidate_resource_overview_cache()

    return {"ok": True, "thread_id": thread_id}


@router.post("/{thread_id}/messages")
async def send_message(
    thread_id: str,
    payload: SendMessageRequest,
    user_id: Annotated[str, Depends(verify_thread_owner)],
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    from protocols.agent_runtime import AgentRuntimeActor, AgentRuntimeMessage, AgentThreadInputEnvelope

    message = payload.message
    if payload.attachments:
        sandbox_type = resolve_thread_sandbox(app, thread_id)
        agent = await get_or_create_agent(
            app,
            sandbox_type,
            thread_id=thread_id,
            messaging_service=get_optional_messaging_service(app),
        )
        message, _ = await prepare_attachment_message(
            thread_id,
            sandbox_type,
            message,
            payload.attachments,
            agent=agent,
        )

    result = await get_thread_input_transport(app).dispatch_thread_input(
        AgentThreadInputEnvelope(
            thread_id=thread_id,
            sender=AgentRuntimeActor(user_id=user_id, user_type="human", display_name="Owner", source="owner"),
            message=AgentRuntimeMessage(content=message, attachments=payload.attachments or None),
            enable_trajectory=payload.enable_trajectory,
        )
    )
    return result.to_response()


@router.post("/{thread_id}/queue")
async def queue_message(
    thread_id: str,
    payload: SendMessageRequest,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    app.state.queue_manager.enqueue(payload.message, thread_id, notification_type="steer")
    return {"status": "queued", "thread_id": thread_id}


@router.get("/{thread_id}/queue")
async def get_queue(
    thread_id: str,
    app: Annotated[Any, Depends(get_app)] = None,
) -> dict[str, Any]:
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
    agent = get_agent_for_thread(app, thread_id)
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    display_builder = getattr(runtime_state, "display_builder", None)
    if agent is not None and display_builder is not None:
        entries = display_builder.get_entries(thread_id)
        if entries is not None:
            return get_thread_history_payload_from_display_entries(
                thread_id=thread_id,
                entries=entries,
                limit=limit,
                truncate=truncate,
            )

    async def _load_live_messages(current_thread_id: str) -> list[Any] | None:
        agent_pool = getattr(app.state, "agent_pool", None)
        if not isinstance(agent_pool, dict):
            raise RuntimeError("agent_pool is required for thread history reads")
        if not agent_pool:
            return None

        agent = get_agent_for_thread(app, current_thread_id)
        if agent is None:
            return None

        state = await agent.agent.aget_state({"configurable": {"thread_id": current_thread_id}})
        values = getattr(state, "values", {}) if state else {}
        messages = values.get("messages", []) if isinstance(values, dict) else []
        return list(messages)

    async def _load_checkpoint_messages(current_thread_id: str) -> list[Any]:
        runtime_state = getattr(app.state, "threads_runtime_state", None)
        checkpoint_store = getattr(runtime_state, "checkpoint_store", None)
        if checkpoint_store is None:
            raise RuntimeError("thread_checkpoint_store is required for cold thread history reads")
        checkpoint_state = await checkpoint_store.load(current_thread_id)
        return list(checkpoint_state.messages) if checkpoint_state is not None else []

    history_transport = build_thread_history_transport(
        load_live_messages=_load_live_messages,
        load_checkpoint_messages=_load_checkpoint_messages,
    )
    set_current_thread_id(thread_id)
    return await get_thread_history_payload(
        thread_id=thread_id,
        history_transport=history_transport,
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
        answers = serialize_permission_answers(payload)
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
            agent.drop_permission_request(request_id)
            await agent.agent.apersist_state(thread_id)

    followup: dict[str, Any] | None = None
    if is_ask_user_question and payload.decision == "allow" and pending_request is not None and answers is not None:
        answered_payload = build_ask_user_question_answered_payload(
            pending_request,
            answers=answers,
            annotations=getattr(payload, "annotations", None),
        )

        followup_result = await get_thread_input_transport(app).dispatch_thread_input(
            AgentThreadInputEnvelope(
                thread_id=thread_id,
                sender=AgentRuntimeActor(
                    user_id=user_id or "internal",
                    user_type="system",
                    display_name="Internal",
                    source="internal",
                ),
                message=AgentRuntimeMessage(
                    content=format_ask_user_question_followup(
                        pending_request,
                        answers=answers,
                        annotations=getattr(payload, "annotations", None),
                    ),
                    metadata={"ask_user_question_answered": answered_payload},
                ),
            ),
        )
        followup = followup_result.to_response()

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
