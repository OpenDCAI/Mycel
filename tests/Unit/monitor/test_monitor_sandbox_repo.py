import pytest

from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient, FakeSupabaseQuery


class _BrokenSandboxInstancesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_instances":
            raise RuntimeError("sandbox_instances exploded")
        return super().table(table_name)


class _MaxInFilterQuery(FakeSupabaseQuery):
    def in_(self, column: str, values: list[object]):
        assert len(values) <= 80
        return super().in_(column, values)


class _MaxInFilterClient(FakeSupabaseClient):
    def table(self, table_name: str):
        query = _MaxInFilterQuery(table_name, self._tables)
        if table_name in self._auto_seq_tables:
            query._auto_seq = True
        return query


def _repo(tables: dict) -> SupabaseSandboxMonitorRepo:
    return SupabaseSandboxMonitorRepo(FakeSupabaseClient(tables))


def _lease(
    lease_id: str,
    *,
    provider_name: str = "local",
    desired_state: str = "running",
    observed_state: str = "running",
    current_instance_id: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    **extra,
) -> dict:
    row = {
        "lease_id": lease_id,
        "provider_name": provider_name,
        "desired_state": desired_state,
        "observed_state": observed_state,
        "current_instance_id": current_instance_id,
    }
    if created_at is not None:
        row["created_at"] = created_at
    if updated_at is not None:
        row["updated_at"] = updated_at
    row.update(extra)
    return row


def _session(
    session_id: str,
    thread_id: str,
    lease_id: str,
    *,
    status: str = "active",
    started_at: str | None = None,
    last_active_at: str | None = None,
) -> dict:
    row = {
        "chat_session_id": session_id,
        "thread_id": thread_id,
        "lease_id": lease_id,
        "status": status,
    }
    if started_at is not None:
        row["started_at"] = started_at
    if last_active_at is not None:
        row["last_active_at"] = last_active_at
    return row


def _terminal(terminal_id: str, lease_id: str, thread_id: str, created_at: str) -> dict:
    return {
        "terminal_id": terminal_id,
        "lease_id": lease_id,
        "thread_id": thread_id,
        "created_at": created_at,
    }


def test_query_threads_accepts_optional_thread_filter() -> None:
    repo = _repo(
        {
            "sandbox_leases": [_lease("lease-1", current_instance_id="instance-1")],
            "chat_sessions": [
                _session("sess-1", "thread-1", "lease-1", last_active_at="2026-04-05T10:01:00"),
                _session("sess-2", "thread-2", "lease-1", last_active_at="2026-04-05T10:06:00"),
            ],
        }
    )

    assert repo.query_threads(thread_id="thread-2") == [
        {
            "thread_id": "thread-2",
            "session_count": 1,
            "last_active": "2026-04-05T10:06:00",
            "lease_id": "lease-1",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "running",
            "current_instance_id": "instance-1",
        }
    ]


def test_query_leases_uses_latest_terminal_binding() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                _lease(
                    "lease-1",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    current_instance_id="instance-1",
                    updated_at="2026-04-05T10:10:00",
                    recipe_id=None,
                    recipe_json=None,
                    last_error=None,
                )
            ],
            "abstract_terminals": [
                _terminal("term-old", "lease-1", "thread-old", "2026-04-05T10:01:00"),
                _terminal("term-new", "lease-1", "thread-new", "2026-04-05T10:02:00"),
            ],
        }
    )

    assert repo.query_leases() == [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "updated_at": "2026-04-05T10:10:00",
            "recipe_id": None,
            "recipe_json": None,
            "last_error": None,
            "thread_id": "thread-new",
        }
    ]


def test_query_leases_chunks_terminal_binding_lookup() -> None:
    leases = [
        _lease(
            f"lease-{index}",
            updated_at=f"2026-04-05T10:{index % 60:02d}:00",
            recipe_id=None,
            recipe_json=None,
            last_error=None,
        )
        for index in range(175)
    ]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "sandbox_leases": leases,
                "abstract_terminals": [_terminal("term-174", "lease-174", "thread-174", "2026-04-05T10:02:00")],
            }
        )
    )

    rows = repo.query_leases()

    assert len(rows) == 175
    assert next(row for row in rows if row["lease_id"] == "lease-174")["thread_id"] == "thread-174"


