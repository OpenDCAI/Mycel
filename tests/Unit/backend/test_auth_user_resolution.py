from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.core import dependencies


class _Request:
    def __init__(self, *, token: str, payload: dict, user_exists: bool = True) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                auth_service=SimpleNamespace(verify_token=lambda seen: payload if seen == token else None),
                user_repo=SimpleNamespace(get_by_id=lambda _user_id: object() if user_exists else None),
                member_repo=SimpleNamespace(
                    get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("member_repo should not gate auth"))
                ),
            )
        )


@pytest.mark.asyncio
async def test_get_current_user_id_still_rejects_deleted_user():
    request = _Request(token="tok-1", payload={"user_id": "ghost-user"}, user_exists=False)

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "User no longer exists — please re-login"


@pytest.mark.asyncio
async def test_get_current_user_id_uses_user_repo_instead_of_member_repo():
    request = _Request(token="tok-1", payload={"user_id": "user-1"}, user_exists=True)

    assert await dependencies.get_current_user_id(request) == "user-1"


@pytest.mark.asyncio
async def test_verify_thread_owner_uses_agent_user_row_not_member_repo():
    request_app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(get_by_id=lambda _thread_id: {"agent_user_id": "agent-1"}),
            terminal_repo=SimpleNamespace(get_active=lambda _thread_id: {"terminal_id": "term-1"}, list_by_thread=lambda _thread_id: []),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-1") if user_id == "agent-1" else None
            ),
            member_repo=SimpleNamespace(
                get_by_id=lambda _user_id: (_ for _ in ()).throw(AssertionError("member_repo should not gate thread ownership"))
            ),
        )
    )

    assert await dependencies.verify_thread_owner("thread-1", "owner-1", request_app) == "owner-1"


@pytest.mark.asyncio
async def test_verify_thread_owner_purges_incomplete_legacy_thread(monkeypatch: pytest.MonkeyPatch):
    deleted: list[str] = []
    purged: list[str] = []
    rows = {"thread-1": {"agent_user_id": "agent-1"}}

    def _get_thread(thread_id: str):
        return rows.get(thread_id)

    def _delete_thread(thread_id: str) -> None:
        deleted.append(thread_id)
        rows.pop(thread_id, None)

    request_app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(get_by_id=_get_thread, delete=_delete_thread),
            terminal_repo=SimpleNamespace(get_active=lambda _thread_id: None, list_by_thread=lambda _thread_id: []),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-1") if user_id == "agent-1" else None
            ),
            queue_manager=SimpleNamespace(clear_all=lambda _thread_id: None),
            thread_sandbox={},
            thread_cwd={},
            thread_event_buffers={},
            thread_tasks={},
            thread_last_active={},
            agent_pool={},
        )
    )

    monkeypatch.setattr(
        "backend.web.services.thread_runtime_convergence.delete_thread_in_db",
        lambda thread_id: purged.append(thread_id),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.verify_thread_owner("thread-1", "owner-1", request_app)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Thread not found"
    assert purged == ["thread-1"]
    assert deleted == ["thread-1"]
