from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


@pytest.mark.asyncio
async def test_request_relationship_accepts_owned_agent_requester_user_id() -> None:
    seen: list[tuple[str, str]] = []
    relationship_service = SimpleNamespace(
        request=lambda requester_id, target_id: seen.append((requester_id, target_id)) or _row(initiator_user_id=requester_id)
    )
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
    )

    result = await owner_relationship_router.request_relationship(
        owner_relationship_router.RelationshipRequestBody(target_user_id="requester-user-1", requester_user_id="agent-user-1"),
        user_id="owner-user-1",
        relationship_service=relationship_service,
        user_repo=user_repo,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["is_requester"] is True


@pytest.mark.asyncio
async def test_approve_relationship_accepts_owned_agent_requester_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "pending",
        "initiator_user_id": "requester-user-1",
    }
    relationship_service = SimpleNamespace(
        get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
        approve=lambda approver_id, requester_id: (
            seen.append((approver_id, requester_id)) or _row(state="visit", initiator_user_id=requester_id)
        ),
    )
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
    )

    result = await owner_relationship_router.approve_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(requester_user_id="agent-user-1"),
        user_id="owner-user-1",
        relationship_service=relationship_service,
        user_repo=user_repo,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"


@pytest.mark.asyncio
async def test_reject_relationship_accepts_owned_agent_requester_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "pending",
        "initiator_user_id": "requester-user-1",
    }
    relationship_service = SimpleNamespace(
        get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
        reject=lambda rejecting_user_id, requester_id: (
            seen.append((rejecting_user_id, requester_id)) or _row(state="none", initiator_user_id=requester_id)
        ),
    )
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
    )

    result = await owner_relationship_router.reject_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(requester_user_id="agent-user-1"),
        user_id="owner-user-1",
        relationship_service=relationship_service,
        user_repo=user_repo,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "none"


@pytest.mark.asyncio
async def test_downgrade_relationship_accepts_owned_agent_requester_user_id() -> None:
    seen: list[tuple[str, str]] = []
    existing = {
        "id": "hire_visit:agent-user-1:requester-user-1",
        "user_low": "agent-user-1",
        "user_high": "requester-user-1",
        "state": "hire",
        "initiator_user_id": "requester-user-1",
    }
    relationship_service = SimpleNamespace(
        get_by_id=lambda relationship_id: existing if relationship_id == existing["id"] else None,
        downgrade=lambda requester_id, other_id: (
            seen.append((requester_id, other_id)) or _row(state="visit", initiator_user_id="requester-user-1")
        ),
    )
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="owner-user-1") if user_id == "agent-user-1" else None
    )

    result = await owner_relationship_router.downgrade_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(requester_user_id="agent-user-1"),
        user_id="owner-user-1",
        relationship_service=relationship_service,
        user_repo=user_repo,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"


@pytest.mark.asyncio
async def test_request_relationship_rejects_unowned_requester_user_id() -> None:
    relationship_service = SimpleNamespace()
    user_repo = SimpleNamespace(
        get_by_id=lambda user_id: SimpleNamespace(id=user_id, owner_user_id="someone-else") if user_id == "agent-user-1" else None
    )

    with pytest.raises(HTTPException) as exc_info:
        await owner_relationship_router.request_relationship(
            owner_relationship_router.RelationshipRequestBody(target_user_id="requester-user-1", requester_user_id="agent-user-1"),
            user_id="owner-user-1",
            relationship_service=relationship_service,
            user_repo=user_repo,
        )

    assert exc_info.value.status_code == 403
