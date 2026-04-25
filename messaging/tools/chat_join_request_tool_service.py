from __future__ import annotations

from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema


class ChatJoinRequestToolService:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        chat_join_identity_id: str,
        chat_join_request_service: Any,
    ) -> None:
        if not chat_join_identity_id:
            raise ValueError("ChatJoinRequestToolService requires chat_join_identity_id")
        if chat_join_request_service is None:
            raise ValueError("ChatJoinRequestToolService requires chat_join_request_service")
        self._identity_id = chat_join_identity_id
        self._join_requests = chat_join_request_service
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_list(registry)
        self._register_approve(registry)
        self._register_reject(registry)

    def _register_list(self, registry: ToolRegistry) -> None:
        def handle(chat_id: str) -> str:
            rows = self._join_requests.list_for_chat(chat_id, self._identity_id)
            if not rows:
                return "No chat join requests found."
            return "\n".join(self._format_row(row) for row in rows)

        registry.register(
            ToolEntry(
                name="list_chat_join_requests",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="list_chat_join_requests",
                    description=(
                        "List join requests for a group chat you own. Use the chat_id from the join request "
                        "notification or chat message before approving or rejecting a request."
                    ),
                    properties={
                        "chat_id": {
                            "type": "string",
                            "description": "Group chat id to inspect.",
                            "minLength": 1,
                        }
                    },
                    required=["chat_id"],
                ),
                handler=handle,
                source="chat_join_request",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    def _register_approve(self, registry: ToolRegistry) -> None:
        def handle(chat_id: str, request_id: str) -> str:
            row = self._join_requests.approve(chat_id, request_id, self._identity_id)
            return f"Chat join request approved. {self._format_row(row)}"

        registry.register(
            ToolEntry(
                name="approve_chat_join_request",
                mode=ToolMode.INLINE,
                schema=self._decision_schema("approve_chat_join_request", "Approve a pending join request for a group chat you own."),
                handler=handle,
                source="chat_join_request",
            )
        )

    def _register_reject(self, registry: ToolRegistry) -> None:
        def handle(chat_id: str, request_id: str) -> str:
            row = self._join_requests.reject(chat_id, request_id, self._identity_id)
            return f"Chat join request rejected. {self._format_row(row)}"

        registry.register(
            ToolEntry(
                name="reject_chat_join_request",
                mode=ToolMode.INLINE,
                schema=self._decision_schema("reject_chat_join_request", "Reject a pending join request for a group chat you own."),
                handler=handle,
                source="chat_join_request",
            )
        )

    def _decision_schema(self, name: str, description: str) -> dict[str, Any]:
        return make_tool_schema(
            name=name,
            description=description,
            properties={
                "chat_id": {
                    "type": "string",
                    "description": "Group chat id containing the join request.",
                    "minLength": 1,
                },
                "request_id": {
                    "type": "string",
                    "description": "Join request id from list_chat_join_requests.",
                    "minLength": 1,
                },
            },
            required=["chat_id", "request_id"],
        )

    def _format_row(self, row: Any) -> str:
        request_id = self._field(row, "id")
        chat_id = self._field(row, "chat_id")
        requester_user_id = self._field(row, "requester_user_id")
        state = self._field(row, "state")
        message = self._field(row, "message", default=None)
        suffix = f"; message: {message}" if message else ""
        return f"- request_id: {request_id}; chat_id: {chat_id}; requester_user_id: {requester_user_id}; state: {state}{suffix}"

    def _field(self, row: Any, field: str, *, default: Any = ...) -> Any:
        if isinstance(row, dict):
            if default is ...:
                return row[field]
            return row.get(field, default)
        if default is ...:
            return getattr(row, field)
        return getattr(row, field, default)
