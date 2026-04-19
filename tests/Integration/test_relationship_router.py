from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import backend.web.main as web_main
from backend.chat.api.http import relationships_router as owner_relationship_router
from messaging.contracts import RelationshipRow


def _row(*, state: str = "pending", initiator_user_id: str = "requester-user-1") -> RelationshipRow:
    now = datetime(2026, 4, 8, tzinfo=UTC)
    return RelationshipRow(
        id="hire_visit:agent-user-1:requester-user-1",
        user_low="agent-user-1",
        user_high="requester-user-1",
        kind="hire_visit",
        state=state,
        initiator_user_id=initiator_user_id,
        created_at=now,
        updated_at=now,
    )


def test_relationship_router_imports_actor_ownership_primitive() -> None:
    source = inspect.getsource(owner_relationship_router)

    assert "from messaging.actor_ownership import" in source
    assert "owner_user_id" not in source


def test_relationship_router_uses_neutral_chat_dependency_owner() -> None:
    source = inspect.getsource(owner_relationship_router)

    assert "backend.web.core.dependencies" not in source
    assert "backend.chat.api.http.dependencies" in source


def test_relationship_router_owner_module_lives_under_backend_chat() -> None:
    assert owner_relationship_router.__name__ == "backend.chat.api.http.relationships_router"
    main_source = inspect.getsource(web_main)
    assert "relationships_router" in main_source
    assert "messaging.relationships.router" not in main_source


@pytest.mark.asyncio
async def test_request_relationship_accepts_owned_agent_actor_user_id() -> None:
    seen: list[tuple[str, str]] = []
    app = SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=SimpleNamespace(
                request=lambda actor_id, target_id: seen.append((actor_id, target_id)) or _row(initiator_user_id=actor_id)
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
            ),
        )
    )

    result = await owner_relationship_router.request_relationship(
        owner_relationship_router.RelationshipRequestBody(target_user_id="requester-user-1", actor_user_id="agent-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["is_requester"] is True
    assert "hire_granted_at" not in result
    assert "hire_revoked_at" not in result


@pytest.mark.asyncio
async def test_approve_relationship_accepts_owned_agent_actor_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "pending",
        "initiator_user_id": "requester-user-1",
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=SimpleNamespace(
                get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
                approve=lambda actor_id, requester_id: (
                    seen.append((actor_id, requester_id)) or _row(state="visit", initiator_user_id=requester_id)
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
            ),
        )
    )

    result = await owner_relationship_router.approve_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(actor_user_id="agent-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"
    assert "hire_granted_at" not in result
    assert "hire_revoked_at" not in result


@pytest.mark.asyncio
async def test_reject_relationship_accepts_owned_agent_actor_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "pending",
        "initiator_user_id": "requester-user-1",
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=SimpleNamespace(
                get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
                reject=lambda actor_id, requester_id: (
                    seen.append((actor_id, requester_id)) or _row(state="none", initiator_user_id=requester_id)
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
            ),
        )
    )

    result = await owner_relationship_router.reject_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(actor_user_id="agent-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "none"


@pytest.mark.asyncio
async def test_downgrade_relationship_accepts_owned_agent_actor_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "hire",
        "initiator_user_id": "requester-user-1",
    }
    app = SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=SimpleNamespace(
                get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
                downgrade=lambda actor_id, other_id: (
                    seen.append((actor_id, other_id)) or _row(state="visit", initiator_user_id="requester-user-1")
                ),
            ),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
            ),
        )
    )

    result = await owner_relationship_router.downgrade_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(actor_user_id="agent-user-1"),
        user_id="owner-user-1",
        app=app,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"


@pytest.mark.asyncio
async def test_request_relationship_rejects_unowned_actor_user_id() -> None:
    app = SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=SimpleNamespace(),
            user_repo=SimpleNamespace(
                get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="someone-else") if user_id == "agent-user-1" else None
            ),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await owner_relationship_router.request_relationship(
            owner_relationship_router.RelationshipRequestBody(target_user_id="requester-user-1", actor_user_id="agent-user-1"),
            user_id="owner-user-1",
            app=app,
        )

    assert exc_info.value.status_code == 403


def test_relationship_action_body_rejects_removed_hire_snapshot_field() -> None:
    with pytest.raises(ValidationError):
        owner_relationship_router.RelationshipActionBody(actor_user_id="agent-user-1", hire_snapshot={"probe": "live"})
