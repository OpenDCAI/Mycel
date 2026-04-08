from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.web.models.requests import CreateThreadRequest, ResolvePermissionRequest, SendMessageRequest, ThreadPermissionRuleRequest
from backend.web.routers import threads as threads_router
from core.runtime.loop import QueryLoop
from core.runtime.middleware.monitor import AgentState
from core.runtime.registry import ToolRegistry
from core.runtime.state import AppState, BootstrapConfig, ToolPermissionState
from storage.contracts import UserRow, UserType


class _FakeUserRepo:
    def __init__(self) -> None:
        self._users = {
            "member-1": UserRow(
                id="member-1",
                type=UserType.AGENT,
                display_name="Toad",
                owner_user_id="owner-1",
                agent_config_id="cfg-1",
                avatar="avatars/member-1.png",
                created_at=1.0,
            )
        }
        self._seq = {"member-1": 0}

    def get_by_id(self, user_id: str):
        return self._users.get(user_id)

    def increment_thread_seq(self, user_id: str) -> int:
        self._seq[user_id] += 1
        return self._seq[user_id]


class _FakeThreadRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def get_by_id(self, thread_id: str):
        row = self.rows.get(thread_id)
        if row is None:
            return None
        return {"id": thread_id, **row}

    def get_default_thread(self, agent_user_id: str):
        for row in self.rows.values():
            if row["agent_user_id"] == agent_user_id and row["is_main"]:
                return {"id": row["thread_id"], **row}
        return None

    def get_next_branch_index(self, agent_user_id: str) -> int:
        indices = [row["branch_index"] for row in self.rows.values() if row["agent_user_id"] == agent_user_id]
        return max(indices, default=0) + 1

    def create(self, **kwargs):
        self.rows[kwargs["thread_id"]] = dict(kwargs)


class _FakeAuthService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def verify_token(self, token: str) -> dict:
        self.tokens.append(token)
        return {"user_id": "owner-1"}


@pytest.mark.asyncio
async def test_send_message_passes_enable_trajectory_to_message_routing() -> None:
    route_message = AsyncMock(return_value={"status": "started", "thread_id": "thread-1"})

    with patch("backend.web.services.message_routing.route_message_to_brain", route_message):
        result = await threads_router.send_message(
            "thread-1",
            SendMessageRequest(message="hello", enable_trajectory=True),
            user_id="owner-1",
            app=SimpleNamespace(),
        )

    assert result == {"status": "started", "thread_id": "thread-1"}
    assert route_message.await_args.kwargs["enable_trajectory"] is True


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/threads/thread-1/events",
        "headers": raw_headers,
    }
    return Request(scope)


def _decode_json_response(response: threads_router.JSONResponse) -> dict[str, Any]:
    body = response.body
    payload = body.tobytes() if isinstance(body, memoryview) else body
    return cast(dict[str, Any], json.loads(payload.decode()))


def _require_thread_result(result: dict[str, Any] | threads_router.JSONResponse) -> dict[str, Any]:
    assert not isinstance(result, threads_router.JSONResponse)
    return result


def _require_app_state(loop: QueryLoop) -> AppState:
    app_state = loop._app_state
    assert app_state is not None
    return app_state


def _require_await_kwargs(mock: AsyncMock) -> dict[str, Any]:
    await_args = mock.await_args
    assert await_args is not None
    return cast(dict[str, Any], await_args.kwargs)


def _require_await_args(mock: AsyncMock) -> tuple[Any, ...]:
    await_args = mock.await_args
    assert await_args is not None
    return cast(tuple[Any, ...], await_args.args)


