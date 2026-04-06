from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from core.agents.communication.chat_tool_service import ChatToolService
from core.runtime.agent import LeonAgent
from core.runtime.registry import ToolRegistry
from storage.contracts import MemberRow, MemberType


class _MemberRepo:
    def __init__(self, members: list[MemberRow]) -> None:
        self._members = {member.id: member for member in members}

    def get_by_id(self, member_id: str) -> MemberRow | None:
        return self._members.get(member_id)

    def list_all(self) -> list[MemberRow]:
        return list(self._members.values())


def test_chat_tool_registry_exposes_only_canonical_chat_surface() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry,
        user_id="m_agent",
        owner_user_id="u_owner",
        chat_service=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )

    for tool_name in ("list_chats", "read_messages", "send_message", "search_messages"):
        assert registry.get(tool_name) is not None

    assert registry.get("chats") is None
    assert registry.get("read_message") is None
    assert registry.get("search_message") is None
    assert registry.get("directory") is None


def test_compose_system_prompt_hardens_chat_reply_contract() -> None:
    agent = LeonAgent.__new__(LeonAgent)
    agent._chat_repos = {
        "user_id": "m_agent",
        "owner_user_id": "u_owner",
        "member_repo": _MemberRepo(
            [
                MemberRow(id="u_owner", name="Owner", type=MemberType.HUMAN, created_at=1.0),
                MemberRow(id="m_agent", name="Helper Member", type=MemberType.MYCEL_AGENT, owner_user_id="u_owner", created_at=2.0),
            ]
        ),
    }
    agent._build_system_prompt = lambda: "BASE"
    agent.config = SimpleNamespace(system_prompt=None)

    prompt = agent._compose_system_prompt()

    assert "you MUST read it with read_messages()" in prompt
    assert "prefer using that exact chat_id directly" in prompt
    assert "you MUST call send_message()" in prompt
    assert "Never claim you replied unless send_message() succeeded." in prompt
    assert "directory" not in prompt


def test_read_messages_validate_input_fills_missing_chat_id_from_latest_notification() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry,
        user_id="m_agent",
        owner_user_id="u_owner",
        chat_service=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )
    entry = registry.get("read_messages")
    assert entry is not None
    assert entry.validate_input is not None

    request = SimpleNamespace(
        state=SimpleNamespace(
            messages=[
                HumanMessage(
                    content=(
                        "<system-reminder>\n"
                        "New message from alice in chat chat-123 (1 unread).\n"
                        'Read it with read_messages(chat_id="chat-123").\n'
                        "</system-reminder>"
                    ),
                    metadata={"source": "external", "notification_type": "chat"},
                )
            ]
        )
    )

    args = entry.validate_input({"chat_id": "", "range": "-10:"}, request)

    assert args == {"chat_id": "chat-123", "range": "-10:"}


def test_send_message_validate_input_fills_missing_chat_id_from_latest_notification() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry,
        user_id="m_agent",
        owner_user_id="u_owner",
        chat_service=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )
    entry = registry.get("send_message")
    assert entry is not None
    assert entry.validate_input is not None

    request = SimpleNamespace(
        state=SimpleNamespace(
            messages=[
                HumanMessage(
                    content=(
                        "<system-reminder>\n"
                        "New message from alice in chat chat-456 (1 unread).\n"
                        'Read it with read_messages(chat_id="chat-456").\n'
                        'Reply with send_message(chat_id="chat-456", content="...").\n'
                        "</system-reminder>"
                    ),
                    metadata={"source": "external", "notification_type": "chat"},
                )
            ]
        )
    )

    args = entry.validate_input({"content": "hi", "chat_id": ""}, request)

    assert args == {"content": "hi", "chat_id": "chat-456"}
