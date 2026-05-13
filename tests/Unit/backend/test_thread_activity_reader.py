from types import SimpleNamespace

from backend.threads.chat_adapters.activity_reader import AppRuntimeThreadActivityReader
from core.runtime.middleware.monitor import AgentState


def test_thread_activity_reader_uses_explicit_thread_repo_and_agent_pool():
    thread_repo = SimpleNamespace(
        list_by_agent_user=lambda agent_user_id: (
            [
                {"id": "thread-1", "is_main": True, "branch_index": 0},
                {"id": "thread-2", "is_main": False, "branch_index": 1},
            ]
            if agent_user_id == "agent-user-1"
            else []
        )
    )
    agent_pool = {
        "thread-1:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.ACTIVE)),
        "thread-2:local": SimpleNamespace(runtime=SimpleNamespace(current_state=AgentState.IDLE)),
    }

    reader = AppRuntimeThreadActivityReader(thread_repo=thread_repo, agent_pool=agent_pool)

    activities = reader.list_active_threads_for_agent("agent-user-1")

    assert [(row.thread_id, row.is_main, row.branch_index, row.state) for row in activities] == [
        ("thread-1", True, 0, "active"),
        ("thread-2", False, 1, "idle"),
    ]
