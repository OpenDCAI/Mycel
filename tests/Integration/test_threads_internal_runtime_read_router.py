from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.threads.api.http import internal_agent_actor_router, internal_runtime_read_router
from protocols.runtime_read import AgentThreadActivity, HireConversation


def test_internal_runtime_read_router_dispatches_lookup_and_conversation_reads() -> None:
    class _ActivityReader:
        def list_active_threads_for_agent(self, agent_user_id: str):
            assert agent_user_id == "agent-user-1"
            return [
                AgentThreadActivity(
                    thread_id="thread-1",
                    is_main=True,
                    branch_index=0,
                    state="active",
                )
            ]

    class _ConversationReader:
        async def list_hire_conversations_for_user(self, user_id: str):
            assert user_id == "owner-1"
            return [
                HireConversation(
                    id="thread-1",
                    title="Agent",
                    avatar_url=None,
                    updated_at="2026-04-22T10:00:00+00:00",
                    running=True,
                )
            ]

    class _AgentActorLookup:
        def is_agent_actor_user(self, social_user_id: str) -> bool:
            return social_user_id == "agent-social-1"

    app = FastAPI()
    app.state.threads_runtime_state = SimpleNamespace(
        activity_reader=_ActivityReader(),
        conversation_reader=_ConversationReader(),
        agent_actor_lookup=_AgentActorLookup(),
    )
    app.include_router(internal_runtime_read_router.router)
    app.include_router(internal_agent_actor_router.router)

    with TestClient(app) as client:
        activity_response = client.get("/api/internal/thread-runtime/activities", params={"agent_user_id": "agent-user-1"})
        conversation_response = client.get("/api/internal/thread-runtime/conversations/hire", params={"user_id": "owner-1"})
        lookup_response = client.get("/api/internal/identity/agent-actors/agent-social-1/exists")

    assert activity_response.status_code == 200
    assert activity_response.json() == [
        {
            "thread_id": "thread-1",
            "is_main": True,
            "branch_index": 0,
            "state": "active",
        }
    ]
    assert conversation_response.status_code == 200
    assert conversation_response.json() == [
        {
            "id": "thread-1",
            "title": "Agent",
            "avatar_url": None,
            "updated_at": "2026-04-22T10:00:00+00:00",
            "running": True,
        }
    ]
    assert lookup_response.json() == {"exists": True}
