"""messaging/contracts.py — canonical types for the messaging module.

All types are Pydantic v2, strict=True, frozen=True.
These types expose the current messaging social-id slot.
The long-term agent social-handle split is still pending.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# User — current messaging social-id record
# ---------------------------------------------------------------------------


class User(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    id: str  # current social-id slot; agent handle source still pending
    name: str
    avatar_url: str | None = None
    type: Literal["human", "agent"]
    owner_id: str | None = None  # owner user_id for agents; None for humans


class UserRepo(Protocol):
    """Resolve the current messaging social-id record. Reads from member-backed storage today."""

    def get_user(self, user_id: str) -> User | None: ...
    def list_users(self) -> list[User]: ...


# ---------------------------------------------------------------------------
# AI metadata
# ---------------------------------------------------------------------------


class AiMetadata(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    tool_calls: dict[str, int] = {}
    elapsed_seconds: float | None = None


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

MessageType = Literal["human", "ai", "ai_process", "system", "notification"]
ContentType = Literal["text", "markdown"]
SignalType = Literal["open", "yield", "close"]


class MessageRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    chat_id: str
    sender_id: str  # user_id
    content: str
    content_type: ContentType = "text"
    message_type: MessageType = "human"
    signal: SignalType | None = None
    mentions: list[str] = []
    reply_to: str | None = None
    ai_metadata: AiMetadata | None = None
    created_at: datetime
    delivered_at: datetime | None = None
    edited_at: datetime | None = None
    retracted_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_for: list[str] = []


# ---------------------------------------------------------------------------
# Chat + Member
# ---------------------------------------------------------------------------

ChatType = Literal["direct", "group"]
ChatStatus = Literal["active", "archived", "deleted"]
MemberRole = Literal["member", "admin"]


class ChatMemberRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    user_id: str
    role: MemberRole = "member"
    joined_at: datetime
    muted: bool = False
    mute_until: datetime | None = None
    last_read_at: datetime | None = None


class ChatRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str | None = None
    type: ChatType = "direct"
    status: ChatStatus = "active"
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

ContactRelation = Literal["normal", "blocked", "muted"]


class ContactRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_user_id: str
    target_user_id: str
    relation: ContactRelation = "normal"
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Relationship (Hire/Visit state machine)
# ---------------------------------------------------------------------------

RelationshipState = Literal["none", "pending", "visit", "hire"]
RelationshipEvent = Literal["request", "approve", "reject", "upgrade", "downgrade", "revoke"]


class RelationshipRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    user_low: str
    user_high: str
    kind: str = "hire_visit"
    state: RelationshipState = "none"
    initiator_user_id: str | None = None
    hire_granted_at: datetime | None = None
    hire_revoked_at: datetime | None = None
    hire_snapshot: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

DeliveryAction = Literal["deliver", "notify", "drop"]


class MessageSendStatus(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    status: Literal["sending", "sent", "delivered", "read", "retracted", "deleted"]