class _FakePermissionAgent:
    def __init__(self) -> None:
        self.pending = [
            {
                "request_id": "perm-1",
                "thread_id": "thread-1",
                "tool_name": "Write",
                "args": {"path": "/tmp/demo.txt"},
                "message": "needs approval",
            }
        ]
        self.session_rules = {
            "allow": ["Read"],
            "deny": ["Bash"],
            "ask": ["Edit"],
        }
        self.managed_only = False
        self.resolve_calls: list[tuple[str, str, str | None, list[dict] | None, dict | None]] = []
        self.rule_add_calls: list[tuple[str, str]] = []
        self.rule_remove_calls: list[tuple[str, str]] = []
        self.agent = SimpleNamespace(
            aget_state=AsyncMock(return_value=SimpleNamespace(values={})),
            apersist_state=AsyncMock(),
        )

    def get_pending_permission_requests(self, thread_id: str | None = None):
        if thread_id is None:
            return list(self.pending)
        return [item for item in self.pending if item["thread_id"] == thread_id]

    def resolve_permission_request(
        self,
        request_id: str,
        *,
        decision: str,
        message: str | None = None,
        answers: list[dict] | None = None,
        annotations: dict | None = None,
    ) -> bool:
        self.resolve_calls.append((request_id, decision, message, answers, annotations))
        if request_id != "perm-1":
            return False
        self.pending = []
        return True

    def drop_permission_request(self, request_id: str) -> bool:
        before = len(self.pending)
        self.pending = [item for item in self.pending if item["request_id"] != request_id]
        return len(self.pending) != before

    def get_thread_permission_rules(self, thread_id: str) -> dict[str, object]:
        return {
            "thread_id": thread_id,
            "scope": "session",
            "managed_only": self.managed_only,
            "rules": dict(self.session_rules),
        }

    def add_thread_permission_rule(self, thread_id: str, *, behavior: str, tool_name: str) -> bool:
        self.rule_add_calls.append((behavior, tool_name))
        if self.managed_only:
            return False
        for bucket in self.session_rules.values():
            if tool_name in bucket:
                bucket.remove(tool_name)
        bucket = self.session_rules.setdefault(behavior, [])
        if tool_name not in bucket:
            bucket.append(tool_name)
        return True

    def remove_thread_permission_rule(self, thread_id: str, *, behavior: str, tool_name: str) -> bool:
        self.rule_remove_calls.append((behavior, tool_name))
        bucket = self.session_rules.get(behavior, [])
        if tool_name not in bucket:
            return False
        bucket.remove(tool_name)
        return True


class _MemoryCheckpointer:
    def __init__(self, channel_values: dict | None = None) -> None:
        self._checkpoint = {"channel_values": dict(channel_values or {})}

    async def aget(self, _cfg):
        return self._checkpoint


class _LivePendingPermissionAgent:
    def __init__(self) -> None:
        app_state = AppState(
            tool_permission_context=ToolPermissionState(alwaysAskRules={"session": ["Bash"]}),
            pending_permission_requests={
                "perm-live": {
                    "request_id": "perm-live",
                    "thread_id": "thread-1",
                    "tool_name": "Bash",
                    "args": {"command": "echo hi"},
                    "message": "Permission required by rule: Bash",
                }
            },
        )
        self.agent = QueryLoop(
            model=MagicMock(),
            system_prompt=SystemMessage(content="sys"),
            middleware=[],
            checkpointer=_MemoryCheckpointer(channel_values={"messages": []}),
            registry=ToolRegistry(),
            app_state=app_state,
            runtime=SimpleNamespace(current_state=AgentState.ACTIVE),
            bootstrap=BootstrapConfig(
                workspace_root=Path("/tmp"),
                model_name="test-model",
                permission_resolver_scope="thread",
            ),
            max_turns=1,
        )

    def get_pending_permission_requests(self, thread_id: str | None = None):
        requests = list(_require_app_state(self.agent).pending_permission_requests.values())
        if thread_id is None:
            return requests
        return [item for item in requests if item["thread_id"] == thread_id]

    def get_thread_permission_rules(self, thread_id: str) -> dict[str, object]:
        state = _require_app_state(self.agent).tool_permission_context
        return {
            "thread_id": thread_id,
            "scope": "session",
            "managed_only": state.allowManagedPermissionRulesOnly,
            "rules": {
                "allow": list(state.alwaysAllowRules.get("session", [])),
                "deny": list(state.alwaysDenyRules.get("session", [])),
                "ask": list(state.alwaysAskRules.get("session", [])),
            },
        }


class _FakeAskUserQuestionAgent(_FakePermissionAgent):
    def __init__(self) -> None:
        super().__init__()
        self.pending = [
            {
                "request_id": "perm-ask",
                "thread_id": "thread-1",
                "tool_name": "AskUserQuestion",
                "args": {
                    "questions": [
                        {
                            "header": "Style",
                            "question": "Choose a style",
                            "options": [
                                {"label": "Minimal", "description": "Keep it simple"},
                                {"label": "Bold", "description": "Make it loud"},
                            ],
                        }
                    ]
                },
                "message": "Please answer the following questions so Leon can continue.",
            }
        ]

    def resolve_permission_request(
        self,
        request_id: str,
        *,
        decision: str,
        message: str | None = None,
        answers: list[dict] | None = None,
        annotations: dict | None = None,
    ) -> bool:
        self.resolve_calls.append((request_id, decision, message, answers, annotations))
        if request_id != "perm-ask":
            return False
        self.pending = []
        return True


