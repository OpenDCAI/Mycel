from __future__ import annotations

from typing import Any

from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema


class RelationshipToolService:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        relationship_identity_id: str,
        relationship_service: Any,
    ) -> None:
        if not relationship_identity_id:
            raise ValueError("RelationshipToolService requires relationship_identity_id")
        if relationship_service is None:
            raise ValueError("RelationshipToolService requires relationship_service")
        self._identity_id = relationship_identity_id
        self._relationships = relationship_service
        self._register(registry)

    def _register(self, registry: ToolRegistry) -> None:
        self._register_list_relationships(registry)
        self._register_request_relationship(registry)
        self._register_approve_relationship(registry)
        self._register_reject_relationship(registry)

    def _register_list_relationships(self, registry: ToolRegistry) -> None:
        def handle() -> str:
            rows = self._relationships.list_for_user(self._identity_id)
            if not rows:
                return "No relationships found."
            return "\n".join(self._format_row(row) for row in rows)

        registry.register(
            ToolEntry(
                name="list_relationships",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="list_relationships",
                    description=(
                        "List relationship requests and active relationships for your current Mycel user identity. "
                        "Use this before approving or rejecting a pending request."
                    ),
                    properties={},
                ),
                handler=handle,
                source="relationship",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    def _register_request_relationship(self, registry: ToolRegistry) -> None:
        def handle(target_user_id: str, message: str | None = None) -> str:
            row = self._relationships.request(self._identity_id, target_user_id, message)
            return f"Requested relationship with {target_user_id}. {self._format_row(row)}"

        registry.register(
            ToolEntry(
                name="request_relationship",
                mode=ToolMode.INLINE,
                schema=make_tool_schema(
                    name="request_relationship",
                    description="Create a pending relationship request from your current Mycel user to another user.",
                    properties={
                        "target_user_id": {
                            "type": "string",
                            "description": "Target Mycel user id to request a relationship with.",
                            "minLength": 1,
                        },
                        "message": {
                            "type": "string",
                            "description": "Optional natural-language reason for the relationship request.",
                        },
                    },
                    required=["target_user_id"],
                ),
                handler=handle,
                source="relationship",
            )
        )

    def _register_approve_relationship(self, registry: ToolRegistry) -> None:
        def handle(relationship_id: str) -> str:
            existing, error = self._pending_decision_relationship(relationship_id)
            if error is not None:
                return error
            requester_id = existing["initiator_user_id"]
            row = self._relationships.approve(self._identity_id, requester_id)
            return f"Relationship approved. {self._format_row(row)}"

        registry.register(
            ToolEntry(
                name="approve_relationship",
                mode=ToolMode.INLINE,
                schema=self._decision_schema("approve_relationship", "Approve a pending relationship request sent to your user."),
                handler=handle,
                source="relationship",
            )
        )

    def _register_reject_relationship(self, registry: ToolRegistry) -> None:
        def handle(relationship_id: str) -> str:
            existing, error = self._pending_decision_relationship(relationship_id)
            if error is not None:
                return error
            requester_id = existing["initiator_user_id"]
            row = self._relationships.reject(self._identity_id, requester_id)
            return f"Relationship rejected. {self._format_row(row)}"

        registry.register(
            ToolEntry(
                name="reject_relationship",
                mode=ToolMode.INLINE,
                schema=self._decision_schema("reject_relationship", "Reject a pending relationship request sent to your user."),
                handler=handle,
                source="relationship",
            )
        )

    def _decision_schema(self, name: str, description: str) -> dict[str, Any]:
        return make_tool_schema(
            name=name,
            description=description,
            properties={
                "relationship_id": {
                    "type": "string",
                    "description": "Relationship id from list_relationships.",
                    "minLength": 1,
                }
            },
            required=["relationship_id"],
        )

    def _pending_decision_relationship(self, relationship_id: str) -> tuple[dict[str, Any], None] | tuple[None, str]:
        existing = self._relationships.get_by_id(relationship_id)
        if existing is None or self._identity_id not in (existing.get("user_low"), existing.get("user_high")):
            return None, "Relationship not found for your user."
        if existing.get("state") != "pending":
            return None, "Relationship is not pending."
        requester_id = existing.get("initiator_user_id")
        if not requester_id:
            return None, "Relationship request is missing requester."
        if requester_id == self._identity_id:
            return None, "You cannot approve or reject your own relationship request."
        return existing, None

    def _format_row(self, row: Any) -> str:
        relationship_id = self._field(row, "id")
        user_low = self._field(row, "user_low")
        user_high = self._field(row, "user_high")
        state = self._field(row, "state")
        initiator_user_id = self._field(row, "initiator_user_id")
        if self._identity_id == user_low:
            other_user_id = user_high
        elif self._identity_id == user_high:
            other_user_id = user_low
        else:
            raise RuntimeError(f"Relationship row does not include current user: {relationship_id}")
        direction = ""
        if state == "pending":
            direction = "incoming pending request" if initiator_user_id != self._identity_id else "outgoing pending request"
        else:
            direction = f"{state} relationship"
        message = self._field(row, "message", default=None)
        suffix = f"; message: {message}" if message else ""
        return f"- {direction}; relationship_id: {relationship_id}; other_user_id: {other_user_id}; state: {state}{suffix}"

    def _field(self, row: Any, field: str, *, default: Any = ...) -> Any:
        if isinstance(row, dict):
            if default is ...:
                return row[field]
            return row.get(field, default)
        if default is ...:
            return getattr(row, field)
        return getattr(row, field, default)
