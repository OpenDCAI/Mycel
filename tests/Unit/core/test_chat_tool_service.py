from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from core.agents.communication.chat_tool_service import ChatToolService
from core.runtime.agent import LeonAgent
from core.runtime.registry import ToolRegistry
from storage.contracts import EntityRow, MemberRow, MemberType


class _EntityRepo:
    def __init__(self, entities: list[EntityRow]) -> None:
        self._entities = {entity.id: entity for entity in entities}

    def list_all(self) -> list[EntityRow]:
        return list(self._entities.values())

    def get_by_id(self, entity_id: str) -> EntityRow | None:
        return self._entities.get(entity_id)


class _MemberRepo:
    def __init__(self, members: list[MemberRow]) -> None:
        self._members = {member.id: member for member in members}

    def get_by_id(self, member_id: str) -> MemberRow | None:
        return self._members.get(member_id)


def test_directory_uses_owner_user_id_for_agent_owner_lookup() -> None:
    owner_member = MemberRow(
        id="u_owner",
        name="Owner",
        type=MemberType.HUMAN,
        created_at=1.0,
    )
    agent_member = MemberRow(
        id="m_agent",
        name="Agent Member",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u_owner",
        created_at=2.0,
    )
    owner_entity = EntityRow(id="e_owner", type="human", member_id="u_owner", name="Owner", created_at=1.0)
    agent_entity = EntityRow(id="e_agent", type="agent", member_id="m_agent", name="Helper", created_at=2.0)

    service = ChatToolService(
        ToolRegistry(),
        entity_id="e_owner",
        owner_entity_id="e_owner",
        entity_repo=_EntityRepo([owner_entity, agent_entity]),
        chat_service=SimpleNamespace(),
        chat_entity_repo=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([owner_member, agent_member]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )

    result = service._handle_directory(type="agent")

    assert "Helper" in result
    assert "(owner: Owner)" in result


def test_compose_system_prompt_hardens_chat_reply_contract() -> None:
    owner_entity = EntityRow(id="e_owner", type="human", member_id="u_owner", name="Owner", created_at=1.0)
    agent_entity = EntityRow(id="e_agent", type="agent", member_id="m_agent", name="Helper", created_at=2.0)

    agent = LeonAgent.__new__(LeonAgent)
    agent._chat_repos = {
        "entity_id": "e_agent",
        "owner_entity_id": "e_owner",
        "entity_repo": _EntityRepo([owner_entity, agent_entity]),
    }
    agent._build_system_prompt = lambda: "BASE"
    agent.config = SimpleNamespace(system_prompt=None)

    prompt = agent._compose_system_prompt()

    assert "you MUST read it with chat_read()" in prompt
    assert "prefer using that exact chat_id directly" in prompt
    assert "you MUST call chat_send()" in prompt
    assert "Never claim you replied unless chat_send() succeeded." in prompt


def test_chat_read_validate_input_fills_missing_chat_id_from_latest_notification() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry,
        entity_id="e_agent",
        owner_entity_id="e_owner",
        entity_repo=_EntityRepo([]),
        chat_service=SimpleNamespace(),
        chat_entity_repo=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )
    entry = registry.get("chat_read")
    assert entry is not None
    assert entry.validate_input is not None

    request = SimpleNamespace(
        state=SimpleNamespace(
            messages=[
                HumanMessage(
                    content=(
                        "<system-reminder>\n"
                        "New message from alice in chat chat-123 (1 unread).\n"
                        'Read it with chat_read(chat_id="chat-123").\n'
                        "</system-reminder>"
                    ),
                    metadata={"source": "external", "notification_type": "chat"},
                )
            ]
        )
    )

    args = entry.validate_input({"chat_id": "", "range": "-10:"}, request)

    assert args == {"chat_id": "chat-123", "range": "-10:"}


def test_chat_send_validate_input_fills_missing_chat_id_from_latest_notification() -> None:
    registry = ToolRegistry()
    ChatToolService(
        registry,
        entity_id="e_agent",
        owner_entity_id="e_owner",
        entity_repo=_EntityRepo([]),
        chat_service=SimpleNamespace(),
        chat_entity_repo=SimpleNamespace(),
        chat_message_repo=SimpleNamespace(),
        member_repo=_MemberRepo([]),
        chat_event_bus=SimpleNamespace(),
        runtime_fn=lambda: None,
    )
    entry = registry.get("chat_send")
    assert entry is not None
    assert entry.validate_input is not None

    request = SimpleNamespace(
        state=SimpleNamespace(
            messages=[
                HumanMessage(
                    content=(
                        "<system-reminder>\n"
                        "New message from alice in chat chat-456 (1 unread).\n"
                        'Read it with chat_read(chat_id="chat-456").\n'
                        'Reply with chat_send(chat_id="chat-456", content="...").\n'
                        "</system-reminder>"
                    ),
                    metadata={"source": "external", "notification_type": "chat"},
                )
            ]
        )
    )

    args = entry.validate_input({"content": "hi", "chat_id": ""}, request)

    assert args == {"content": "hi", "chat_id": "chat-456"}