class _NullLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClearAgent:
    def __init__(self, state: AgentState = AgentState.IDLE) -> None:
        self.runtime = SimpleNamespace(current_state=state)
        self.aclear_thread = AsyncMock()


def _make_threads_app(
    *,
    thread_repo=None,
    **state_overrides,
):
    return SimpleNamespace(
        state=SimpleNamespace(
            user_repo=state_overrides.pop("user_repo", _FakeUserRepo()),
            thread_repo=thread_repo or _FakeThreadRepo(),
            **state_overrides,
        )
    )


def _make_clear_thread_app():
    display_builder = SimpleNamespace(clear=MagicMock())
    queue_manager = SimpleNamespace(clear_all=MagicMock())
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_pool={},
            display_builder=display_builder,
            queue_manager=queue_manager,
            thread_event_buffers={"thread-1": object()},
        )
    )
    return app, display_builder, queue_manager


@contextmanager
def _patch_create_thread_noop_guards():
    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", return_value=None),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None) as create_resources,
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
        patch.object(threads_router, "save_last_successful_config", return_value=None),
    ):
        yield create_resources


@contextmanager
def _patch_local_clear_thread_agent(agent):
    with (
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
        patch.object(threads_router, "get_or_create_agent", AsyncMock(return_value=agent)),
        patch.object(threads_router, "get_thread_lock", AsyncMock(return_value=_NullLock())),
    ):
        yield


@pytest.mark.asyncio
async def test_get_thread_lease_status_returns_null_when_thread_has_no_lease():
    with patch.object(threads_router, "get_lease_status", AsyncMock(return_value=None)) as get_lease_status:
        result = await threads_router.get_thread_lease_status("thread-1", agent=object())

    get_lease_status.assert_awaited_once()
    assert result is None


@pytest.mark.asyncio
async def test_create_thread_route_preserves_legacy_sandbox_type_alias():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "sandbox_type": "daytona_selfhost",
            "model": "gpt-5.4-mini",
        }
    )

    with _patch_create_thread_noop_guards():
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    assert result["sandbox"] == "daytona_selfhost"
    assert app.state.thread_sandbox[result["thread_id"]] == "daytona_selfhost"
    assert app.state.thread_repo.rows[result["thread_id"]]["sandbox_type"] == "daytona_selfhost"


@pytest.mark.asyncio
async def test_resolve_main_thread_returns_null_for_orphaned_main_thread_metadata():
    thread_repo = _FakeThreadRepo()
    thread_repo.create(
        thread_id="thread-1",
        agent_user_id="member-1",
        owner_user_id="owner-1",
        sandbox_type="local",
        is_main=True,
        branch_index=0,
    )
    empty_user_repo = SimpleNamespace(get_by_id=lambda _mid: None)
    app = _make_threads_app(thread_repo=thread_repo, user_repo=empty_user_repo)

    payload = threads_router.ResolveMainThreadRequest(agent_user_id="member-1")

    result = await threads_router.resolve_main_thread(payload, "owner-1", app)

    assert result == {
        "agent_user_id": "member-1",
        "default_thread_id": None,
        "thread": None,
    }


@pytest.mark.asyncio
async def test_resolve_main_thread_exposes_default_thread_identity_without_hiding_thread_payload():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = threads_router.ResolveMainThreadRequest(agent_user_id="member-1")

    with _patch_create_thread_noop_guards():
        created = _require_thread_result(
            await threads_router.create_thread(payload=CreateThreadRequest(agent_user_id="member-1"), user_id="owner-1", app=app)
        )

    result = await threads_router.resolve_main_thread(payload, "owner-1", app)

    assert result["agent_user_id"] == "member-1"
    assert result["default_thread_id"] == created["thread_id"]
    assert result["thread"]["thread_id"] == created["thread_id"]
    assert result["thread"]["agent_user_id"] == "member-1"


