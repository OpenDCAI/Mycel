from __future__ import annotations

from types import SimpleNamespace

from core.runtime.registry import ToolRegistry
from messaging.tools.chat_join_request_tool_service import ChatJoinRequestToolService


def _request_row(
    *,
    request_id: str = "chat_join:chat-1:visitor-1",
    chat_id: str = "chat-1",
    requester_user_id: str = "visitor-1",
    state: str = "pending",
    message: str | None = "please add me",
):
    return {
        "id": request_id,
        "chat_id": chat_id,
        "requester_user_id": requester_user_id,
        "state": state,
        "message": message,
    }


def test_chat_join_request_tool_service_registers_owner_tools_without_identity_arguments() -> None:
    registry = ToolRegistry()
    ChatJoinRequestToolService(
        registry=registry,
        chat_join_identity_id="agent-owner-1",
        chat_join_request_service=SimpleNamespace(list_for_chat=lambda _chat_id, _owner_id: []),
    )

    for tool_name in ("list_chat_join_requests", "approve_chat_join_request", "reject_chat_join_request"):
        tool = registry.get(tool_name)
        assert tool is not None
        assert "user_id" not in tool.get_schema()["parameters"]["properties"]
        assert "owner_id" not in tool.get_schema()["parameters"]["properties"]


def test_list_chat_join_requests_renders_request_ids_and_messages() -> None:
    registry = ToolRegistry()
    ChatJoinRequestToolService(
        registry=registry,
        chat_join_identity_id="agent-owner-1",
        chat_join_request_service=SimpleNamespace(list_for_chat=lambda chat_id, owner_id: [_request_row(chat_id=chat_id)]),
    )

    result = registry.get("list_chat_join_requests").handler("chat-1")

    assert "request_id: chat_join:chat-1:visitor-1" in result
    assert "requester_user_id: visitor-1" in result
    assert "state: pending" in result
    assert "message: please add me" in result


def test_approve_chat_join_request_uses_current_identity() -> None:
    seen: list[tuple[str, str, str]] = []
    registry = ToolRegistry()
    ChatJoinRequestToolService(
        registry=registry,
        chat_join_identity_id="agent-owner-1",
        chat_join_request_service=SimpleNamespace(
            approve=lambda chat_id, request_id, owner_id: seen.append((chat_id, request_id, owner_id)) or _request_row(state="approved")
        ),
    )

    result = registry.get("approve_chat_join_request").handler("chat-1", "chat_join:chat-1:visitor-1")

    assert seen == [("chat-1", "chat_join:chat-1:visitor-1", "agent-owner-1")]
    assert "approved" in result


def test_reject_chat_join_request_uses_current_identity() -> None:
    seen: list[tuple[str, str, str]] = []
    registry = ToolRegistry()
    ChatJoinRequestToolService(
        registry=registry,
        chat_join_identity_id="agent-owner-1",
        chat_join_request_service=SimpleNamespace(
            reject=lambda chat_id, request_id, owner_id: seen.append((chat_id, request_id, owner_id)) or _request_row(state="rejected")
        ),
    )

    result = registry.get("reject_chat_join_request").handler("chat-1", "chat_join:chat-1:visitor-1")

    assert seen == [("chat-1", "chat_join:chat-1:visitor-1", "agent-owner-1")]
    assert "rejected" in result
