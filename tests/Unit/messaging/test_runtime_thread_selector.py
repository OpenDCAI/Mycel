from __future__ import annotations

from types import SimpleNamespace

from backend.threads.agent_actor_routing import select_runtime_thread_for_recipient


def test_selector_prefers_default_thread_over_live_child_thread_when_thread_not_explicitly_specified() -> None:
    thread_repo = SimpleNamespace(
        get_canonical_thread_for_agent_actor=lambda uid: {"id": "thread-main", "agent_user_id": "agent-user-1"} if uid == "agent-user-1" else None,
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

    selected = select_runtime_thread_for_recipient(
        "agent-user-1",
        thread_repo=thread_repo,
    )

    assert selected == "thread-main"


def test_selector_returns_none_when_agent_has_no_canonical_thread_even_if_live_child_exists() -> None:
    thread_repo = SimpleNamespace(
        get_canonical_thread_for_agent_actor=lambda _uid: None,
        list_by_agent_user=lambda uid: (
            [
                {"id": "thread-child-fresh", "agent_user_id": "agent-user-1", "is_main": False, "branch_index": 2},
            ]
            if uid == "agent-user-1"
            else []
        ),
    )

    selected = select_runtime_thread_for_recipient(
        "agent-user-1",
        thread_repo=thread_repo,
    )

    assert selected is None


def test_selector_returns_default_thread_when_no_live_runtime_candidate_exists() -> None:
    default_thread = {"id": "thread-main", "agent_user_id": "agent-user-1", "is_main": True, "branch_index": 0}
    thread_repo = SimpleNamespace(
        get_canonical_thread_for_agent_actor=lambda uid: default_thread if uid == "agent-user-1" else None,
        list_by_agent_user=lambda uid: [default_thread] if uid == "agent-user-1" else [],
    )

    selected = select_runtime_thread_for_recipient(
        "agent-user-1",
        thread_repo=thread_repo,
    )

    assert selected == "thread-main"
