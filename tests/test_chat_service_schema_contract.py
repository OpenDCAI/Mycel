from __future__ import annotations

from backend.web.services.chat_service import ChatService
from storage.contracts import ChatRow


class CapturingChatRepo:
    def __init__(self) -> None:
        self.created: list[ChatRow] = []

    def create(self, row: ChatRow) -> None:
        self.created.append(row)

    def get_by_id(self, chat_id: str) -> ChatRow | None:
        return next((row for row in self.created if row.id == chat_id), None)


class EmptyChatEntityRepo:
    def __init__(self) -> None:
        self.participants: list[tuple[str, str]] = []

    def find_chat_between(self, user_a: str, user_b: str) -> str | None:
        return None

    def add_participant(self, chat_id: str, user_id: str, joined_at: float) -> None:
        self.participants.append((chat_id, user_id))


class EmptyMessageRepo:
    pass


class EmptyEntityRepo:
    pass


class EmptyMemberRepo:
    pass


def test_chat_service_sets_direct_chat_type_and_creator() -> None:
    chats = CapturingChatRepo()
    service = ChatService(chats, EmptyChatEntityRepo(), EmptyMessageRepo(), EmptyEntityRepo(), EmptyMemberRepo())

    service.find_or_create_chat(["human_1", "agent_1"], created_by_user_id="human_1")

    assert chats.created[0].type == "direct"
    assert chats.created[0].created_by_user_id == "human_1"


def test_chat_service_sets_group_chat_type_and_creator() -> None:
    chats = CapturingChatRepo()
    service = ChatService(chats, EmptyChatEntityRepo(), EmptyMessageRepo(), EmptyEntityRepo(), EmptyMemberRepo())

    service.create_group_chat(["human_1", "agent_1", "agent_2"], "group", created_by_user_id="human_1")

    assert chats.created[0].type == "group"
    assert chats.created[0].created_by_user_id == "human_1"
