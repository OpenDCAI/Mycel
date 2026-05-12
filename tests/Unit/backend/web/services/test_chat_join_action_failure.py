from __future__ import annotations

from backend.chat.api.http.chats_router import _map_chat_join_error
from messaging.join_requests import ChatJoinRequestActionError


def test_chat_join_action_failure_maps_to_structured_http_error() -> None:
    error = ChatJoinRequestActionError(
        action="reject",
        row={
            "id": "request-1",
            "chat_id": "chat-1",
            "requester_user_id": "visitor-1",
            "state": "rejected",
        },
    )

    mapped = _map_chat_join_error(error)

    assert mapped.status_code == 500
    assert mapped.detail == {
        "error": "chat_join_action_failed",
        "action": "reject",
        "row": {
            "id": "request-1",
            "chat_id": "chat-1",
            "requester_user_id": "visitor-1",
            "state": "rejected",
        },
        "cause": "Chat join action failed after reject",
    }
