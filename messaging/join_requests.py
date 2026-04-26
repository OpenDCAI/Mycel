from __future__ import annotations

from typing import Any


class ChatJoinRequestService:
    def __init__(
        self,
        *,
        chat_repo: Any,
        chat_member_repo: Any,
        chat_join_request_repo: Any,
        messaging_service: Any,
        on_join_request_rejected: Any | None = None,
    ) -> None:
        self._chats = chat_repo
        self._members = chat_member_repo
        self._requests = chat_join_request_repo
        self._messaging = messaging_service
        self._on_join_request_rejected = on_join_request_rejected

    def set_join_request_rejected_notification_fn(self, fn: Any) -> None:
        self._on_join_request_rejected = fn

    def request(self, chat_id: str, requester_user_id: str, message: str | None = None) -> dict[str, Any]:
        chat = self._require_joinable_chat(chat_id)
        if self._members.is_member(chat_id, requester_user_id):
            raise ValueError("Already a participant of this chat")
        row = self._requests.upsert_request(chat_id, requester_user_id, message=message)
        owner_id = chat.created_by_user_id
        self._messaging.send(
            chat_id,
            requester_user_id,
            self._request_notification(requester_user_id, message),
            message_type="notification",
            mentions=[owner_id],
        )
        return self._project_request(row)

    def join_target(self, chat_id: str, viewer_user_id: str) -> dict[str, Any]:
        chat = self._require_joinable_chat(chat_id)
        current_request = next(
            (self._project_request(row) for row in self._requests.list_for_chat(chat_id) if row.get("requester_user_id") == viewer_user_id),
            None,
        )
        return {
            "id": chat.id,
            "type": chat.type,
            "title": chat.title,
            "status": chat.status,
            "created_by_user_id": chat.created_by_user_id,
            "is_member": self._members.is_member(chat_id, viewer_user_id),
            "current_request": current_request,
        }

    def list_for_chat(self, chat_id: str, viewer_user_id: str) -> list[dict[str, Any]]:
        self._require_chat_owner(chat_id, viewer_user_id)
        return [self._project_request(row) for row in self._requests.list_for_chat(chat_id)]

    def approve(self, chat_id: str, request_id: str, approver_user_id: str) -> dict[str, Any]:
        self._require_chat_owner(chat_id, approver_user_id)
        request = self._require_pending_request(chat_id, request_id)
        requester_user_id = request["requester_user_id"]
        self._members.add_member(chat_id, requester_user_id)
        row = self._requests.set_state(request_id, state="approved", decided_by_user_id=approver_user_id)
        self._messaging.send(
            chat_id,
            approver_user_id,
            f"Approved chat join request for {requester_user_id}.",
            message_type="notification",
            mentions=[requester_user_id],
        )
        return self._project_request(row)

    def reject(self, chat_id: str, request_id: str, rejecter_user_id: str) -> dict[str, Any]:
        self._require_chat_owner(chat_id, rejecter_user_id)
        request = self._require_pending_request(chat_id, request_id)
        requester_user_id = request["requester_user_id"]
        row = self._requests.set_state(request_id, state="rejected", decided_by_user_id=rejecter_user_id)
        self._messaging.send(
            chat_id,
            rejecter_user_id,
            f"Rejected chat join request for {requester_user_id}.",
            message_type="notification",
            mentions=[requester_user_id],
        )
        if self._on_join_request_rejected is not None:
            self._on_join_request_rejected(row)
        return self._project_request(row)

    def _require_joinable_chat(self, chat_id: str) -> Any:
        chat = self._chats.get_by_id(chat_id)
        if chat is None:
            raise LookupError("Chat not found")
        if chat.type != "group":
            raise ValueError("Join requests are only supported for group chats")
        if chat.status != "active":
            raise ValueError("Chat is not active")
        return chat

    def _require_chat_owner(self, chat_id: str, user_id: str) -> Any:
        chat = self._require_joinable_chat(chat_id)
        if chat.created_by_user_id != user_id:
            raise PermissionError("Only the chat owner can manage join requests")
        return chat

    def _require_pending_request(self, chat_id: str, request_id: str) -> dict[str, Any]:
        request = self._requests.get_by_id(request_id)
        if request is None or request.get("chat_id") != chat_id:
            raise LookupError("Chat join request not found")
        if request.get("state") != "pending":
            raise ValueError("Chat join request is not pending")
        return request

    def _request_notification(self, requester_user_id: str, message: str | None) -> str:
        if message and message.strip():
            return f"{requester_user_id} requested to join this chat: {message.strip()}"
        return f"{requester_user_id} requested to join this chat."

    def _project_request(self, row: dict[str, Any]) -> dict[str, Any]:
        projected = dict(row)
        requester_user_id = str(projected.get("requester_user_id") or "")
        requester = self._messaging.resolve_display_user(requester_user_id) if requester_user_id else None
        if requester is not None:
            projected["requester_name"] = requester.display_name
            requester_type = getattr(requester, "type", None)
            projected["requester_type"] = requester_type.value if hasattr(requester_type, "value") else str(requester_type)
        return projected