@pytest.mark.asyncio
async def test_create_thread_persists_agent_user_id():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})

    with _patch_create_thread_noop_guards():
        created = _require_thread_result(
            await threads_router.create_thread(
                payload=CreateThreadRequest(agent_user_id="member-1"),
                user_id="owner-1",
                app=app,
            )
        )

    row = app.state.thread_repo.rows[created["thread_id"]]
    assert row["agent_user_id"] == "member-1"


@pytest.mark.asyncio
async def test_create_thread_route_uses_canonical_existing_lease_binding_helper():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "lease_id": "lease-1",
            "cwd": "/workspace/reused",
        }
    )

    with (
        patch.object(
            threads_router.sandbox_service,
            "list_user_leases",
            return_value=[{"lease_id": "lease-1", "provider_name": "local", "recipe": None}],
        ),
        patch.object(threads_router, "bind_thread_to_existing_lease", return_value="/workspace/reused") as bind_helper,
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
        patch.object(threads_router, "save_last_successful_config", return_value=None),
    ):
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    bind_helper.assert_called_once_with(
        result["thread_id"],
        "lease-1",
        cwd="/workspace/reused",
    )
    assert app.state.thread_cwd[result["thread_id"]] == "/workspace/reused"


@pytest.mark.asyncio
async def test_create_thread_route_passes_local_cwd_into_sandbox_bootstrap():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "cwd": "/tmp/fresh-local-thread",
        }
    )

    with _patch_create_thread_noop_guards() as create_resources:
        result = _require_thread_result(await threads_router.create_thread(payload, "owner-1", app))

    create_resources.assert_called_once_with(
        result["thread_id"],
        "local",
        None,
        "/tmp/fresh-local-thread",
    )


@pytest.mark.asyncio
async def test_list_threads_hides_internal_subagent_threads():
    rows = {
        "main-thread": {
            "id": "main-thread",
            "sandbox_type": "local",
            "agent_name": "Toad",
            "agent_user_id": "member-1",
            "branch_index": 0,
            "is_main": True,
            "agent_avatar": None,
        },
        "subagent-deadbeef": {
            "id": "subagent-deadbeef",
            "sandbox_type": "local",
            "agent_name": "Toad",
            "agent_user_id": "member-1",
            "branch_index": 1,
            "is_main": False,
            "agent_avatar": None,
        },
    }
    app = _make_threads_app(
        thread_repo=SimpleNamespace(
            list_by_owner_user_id=lambda user_id: list(rows.values()),
            get_by_id=lambda thread_id: rows.get(thread_id),
        ),
        terminal_repo=SimpleNamespace(
            get_active=lambda _thread_id: {"terminal_id": "term-1"},
            list_by_thread=lambda _thread_id: [{"terminal_id": "term-1"}],
            set_active=lambda _thread_id, _terminal_id: None,
        ),
        agent_pool={},
        thread_last_active={},
    )

    payload = await threads_router.list_threads("owner-1", app)

    assert [item["thread_id"] for item in payload["threads"]] == ["main-thread"]


@pytest.mark.asyncio
async def test_list_threads_purges_incomplete_owner_visible_threads(monkeypatch: pytest.MonkeyPatch):
    deleted: list[str] = []
    purged: list[str] = []
    rows = {
        "broken-thread": {
            "id": "broken-thread",
            "sandbox_type": "local",
            "agent_name": "Toad",
            "agent_user_id": "member-1",
            "branch_index": 0,
            "is_main": True,
            "agent_avatar": None,
        },
        "healthy-thread": {
            "id": "healthy-thread",
            "sandbox_type": "local",
            "agent_name": "Toad",
            "agent_user_id": "member-1",
            "branch_index": 1,
            "is_main": False,
            "agent_avatar": None,
        },
    }

    def _delete(thread_id: str) -> None:
        deleted.append(thread_id)
        rows.pop(thread_id, None)

    app = _make_threads_app(
        thread_repo=SimpleNamespace(
            list_by_owner_user_id=lambda _user_id: list(rows.values()),
            get_by_id=lambda thread_id: rows.get(thread_id),
            delete=_delete,
        ),
        terminal_repo=SimpleNamespace(
            get_active=lambda thread_id: {"terminal_id": f"term-{thread_id}"} if thread_id == "healthy-thread" else None,
            list_by_thread=lambda thread_id: [] if thread_id == "broken-thread" else [{"terminal_id": "term-healthy"}],
            set_active=lambda _thread_id, _terminal_id: None,
        ),
        agent_pool={},
        thread_last_active={},
        queue_manager=SimpleNamespace(clear_all=lambda _thread_id: None),
        thread_sandbox={},
        thread_cwd={},
        thread_event_buffers={},
        thread_tasks={},
    )

    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda thread_id: purged.append(thread_id),
    )

    payload = await threads_router.list_threads("owner-1", app)

    assert [item["thread_id"] for item in payload["threads"]] == ["healthy-thread"]
    assert purged == ["broken-thread"]
    assert deleted == ["broken-thread"]


