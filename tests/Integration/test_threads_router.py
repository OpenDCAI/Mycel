from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.web.models.requests import CreateThreadRequest
from backend.web.routers import threads as threads_router
from core.runtime.loop import QueryLoop
from core.runtime.middleware.monitor import AgentState
from core.runtime.registry import ToolRegistry
from core.runtime.state import AppState, BootstrapConfig, ToolPermissionState
from storage.contracts import MemberRow, MemberType


class _FakeMemberRepo:
    def __init__(self) -> None:
        self._members = {
            "member-1": MemberRow(
                id="member-1",
                name="Toad",
                type=MemberType.MYCEL_AGENT,
                owner_user_id="owner-1",
                created_at=1.0,
            )
        }
        self._seq = {"member-1": 0}

    def get_by_id(self, member_id: str):
        return self._members.get(member_id)

    def increment_entity_seq(self, member_id: str) -> int:
        self._seq[member_id] += 1
        return self._seq[member_id]


class _FakeThreadRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def get_main_thread(self, member_id: str):
        for row in self.rows.values():
            if row["member_id"] == member_id and row["is_main"]:
                return {"id": row["thread_id"], **row}
        return None

    def get_next_branch_index(self, member_id: str) -> int:
        indices = [row["branch_index"] for row in self.rows.values() if row["member_id"] == member_id]
        return max(indices, default=0) + 1

    def create(self, **kwargs):
        self.rows[kwargs["thread_id"]] = dict(kwargs)


class _FakeEntityRepo:
    def __init__(self) -> None:
        self.rows = []

    def create(self, row):
        self.rows.append(row)

    def get_by_id(self, entity_id: str):
        for row in self.rows:
            if row.id == entity_id:
                return row
        return None

    def update_thread_id(self, entity_id: str, thread_id: str):
        row = self.get_by_id(entity_id)
        if row is not None:
            row.thread_id = thread_id


class _FakeAuthService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def verify_token(self, token: str) -> dict:
        self.tokens.append(token)
        return {"user_id": "owner-1"}


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


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
        self.resolve_calls: list[tuple[str, str, str | None]] = []
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

    def resolve_permission_request(self, request_id: str, *, decision: str, message: str | None = None) -> bool:
        self.resolve_calls.append((request_id, decision, message))
        if request_id != "perm-1":
            return False
        self.pending = []
        return True

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
        requests = list(self.agent._app_state.pending_permission_requests.values())
        if thread_id is None:
            return requests
        return [item for item in requests if item["thread_id"] == thread_id]

    def get_thread_permission_rules(self, thread_id: str) -> dict[str, object]:
        state = self.agent._app_state.tool_permission_context
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


class _NullLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClearAgent:
    def __init__(self, state: AgentState = AgentState.IDLE) -> None:
        self.runtime = SimpleNamespace(current_state=state)
        self.aclear_thread = AsyncMock()


@pytest.mark.asyncio
async def test_create_thread_route_preserves_legacy_sandbox_type_alias():
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=_FakeMemberRepo(),
            thread_repo=_FakeThreadRepo(),
            entity_repo=_FakeEntityRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
            "sandbox_type": "daytona_selfhost",
            "model": "gpt-5.4-mini",
        }
    )

    with (
        patch.object(threads_router, "_validate_sandbox_provider_gate", return_value=None),
        patch.object(threads_router, "_validate_mount_capability_gate", return_value=None),
        patch.object(threads_router, "_create_thread_sandbox_resources", return_value=None),
        patch.object(threads_router, "_invalidate_resource_overview_cache", return_value=None),
        patch.object(threads_router, "save_last_successful_config", return_value=None),
    ):
        result = await threads_router.create_thread(payload, "owner-1", app)

    assert result["sandbox"] == "daytona_selfhost"
    assert app.state.thread_sandbox[result["thread_id"]] == "daytona_selfhost"
    assert app.state.thread_repo.rows[result["thread_id"]]["sandbox_type"] == "daytona_selfhost"


@pytest.mark.asyncio
async def test_create_thread_route_uses_canonical_existing_lease_binding_helper():
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=_FakeMemberRepo(),
            thread_repo=_FakeThreadRepo(),
            entity_repo=_FakeEntityRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
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
        result = await threads_router.create_thread(payload, "owner-1", app)

    bind_helper.assert_called_once_with(
        result["thread_id"],
        "lease-1",
        cwd="/workspace/reused",
    )
    assert app.state.thread_cwd[result["thread_id"]] == "/workspace/reused"