def test_query_lease_threads_returns_latest_unique_threads_first() -> None:
    repo = _repo(
        {
            "abstract_terminals": [
                _terminal("term-old", "lease-1", "thread-old", "2026-04-05T10:01:00"),
                _terminal("term-new", "lease-1", "thread-new", "2026-04-05T10:02:00"),
                _terminal("term-dupe", "lease-1", "thread-new", "2026-04-05T10:03:00"),
            ]
        }
    )

    assert repo.query_lease_threads("lease-1") == [{"thread_id": "thread-new"}, {"thread_id": "thread-old"}]


def test_query_lease_instance_id_prefers_provider_session_id() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                _lease("lease-1", provider_name="daytona_selfhost", observed_state="detached", current_instance_id="instance-fallback")
            ],
            "sandbox_instances": [
                {"lease_id": "lease-1", "provider_session_id": "provider-session-1"},
            ],
        }
    )

    assert repo.query_lease_instance_id("lease-1") == "provider-session-1"


def test_list_probe_targets_prefers_provider_session_id() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                _lease(
                    "lease-running",
                    provider_name="daytona_selfhost",
                    observed_state="detached",
                    current_instance_id="instance-fallback",
                    updated_at="2026-04-05T10:10:00",
                ),
                _lease(
                    "lease-paused",
                    desired_state="paused",
                    observed_state="paused",
                    current_instance_id="instance-local",
                    updated_at="2026-04-05T10:11:00",
                ),
                _lease(
                    "lease-stopped",
                    provider_name="docker",
                    desired_state="stopped",
                    observed_state="stopped",
                    current_instance_id="instance-stopped",
                    updated_at="2026-04-05T10:12:00",
                ),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-running", "provider_session_id": "provider-session-1"},
            ],
        }
    )

    assert repo.list_probe_targets() == [
        {
            "lease_id": "lease-paused",
            "provider_name": "local",
            "instance_id": "instance-local",
            "observed_state": "paused",
        },
        {
            "lease_id": "lease-running",
            "provider_name": "daytona_selfhost",
            "instance_id": "provider-session-1",
            "observed_state": "detached",
        },
    ]


@pytest.mark.parametrize(
    ("include_updated_at", "caller"),
    [
        (False, lambda repo: repo.query_lease_instance_id("lease-1")),
        (True, lambda repo: repo.list_probe_targets()),
    ],
    ids=["query-lease-instance-id", "list-probe-targets"],
)
def test_instance_lookup_failures_are_loud(include_updated_at, caller) -> None:
    lease = _lease("lease-1", provider_name="daytona_selfhost", observed_state="detached", current_instance_id="instance-fallback")
    if include_updated_at:
        lease["updated_at"] = "2026-04-05T10:10:00"
    repo = SupabaseSandboxMonitorRepo(_BrokenSandboxInstancesClient({"sandbox_leases": [lease]}))

    with pytest.raises(RuntimeError, match="sandbox_instances exploded"):
        caller(repo)


def test_list_sessions_with_leases_keeps_active_terminal_and_recent_session_fallbacks() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                _lease("lease-active", created_at="2026-04-05T10:00:00"),
                _lease(
                    "lease-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                ),
                _lease(
                    "lease-recent",
                    provider_name="docker",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T12:00:00",
                ),
            ],
            "abstract_terminals": [
                _terminal("term-parent", "lease-terminal", "thread-parent", "2026-04-05T11:05:00"),
                _terminal("term-subagent", "lease-terminal", "subagent-deadbeef", "2026-04-05T11:06:00"),
            ],
            "chat_sessions": [
                _session("sess-active", "thread-active", "lease-active", started_at="2026-04-05T10:01:00"),
                _session("sess-recent-a", "thread-old", "lease-recent", status="closed", started_at="2026-04-05T12:01:00"),
                _session("sess-recent-b", "thread-new", "lease-recent", status="closed", started_at="2026-04-05T12:02:00"),
            ],
        }
    )

    assert repo.list_sessions_with_leases() == [
        {
            "provider": "docker",
            "session_id": None,
            "thread_id": "thread-new",
            "lease_id": "lease-recent",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T12:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-parent",
            "lease_id": "lease-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "subagent-deadbeef",
            "lease_id": "lease-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": "sess-active",
            "thread_id": "thread-active",
            "lease_id": "lease-active",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]