@pytest.mark.asyncio
async def test_create_thread_route_rejects_unavailable_provider():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "sandbox": "daytona",
        }
    )

    with patch.object(threads_router.sandbox_service, "build_provider_from_config_name", return_value=None):
        result = await threads_router.create_thread(payload, "owner-1", app)

    assert isinstance(result, threads_router.JSONResponse)
    assert result.status_code == 400
    assert _decode_json_response(result) == {
        "error": "sandbox_provider_unavailable",
        "provider": "daytona",
    }
    assert app.state.thread_repo.rows == {}


@pytest.mark.asyncio
async def test_create_thread_route_rejects_unavailable_provider_for_existing_lease():
    app = _make_threads_app(thread_sandbox={}, thread_cwd={})
    payload = CreateThreadRequest.model_validate(
        {
            "agent_user_id": "member-1",
            "lease_id": "lease-1",
        }
    )

    with (
        patch.object(
            threads_router.sandbox_service,
            "list_user_leases",
            return_value=[{"lease_id": "lease-1", "provider_name": "daytona", "recipe": None}],
        ),
        patch.object(threads_router.sandbox_service, "build_provider_from_config_name", return_value=None),
    ):
        result = await threads_router.create_thread(payload, "owner-1", app)

    assert isinstance(result, threads_router.JSONResponse)
    assert result.status_code == 400
    assert _decode_json_response(result) == {
        "error": "sandbox_provider_unavailable",
        "provider": "daytona",
    }
    assert app.state.thread_repo.rows == {}


