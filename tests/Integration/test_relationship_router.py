from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from backend.chat.api.http import relationships_router as owner_relationship_router
from messaging.contracts import RelationshipRow


def _row(
    *,
    state: str = "pending",
    initiator_user_id: str = "requester-user-1",
    user_low: str = "agent-user-1",
    user_high: str = "requester-user-1",
) -> RelationshipRow:
    now = datetime(2026, 4, 8, tzinfo=UTC)
    return RelationshipRow(
        id=f"hire_visit:{user_low}:{user_high}",
        user_low=user_low,
        user_high=user_high,
        kind="hire_visit",
        state=state,
        initiator_user_id=initiator_user_id,
        created_at=now,
        updated_at=now,
    )


def test_relationship_public_openapi_uses_token_identity_only() -> None:
    app = FastAPI()
    app.include_router(owner_relationship_router.router)

    schemas = app.openapi()["components"]["schemas"]
    request_properties = schemas["RelationshipRequestBody"]["properties"]
    action_properties = schemas["RelationshipActionBody"]["properties"]

    assert list(request_properties) == ["target_user_id"]
    assert action_properties == {}


def test_relationship_request_route_is_sync_for_runtime_notification_delivery() -> None:
    assert inspect.iscoroutinefunction(owner_relationship_router.request_relationship) is False


def test_request_relationship_uses_current_token_user() -> None:
    seen: list[tuple[str, str]] = []
    relationship_service = SimpleNamespace(
        request=lambda requester_id, target_id: (
            seen.append((requester_id, target_id))
            or _row(
                initiator_user_id=requester_id,
                user_low=requester_id,
                user_high=target_id,
            )
        )
    )

    result = owner_relationship_router.request_relationship(
        owner_relationship_router.RelationshipRequestBody(target_user_id="requester-user-1"),
        user_id="owner-user-1",
        relationship_service=relationship_service,
    )

    assert seen == [("owner-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["is_requester"] is True


def test_approve_relationship_uses_current_token_user() -> None:
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

    result = owner_relationship_router.approve_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(),
        user_id="agent-user-1",
        relationship_service=relationship_service,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"


def test_reject_relationship_uses_current_token_user() -> None:
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

    result = owner_relationship_router.reject_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(),
        user_id="agent-user-1",
        relationship_service=relationship_service,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "none"


def test_downgrade_relationship_uses_current_token_user() -> None:
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

    result = owner_relationship_router.downgrade_relationship(
        existing["id"],
        owner_relationship_router.RelationshipActionBody(),
        user_id="agent-user-1",
        relationship_service=relationship_service,
    )

    assert seen == [("agent-user-1", "requester-user-1")]
    assert result["other_user_id"] == "requester-user-1"
    assert result["state"] == "visit"


def test_relationship_bodies_reject_identity_injection() -> None:
    with pytest.raises(ValidationError):
        owner_relationship_router.RelationshipRequestBody(
            target_user_id="requester-user-1",
            requester_user_id="agent-user-1",
        )

    with pytest.raises(ValidationError):
        owner_relationship_router.RelationshipActionBody(requester_user_id="agent-user-1")
