from __future__ import annotations

from types import SimpleNamespace

from messaging.delivery.runtime_thread_selector import select_runtime_thread_for_recipient


def test_selector_prefers_latest_live_child_thread_over_active_main() -> None:
    thread_repo = SimpleNamespace(
        get_by_user_id=lambda uid: {"id": "thread-main", "agent_user_id": "agent-user-1"} if uid == "agent-user-1" else None,
        list_by_agent_user=lambda uid: (
            [
                {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0},
                {"id": "thread-child-old", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 1},
                {"id": "thread-child-fresh", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 2},
            ]
            if uid == "agent-user-1"
            else []
        ),
    )
    activity_reader = SimpleNamespace(
        list_active_threads_for_agent=lambda _agent_user_id: [
            SimpleNamespace(thread_id="thread-main", is_main=True, branch_index=0, state="active"),
            SimpleNamespace(thread_id="thread-child-old", is_main=False, branch_index=1, state="idle"),
            SimpleNamespace(thread_id="thread-child-fresh", is_main=False, branch_index=2, state="ready"),
        ]
    )

    selected = select_runtime_thread_for_recipient(
        "agent-user-1",
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )

    assert selected == "thread-child-fresh"


def test_selector_falls_back_to_default_thread_when_no_live_runtime_candidate_exists() -> None:
    default_thread = {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}
    thread_repo = SimpleNamespace(
        get_by_user_id=lambda uid: default_thread if uid == "agent-user-1" else None,
        list_by_agent_user=lambda uid: [default_thread] if uid == "agent-user-1" else [],
    )
    activity_reader = SimpleNamespace(list_active_threads_for_agent=lambda _agent_user_id: [])

    selected = select_runtime_thread_for_recipient(
        "agent-user-1",
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )

    assert selected == "thread-main"
