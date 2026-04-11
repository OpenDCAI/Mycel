import pytest

from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient


class _BrokenSandboxInstancesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_instances":
            raise RuntimeError("sandbox_instances exploded")
        return super().table(table_name)


def _repo(tables: dict) -> SupabaseSandboxMonitorRepo:
    return SupabaseSandboxMonitorRepo(FakeSupabaseClient(tables))


def test_query_threads_accepts_optional_thread_filter() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                {
                    "lease_id": "lease-1",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "running",
                    "current_instance_id": "instance-1",
                }
            ],
            "chat_sessions": [
                {
                    "chat_session_id": "sess-1",
                    "thread_id": "thread-1",
                    "lease_id": "lease-1",
                    "status": "active",
                    "last_active_at": "2026-04-05T10:01:00",
                },
                {
                    "chat_session_id": "sess-2",
                    "thread_id": "thread-2",
                    "lease_id": "lease-1",
                    "status": "active",
                    "last_active_at": "2026-04-05T10:06:00",
                },
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
                }
            ],
            "abstract_terminals": [
                {"terminal_id": "term-old", "lease_id": "lease-1", "thread_id": "thread-old", "created_at": "2026-04-05T10:01:00"},
                {"terminal_id": "term-new", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:02:00"},
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


def test_query_lease_threads_returns_latest_unique_threads_first() -> None:
    repo = _repo(
        {
            "abstract_terminals": [
                {"terminal_id": "term-old", "lease_id": "lease-1", "thread_id": "thread-old", "created_at": "2026-04-05T10:01:00"},
                {"terminal_id": "term-new", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:02:00"},
                {"terminal_id": "term-dupe", "lease_id": "lease-1", "thread_id": "thread-new", "created_at": "2026-04-05T10:03:00"},
            ]
        }
    )

    assert repo.query_lease_threads("lease-1") == [{"thread_id": "thread-new"}, {"thread_id": "thread-old"}]


def test_query_lease_instance_id_prefers_provider_session_id() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                {
                    "lease_id": "lease-1",
                    "provider_name": "daytona_selfhost",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "instance-fallback",
                }
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
                {
                    "lease_id": "lease-running",
                    "provider_name": "daytona_selfhost",
                    "desired_state": "running",
                    "observed_state": "detached",
                    "current_instance_id": "instance-fallback",
                    "updated_at": "2026-04-05T10:10:00",
                },
                {
                    "lease_id": "lease-paused",
                    "provider_name": "local",
                    "desired_state": "paused",
                    "observed_state": "paused",
                    "current_instance_id": "instance-local",
                    "updated_at": "2026-04-05T10:11:00",
                },
                {
                    "lease_id": "lease-stopped",
                    "provider_name": "docker",
                    "desired_state": "stopped",
                    "observed_state": "stopped",
                    "current_instance_id": "instance-stopped",
                    "updated_at": "2026-04-05T10:12:00",
                },
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
    lease = {
        "lease_id": "lease-1",
        "provider_name": "daytona_selfhost",
        "desired_state": "running",
        "observed_state": "detached",
        "current_instance_id": "instance-fallback",
    }
    if include_updated_at:
        lease["updated_at"] = "2026-04-05T10:10:00"
    repo = SupabaseSandboxMonitorRepo(_BrokenSandboxInstancesClient({"sandbox_leases": [lease]}))

    with pytest.raises(RuntimeError, match="sandbox_instances exploded"):
        caller(repo)


def test_list_sessions_with_leases_keeps_active_terminal_and_recent_session_fallbacks() -> None:
    repo = _repo(
        {
            "sandbox_leases": [
                {
                    "lease_id": "lease-active",
                    "provider_name": "local",
                    "desired_state": "running",
                    "observed_state": "running",
                    "created_at": "2026-04-05T10:00:00",
                },
                {
                    "lease_id": "lease-terminal",
                    "provider_name": "daytona_selfhost",
                    "desired_state": "paused",
                    "observed_state": "paused",
                    "created_at": "2026-04-05T11:00:00",
                },
                {
                    "lease_id": "lease-recent",
                    "provider_name": "docker",
                    "desired_state": "paused",
                    "observed_state": "paused",
                    "created_at": "2026-04-05T12:00:00",
                },
            ],
            "abstract_terminals": [
                {"terminal_id": "term-parent", "lease_id": "lease-terminal", "thread_id": "thread-parent", "created_at": "2026-04-05T11:05:00"},
                {
                    "terminal_id": "term-subagent",
                    "lease_id": "lease-terminal",
                    "thread_id": "subagent-deadbeef",
                    "created_at": "2026-04-05T11:06:00",
                },
            ],
            "chat_sessions": [
                {
                    "chat_session_id": "sess-active",
                    "thread_id": "thread-active",
                    "lease_id": "lease-active",
                    "status": "active",
                    "started_at": "2026-04-05T10:01:00",
                },
                {
                    "chat_session_id": "sess-recent-a",
                    "thread_id": "thread-old",
                    "lease_id": "lease-recent",
                    "status": "closed",
                    "started_at": "2026-04-05T12:01:00",
                },
                {
                    "chat_session_id": "sess-recent-b",
                    "thread_id": "thread-new",
                    "lease_id": "lease-recent",
                    "status": "closed",
                    "started_at": "2026-04-05T12:02:00",
                },
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
