from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from core.runtime.registry import ToolRegistry
from messaging.tools.relationship_tool_service import RelationshipToolService


def _row(
    *,
    relationship_id: str = "hire_visit:agent-user-1:human-user-1",
    user_low: str = "agent-user-1",
    user_high: str = "human-user-1",
    state: str = "pending",
    initiator_user_id: str | None = "human-user-1",
    message: str | None = None,
):
    now = datetime(2026, 4, 26, tzinfo=UTC)
    return SimpleNamespace(
        id=relationship_id,
        user_low=user_low,
        user_high=user_high,
        state=state,
        initiator_user_id=initiator_user_id,
        message=message,
        created_at=now,
        updated_at=now,
    )


def test_relationship_tool_service_registers_user_level_tools_without_identity_arguments() -> None:
    registry = ToolRegistry()
    RelationshipToolService(
        registry=registry,
        relationship_identity_id="agent-user-1",
        relationship_service=SimpleNamespace(list_for_user=lambda _user_id: []),
    )

    for tool_name in ("list_relationships", "request_relationship", "approve_relationship", "reject_relationship"):
        tool = registry.get(tool_name)
        assert tool is not None
        assert "user_id" not in tool.get_schema()["parameters"]["properties"]


def test_list_relationships_renders_pending_direction_and_relationship_id() -> None:
    registry = ToolRegistry()
    RelationshipToolService(
        registry=registry,
        relationship_identity_id="agent-user-1",
        relationship_service=SimpleNamespace(list_for_user=lambda _user_id: [_row()]),
    )

    result = registry.get("list_relationships").handler()

    assert "incoming pending request" in result
    assert "relationship_id: hire_visit:agent-user-1:human-user-1" in result
    assert "other_user_id: human-user-1" in result


def test_request_relationship_tool_accepts_natural_language_message() -> None:
    seen: list[tuple[str, str, str | None]] = []
    registry = ToolRegistry()
    RelationshipToolService(
        registry=registry,
        relationship_identity_id="agent-user-1",
        relationship_service=SimpleNamespace(
            request=lambda requester_id, target_user_id, message=None: (
                seen.append((requester_id, target_user_id, message))
                or _row(
                    user_low=requester_id,
                    user_high=target_user_id,
                    initiator_user_id=requester_id,
                    message=message,
                )
            )
        ),
    )

    result = registry.get("request_relationship").handler(
        "human-user-1",
        "I want to join the planning group.",
    )

    assert seen == [("agent-user-1", "human-user-1", "I want to join the planning group.")]
    assert "message: I want to join the planning group." in result


def test_approve_relationship_uses_current_identity_and_request_initiator() -> None:
    seen: list[tuple[str, str]] = []
    relationship = {
        "id": "hire_visit:agent-user-1:human-user-1",
        "user_low": "agent-user-1",
        "user_high": "human-user-1",
        "state": "pending",
        "initiator_user_id": "human-user-1",
    }
    service = SimpleNamespace(
        get_by_id=lambda relationship_id: relationship if relationship_id == relationship["id"] else None,
        approve=lambda approver_id, requester_id: seen.append((approver_id, requester_id)) or _row(state="visit"),
    )
    registry = ToolRegistry()
    RelationshipToolService(
        registry=registry,
        relationship_identity_id="agent-user-1",
        relationship_service=service,
    )

    result = registry.get("approve_relationship").handler("hire_visit:agent-user-1:human-user-1")

    assert seen == [("agent-user-1", "human-user-1")]
    assert "approved" in result
    assert "state: visit" in result


def test_reject_relationship_refuses_to_decide_unrelated_relationship() -> None:
    registry = ToolRegistry()
    RelationshipToolService(
        registry=registry,
        relationship_identity_id="agent-user-1",
        relationship_service=SimpleNamespace(
            get_by_id=lambda _relationship_id: {
                "id": "hire_visit:human-user-1:human-user-2",
                "user_low": "human-user-1",
                "user_high": "human-user-2",
                "state": "pending",
                "initiator_user_id": "human-user-1",
            }
        ),
    )

    result = registry.get("reject_relationship").handler("hire_visit:human-user-1:human-user-2")

    assert result == "Relationship not found for your user."