@pytest.mark.asyncio
async def test_list_threads_hides_internal_subagent_threads():
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                list_by_owner_user_id=lambda user_id: [
                    {
                        "id": "main-thread",
                        "sandbox_type": "local",
                        "member_name": "Toad",
                        "member_id": "member-1",
                        "entity_name": "Toad",
                        "branch_index": 0,
                        "is_main": True,
                        "member_avatar": None,
                    },
                    {
                        "id": "subagent-deadbeef",
                        "sandbox_type": "local",
                        "member_name": "Toad",
                        "member_id": "member-1",
                        "entity_name": "worker-1",
                        "branch_index": 1,
                        "is_main": False,
                        "member_avatar": None,
                    },
                ]
            ),
            agent_pool={},
            thread_last_active={},
        )
    )

    payload = await threads_router.list_threads("owner-1", app)

    assert [item["thread_id"] for item in payload["threads"]] == ["main-thread"]


@pytest.mark.asyncio
async def test_create_thread_route_rejects_unavailable_provider():
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=_FakeMemberRepo(),
            thread_repo=_FakeThreadRepo(),
            entity_repo=_FakeEntityRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
            "sandbox": "daytona",
        }
    )

    with patch.object(threads_router.sandbox_service, "build_provider_from_config_name", return_value=None):
        result = await threads_router.create_thread(payload, "owner-1", app)

    assert isinstance(result, threads_router.JSONResponse)
    assert result.status_code == 400
    assert json.loads(result.body.decode()) == {
        "error": "sandbox_provider_unavailable",
        "provider": "daytona",
    }
    assert app.state.thread_repo.rows == {}


@pytest.mark.asyncio
async def test_create_thread_route_rejects_unavailable_provider_for_existing_lease():
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=_FakeMemberRepo(),
            thread_repo=_FakeThreadRepo(),
            entity_repo=_FakeEntityRepo(),
            thread_sandbox={},
            thread_cwd={},
        )
    )
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
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
    assert json.loads(result.body.decode()) == {
        "error": "sandbox_provider_unavailable",
        "provider": "daytona",
    }
    assert app.state.thread_repo.rows == {}


@pytest.mark.asyncio
async def test_stream_thread_events_requires_token():
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_service=_FakeAuthService(),
            thread_repo=SimpleNamespace(get_by_id=lambda _thread_id: None),
            member_repo=_FakeMemberRepo(),
            thread_event_buffers={},
        )
    )

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.stream_thread_events(
            "thread-1",
            request=_FakeRequest(),
            token=None,
            app=app,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing token"


@pytest.mark.asyncio
async def test_stream_thread_events_verifies_token_before_owner_check():
    auth_service = _FakeAuthService()
    thread_repo = SimpleNamespace(get_by_id=lambda _thread_id: {"member_id": "member-1"})
    app = SimpleNamespace(
        state=SimpleNamespace(
            auth_service=auth_service,
            thread_repo=thread_repo,
            member_repo=_FakeMemberRepo(),
            thread_event_buffers={},
        )
    )

    response = await threads_router.stream_thread_events(
        "thread-1",
        request=_FakeRequest(),
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
    assert agent.agent._app_state.pending_permission_requests == {
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
    agent.agent._app_state.messages = [
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
    assert agent.agent._app_state.pending_permission_requests == {
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
        SimpleNamespace(decision="allow", message="go ahead"),
        user_id="owner-1",
        agent=agent,
    )

    assert result == {"ok": True, "thread_id": "thread-1", "request_id": "perm-1"}
    assert agent.resolve_calls == [("perm-1", "allow", "go ahead")]
    agent.agent.apersist_state.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_resolve_thread_permission_request_404s_missing_request():
    agent = _FakePermissionAgent()

    with pytest.raises(threads_router.HTTPException) as exc_info:
        await threads_router.resolve_thread_permission_request(
            "thread-1",
            "missing",
            SimpleNamespace(decision="deny", message="no"),
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
        SimpleNamespace(behavior="allow", tool_name="Write"),
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
            SimpleNamespace(behavior="allow", tool_name="Write"),
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

    with (
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
        patch.object(threads_router, "get_or_create_agent", AsyncMock(return_value=agent)),
        patch.object(threads_router, "get_thread_lock", AsyncMock(return_value=_NullLock())),
    ):
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

    with (
        patch.object(threads_router, "resolve_thread_sandbox", return_value="local"),
        patch.object(threads_router, "get_or_create_agent", AsyncMock(return_value=agent)),
        patch.object(threads_router, "get_thread_lock", AsyncMock(return_value=_NullLock())),
    ):
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
