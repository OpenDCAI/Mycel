from types import SimpleNamespace

from backend.monitor.application.use_cases import thread_workbench


def _reader(
    *,
    rows,
    runtime_states,
    converge_calls,
):
    return SimpleNamespace(
        list_owner_thread_rows=lambda _user_id: rows,
        converge_runtime_state=lambda thread_id: converge_calls.append(thread_id) or runtime_states[thread_id],
        is_runtime_active=lambda _thread_id, _sandbox_type: False,
        last_active_at=lambda _thread_id: None,
        canonical_owner_threads=lambda group: sorted(
            group,
            key=lambda row: (
                not bool(row.get("is_main", False)),
                int(row.get("branch_index", 0)),
            ),
        )[:1],
        avatar_url=lambda _agent_user_id, _has_avatar: None,
    )


def test_build_owner_thread_workbench_avoids_eager_runtime_summary_scan():
    rows = [
        {"id": "thread-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "thread-branch", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
        {"id": "thread-other", "agent_user_id": "agent-2", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={
            "thread-main": "ready",
            "thread-branch": "ready",
            "thread-other": "ready",
        },
        converge_calls=converge_calls,
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["thread-main", "thread-other"]
    assert converge_calls == ["thread-main", "thread-other"]


def test_build_owner_thread_workbench_falls_through_to_next_candidate_when_preferred_thread_is_purged():
    rows = [
        {"id": "thread-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "thread-branch", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={
            "thread-main": "purged",
            "thread-branch": "ready",
        },
        converge_calls=converge_calls,
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["thread-branch"]
    assert converge_calls == ["thread-main", "thread-branch"]


def test_build_owner_thread_workbench_skips_internal_child_threads_before_runtime_checks():
    rows = [
        {"id": "subagent-hidden", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
        {"id": "thread-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={
            "thread-main": "ready",
        },
        converge_calls=converge_calls,
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["thread-main"]
    assert converge_calls == ["thread-main"]


def test_build_owner_thread_workbench_requires_agent_user_id_for_visible_threads():
    rows = [
        {"id": "thread-main", "agent_user_id": "", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={},
        converge_calls=converge_calls,
    )

    try:
        thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)
    except RuntimeError as exc:
        assert "missing agent_user_id" in str(exc)
    else:
        raise AssertionError("expected owner-visible thread rows without agent_user_id to fail loudly")


def test_build_owner_thread_workbench_preserves_agent_order_across_fallback_selection():
    rows = [
        {"id": "agent-1-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "agent-2-main", "agent_user_id": "agent-2", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "agent-1-branch", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={
            "agent-1-main": "purged",
            "agent-1-branch": "ready",
            "agent-2-main": "ready",
        },
        converge_calls=converge_calls,
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["agent-2-main", "agent-1-branch"]


def test_build_owner_thread_workbench_omits_agent_groups_with_no_visible_runtime_candidate():
    rows = [
        {"id": "agent-1-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "agent-1-branch", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
        {"id": "agent-2-main", "agent_user_id": "agent-2", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
    ]
    reader = _reader(
        rows=rows,
        runtime_states={
            "agent-1-main": "purged",
            "agent-1-branch": "missing",
            "agent-2-main": "ready",
        },
        converge_calls=[],
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["agent-2-main"]


def test_build_owner_thread_workbench_stops_after_first_ready_candidate_per_agent():
    rows = [
        {"id": "agent-1-main", "agent_user_id": "agent-1", "is_main": True, "branch_index": 0, "sandbox_type": "local"},
        {"id": "agent-1-branch-1", "agent_user_id": "agent-1", "is_main": False, "branch_index": 1, "sandbox_type": "local"},
        {"id": "agent-1-branch-2", "agent_user_id": "agent-1", "is_main": False, "branch_index": 2, "sandbox_type": "local"},
    ]
    converge_calls: list[str] = []
    reader = _reader(
        rows=rows,
        runtime_states={
            "agent-1-main": "ready",
            "agent-1-branch-1": "ready",
            "agent-1-branch-2": "ready",
        },
        converge_calls=converge_calls,
    )

    payload = thread_workbench.build_owner_thread_workbench_from_rows(rows, reader=reader)

    assert [thread["thread_id"] for thread in payload["threads"]] == ["agent-1-main"]
    assert converge_calls == ["agent-1-main"]