@pytest.mark.asyncio
async def test_stream_thread_events_requires_token():
    app = _make_threads_app(
        auth_service=_FakeAuthService(),
        thread_repo=SimpleNamespace(get_by_id=lambda _thread_id: None),
        thread_event_buffers={},
    )

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.stream_thread_events(
            "thread-1",
            request=_make_request(),
            token=None,
            app=app,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing token"


@pytest.mark.asyncio
async def test_stream_thread_events_verifies_token_before_owner_check():
    auth_service = _FakeAuthService()
    thread_repo = SimpleNamespace(get_by_id=lambda _thread_id: {"agent_user_id": "member-1"})
    app = _make_threads_app(
        auth_service=auth_service,
        thread_repo=thread_repo,
        thread_event_buffers={},
    )

    response = await threads_router.stream_thread_events(
        "thread-1",
        request=_make_request(),
        token="tok-thread",
        app=app,
    )

    assert auth_service.tokens == ["tok-thread"]
    assert response is not None


@pytest.mark.asyncio
async def test_get_thread_permissions_returns_thread_scoped_pending_requests():
    agent = _FakePermissionAgent()

    result = await threads_router.get_thread_permissions(
        "thread-1",
        user_id="owner-1",
        agent=agent,
    )

    assert result == {
        "thread_id": "thread-1",
        "requests": [
            {
                "request_id": "perm-1",
                "thread_id": "thread-1",
                "tool_name": "Write",
                "args": {"path": "/tmp/demo.txt"},
                "message": "needs approval",
            }
        ],
        "session_rules": {
            "allow": ["Read"],
            "deny": ["Bash"],
            "ask": ["Edit"],
        },
        "managed_only": False,
    }


@pytest.mark.asyncio
async def test_get_thread_permissions_does_not_clear_live_pending_requests_during_active_run():
    agent = _LivePendingPermissionAgent()
    app_state = _require_app_state(agent.agent)

    result = await threads_router.get_thread_permissions(
        "thread-1",
        user_id="owner-1",
        agent=agent,
    )

    assert result == {
        "thread_id": "thread-1",
        "requests": [
            {
                "request_id": "perm-live",
                "thread_id": "thread-1",
                "tool_name": "Bash",
                "args": {"command": "echo hi"},
                "message": "Permission required by rule: Bash",
            }
        ],
        "session_rules": {
            "allow": [],
            "deny": [],
            "ask": ["Bash"],
        },
        "managed_only": False,
    }
    assert app_state.pending_permission_requests == {
        "perm-live": {
            "request_id": "perm-live",
            "thread_id": "thread-1",
            "tool_name": "Bash",
            "args": {"command": "echo hi"},
            "message": "Permission required by rule: Bash",
        }
    }


@pytest.mark.asyncio
async def test_get_thread_history_does_not_clear_live_pending_requests_during_active_run():
    agent = _LivePendingPermissionAgent()
    app_state = _require_app_state(agent.agent)
    app_state.messages = [
        HumanMessage(content="please run bash"),
        ToolMessage(content="Permission required by rule: Bash", tool_call_id="call-1", name="Bash"),
    ]

    with (
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
        patch.object(
            threads_router,
            "get_or_create_agent",
            AsyncMock(return_value=agent),
        ),
    ):
        result = await threads_router.get_thread_history(
            "thread-1",
            limit=20,
            truncate=0,
            user_id="owner-1",
            app=SimpleNamespace(state=SimpleNamespace()),
        )

    assert result["messages"] == [
        {"role": "human", "text": "please run bash"},
        {"role": "tool_result", "tool": "Bash", "text": "Permission required by rule: Bash"},
    ]
    assert app_state.pending_permission_requests == {
        "perm-live": {
            "request_id": "perm-live",
            "thread_id": "thread-1",
            "tool_name": "Bash",
            "args": {"command": "echo hi"},
            "message": "Permission required by rule: Bash",
        }
    }


@pytest.mark.asyncio
async def test_resolve_thread_permission_request_persists_resolution():
    agent = _FakePermissionAgent()

    result = await threads_router.resolve_thread_permission_request(
        "thread-1",
        "perm-1",
        ResolvePermissionRequest(decision="allow", message="go ahead"),
        user_id="owner-1",
        agent=agent,
    )

    assert result == {"ok": True, "thread_id": "thread-1", "request_id": "perm-1"}
    assert agent.resolve_calls == [("perm-1", "allow", "go ahead", None, None)]
    agent.agent.apersist_state.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_resolve_ask_user_question_request_starts_followup_run_with_answers():
    agent = _FakeAskUserQuestionAgent()
    app = SimpleNamespace()
    payload = ResolvePermissionRequest.model_validate(
        {
            "decision": "allow",
            "message": None,
            "answers": [
                {
                    "header": "Style",
                    "question": "Choose a style",
                    "selected_options": ["Minimal"],
                }
            ],
            "annotations": {"source": "ask-user-ui"},
        }
    )

    with patch(
        "backend.web.services.message_routing.route_message_to_brain",
        AsyncMock(return_value={"status": "started", "routing": "direct", "thread_id": "thread-1"}),
    ) as route_message:
        result = await threads_router.resolve_thread_permission_request(
            "thread-1",
            "perm-ask",
            payload,
            user_id="owner-1",
            agent=agent,
            app=app,
        )

    assert result == {
        "ok": True,
        "thread_id": "thread-1",
        "request_id": "perm-ask",
        "followup": {"status": "started", "routing": "direct", "thread_id": "thread-1"},
    }
    assert agent.resolve_calls == [
        (
            "perm-ask",
            "allow",
            None,
            [
                {
                    "header": "Style",
                    "question": "Choose a style",
                    "selected_options": ["Minimal"],
                }
            ],
            {"source": "ask-user-ui"},
        )
    ]
    route_message.assert_awaited_once()
    route_kwargs = _require_await_kwargs(route_message)
    assert route_kwargs["source"] == "internal"
    assert route_kwargs["message_metadata"] == {
        "ask_user_question_answered": {
            "questions": [
                {
                    "header": "Style",
                    "question": "Choose a style",
                    "options": [
                        {"label": "Minimal", "description": "Keep it simple"},
                        {"label": "Bold", "description": "Make it loud"},
                    ],
                }
            ],
            "answers": [
                {
                    "header": "Style",
                    "question": "Choose a style",
                    "selected_options": ["Minimal"],
                }
            ],
            "annotations": {"source": "ask-user-ui"},
        }
    }
    followup_message = _require_await_args(route_message)[2]
    assert "AskUserQuestion" in followup_message
    assert "Minimal" in followup_message
    assert "Choose a style" in followup_message
    assert agent.pending == []
    assert agent.agent.apersist_state.await_count == 2
    assert [call.args for call in agent.agent.apersist_state.await_args_list] == [("thread-1",), ("thread-1",)]


@pytest.mark.asyncio
async def test_resolve_ask_user_question_request_requires_answers_for_allow():
    agent = _FakeAskUserQuestionAgent()

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.resolve_thread_permission_request(
            "thread-1",
            "perm-ask",
            ResolvePermissionRequest(decision="allow", message=None, answers=None, annotations=None),
            user_id="owner-1",
            agent=agent,
            app=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "AskUserQuestion answers are required when approving the request"
    agent.agent.apersist_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_thread_permission_request_404s_missing_request():
    agent = _FakePermissionAgent()

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.resolve_thread_permission_request(
            "thread-1",
            "missing",
            ResolvePermissionRequest(decision="deny", message="no"),
            user_id="owner-1",
            agent=agent,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Permission request not found"
    agent.agent.apersist_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_thread_permission_rule_persists_session_rule():
    agent = _FakePermissionAgent()

    result = await threads_router.add_thread_permission_rule(
        "thread-1",
        ThreadPermissionRuleRequest(behavior="allow", tool_name="Write"),
        user_id="owner-1",
        agent=agent,
    )

    assert result == {
        "ok": True,
        "thread_id": "thread-1",
        "scope": "session",
        "rules": {
            "allow": ["Read", "Write"],
            "deny": ["Bash"],
            "ask": ["Edit"],
        },
        "managed_only": False,
    }
    assert agent.rule_add_calls == [("allow", "Write")]
    agent.agent.apersist_state.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_add_thread_permission_rule_fails_loud_when_managed_only():
    agent = _FakePermissionAgent()
    agent.managed_only = True

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.add_thread_permission_rule(
            "thread-1",
            ThreadPermissionRuleRequest(behavior="allow", tool_name="Write"),
            user_id="owner-1",
            agent=agent,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Managed permission rules only; session overrides are disabled"
    agent.agent.apersist_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_thread_permission_rule_persists_session_rule_change():
    agent = _FakePermissionAgent()

    result = await threads_router.delete_thread_permission_rule(
        "thread-1",
        "deny",
        "Bash",
        user_id="owner-1",
        agent=agent,
    )

    assert result == {
        "ok": True,
        "thread_id": "thread-1",
        "scope": "session",
        "rules": {
            "allow": ["Read"],
            "deny": [],
            "ask": ["Edit"],
        },
        "managed_only": False,
    }
    assert agent.rule_remove_calls == [("deny", "Bash")]
    agent.agent.apersist_state.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_clear_thread_route_clears_agent_state_and_thread_buffers():
    agent = _FakeClearAgent()
    app, display_builder, queue_manager = _make_clear_thread_app()

    with _patch_local_clear_thread_agent(agent):
        result = await threads_router.clear_thread_history(
            "thread-1",
            user_id="owner-1",
            app=app,
        )

    assert result == {"ok": True, "thread_id": "thread-1"}
    agent.aclear_thread.assert_awaited_once_with("thread-1")
    display_builder.clear.assert_called_once_with("thread-1")
    queue_manager.clear_all.assert_called_once_with("thread-1")
    assert app.state.thread_event_buffers == {}


@pytest.mark.asyncio
async def test_clear_thread_route_rejects_active_run():
    agent = _FakeClearAgent(state=AgentState.ACTIVE)
    app, display_builder, queue_manager = _make_clear_thread_app()

    with _patch_local_clear_thread_agent(agent):
        with pytest.raises(threads_router.HTTPException) as exc_info:
            await threads_router.clear_thread_history(
                "thread-1",
                user_id="owner-1",
                app=app,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Cannot clear thread while run is in progress"
    agent.aclear_thread.assert_not_awaited()
    display_builder.clear.assert_not_called()
    queue_manager.clear_all.assert_not_called()
    assert "thread-1" in app.state.thread_event_buffers
