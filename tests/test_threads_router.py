from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.web.models.requests import CreateThreadRequest
from backend.web.routers import threads as threads_router
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
        self.resolve_calls: list[tuple[str, str, str | None]] = []
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
