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


def _sandbox(
    sandbox_id: str,
    *,
    owner_user_id: str = "owner-1",
    provider_name: str = "local",
    provider_env_id: str | None = None,
    sandbox_template_id: str | None = None,
    desired_state: str = "running",
    observed_state: str = "running",
    status: str = "ready",
    observed_at: str = "2026-04-05T10:00:00",
    updated_at: str = "2026-04-05T10:00:00",
    created_at: str = "2026-04-05T09:00:00",
    last_error: str | None = None,
    legacy_lease_id: str | None = None,
    **config_extra,
) -> dict:
    config = dict(config_extra)
    if legacy_lease_id is not None:
        config["legacy_lease_id"] = legacy_lease_id
    return {
        "id": sandbox_id,
        "owner_user_id": owner_user_id,
        "provider_name": provider_name,
        "provider_env_id": provider_env_id,
        "sandbox_template_id": sandbox_template_id,
        "desired_state": desired_state,
        "observed_state": observed_state,
        "status": status,
        "observed_at": observed_at,
        "updated_at": updated_at,
        "created_at": created_at,
        "last_error": last_error,
        "config": config,
    }


def test_query_threads_accepts_optional_thread_filter() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_env_id="instance-1",
                    legacy_lease_id="lease-1",
                )
            ],
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
            "sandbox_id": "sandbox-1",
            "last_active": "2026-04-05T10:06:00",
            "lease_id": "lease-1",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "running",
            "current_instance_id": "instance-1",
        }
    ]


def test_query_threads_no_longer_roundtrips_through_lease_summary_shell(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_env_id="instance-1",
                    legacy_lease_id="lease-1",
                )
            ],
            "chat_sessions": [
                _session("sess-1", "thread-1", "lease-1", last_active_at="2026-04-05T10:01:00"),
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "_sandboxes_by_legacy_lease_id",
        lambda operation: (_ for _ in ()).throw(AssertionError("query_threads should not roundtrip through _sandboxes_by_legacy_lease_id")),
    )

    assert repo.query_threads() == [
        {
            "thread_id": "thread-1",
            "session_count": 1,
            "sandbox_id": "sandbox-1",
            "last_active": "2026-04-05T10:01:00",
            "lease_id": "lease-1",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "running",
            "current_instance_id": "instance-1",
        }
    ]


def test_query_threads_chunks_lease_lookup() -> None:
    sessions = [
        _session(f"sess-{index}", f"thread-{index}", f"lease-{index}", last_active_at=f"2026-04-05T10:{index % 60:02d}:00")
        for index in range(175)
    ]
    sandboxes = [
        _sandbox(f"sandbox-{index}", provider_env_id=f"instance-{index}", legacy_lease_id=f"lease-{index}") for index in range(175)
    ]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "chat_sessions": sessions,
                "container.sandboxes": sandboxes,
            }
        )
    )

    rows = repo.query_threads()

    assert len(rows) == 175
    assert next(row for row in rows if row["thread_id"] == "thread-174")["current_instance_id"] == "instance-174"


def test_query_lease_reads_container_sandbox_row() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="provider-env-1",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-1",
                    sandbox_template_id="template-1",
                )
            ]
        }
    )

    assert repo.query_lease("lease-1") == {
        "sandbox_id": "sandbox-1",
        "lease_id": "lease-1",
        "provider_name": "daytona_selfhost",
        "recipe_id": "template-1",
        "recipe_json": None,
        "desired_state": "paused",
        "observed_state": "paused",
        "current_instance_id": "provider-env-1",
        "last_error": None,
        "updated_at": "2026-04-05T10:10:00",
    }


def test_query_sandbox_threads_no_longer_roundtrips_through_lease_thread_shell(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    legacy_lease_id="lease-1",
                )
            ],
            "abstract_terminals": [
                {"thread_id": "thread-2", "lease_id": "lease-1", "created_at": "2026-04-05T10:02:00"},
                {"thread_id": "thread-1", "lease_id": "lease-1", "created_at": "2026-04-05T10:01:00"},
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "query_lease_threads",
        lambda lease_id: (_ for _ in ()).throw(AssertionError("query_sandbox_threads should not roundtrip through query_lease_threads")),
    )

    assert repo.query_sandbox_threads("sandbox-1") == [
        {"thread_id": "thread-2"},
        {"thread_id": "thread-1"},
    ]


def test_query_sandbox_reads_container_sandbox_row_by_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="provider-env-1",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-1",
                    sandbox_template_id="template-1",
                )
            ]
        }
    )

    assert repo.query_sandbox("sandbox-1") == {
        "sandbox_id": "sandbox-1",
        "lease_id": "lease-1",
        "provider_name": "daytona_selfhost",
        "recipe_id": "template-1",
        "recipe_json": None,
        "desired_state": "paused",
        "observed_state": "paused",
        "current_instance_id": "provider-env-1",
        "last_error": None,
        "updated_at": "2026-04-05T10:10:00",
    }


def test_query_lease_threads_no_longer_roundtrips_through_legacy_bridge_requirement(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    legacy_lease_id="lease-1",
                )
            ],
            "abstract_terminals": [
                {"thread_id": "thread-2", "lease_id": "lease-1", "created_at": "2026-04-05T10:02:00"},
                {"thread_id": "thread-1", "lease_id": "lease-1", "created_at": "2026-04-05T10:01:00"},
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "_require_sandbox_rows_by_legacy_lease_ids",
        lambda lease_ids, operation: (_ for _ in ()).throw(
            AssertionError("query_lease_threads should not roundtrip through _require_sandbox_rows_by_legacy_lease_ids")
        ),
    )

    assert repo.query_lease_threads("lease-1") == [
        {"thread_id": "thread-2"},
        {"thread_id": "thread-1"},
    ]


def test_query_lease_events_no_longer_roundtrips_through_legacy_bridge_requirement(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    legacy_lease_id="lease-1",
                )
            ],
            "provider_events": [
                {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:02:00", "event": "newer"},
                {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:01:00", "event": "older"},
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "_require_sandbox_rows_by_legacy_lease_ids",
        lambda lease_ids, operation: (_ for _ in ()).throw(
            AssertionError("query_lease_events should not roundtrip through _require_sandbox_rows_by_legacy_lease_ids")
        ),
    )

    assert repo.query_lease_events("lease-1") == [
        {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:02:00", "event": "newer"},
        {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:01:00", "event": "older"},
    ]


def test_query_thread_sessions_reads_container_sandbox_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    legacy_lease_id="lease-1",
                    last_error="last boom",
                )
            ],
            "chat_sessions": [
                {
                    **_session("sess-1", "thread-1", "lease-1", started_at="2026-04-05T10:01:00"),
                    "ended_at": None,
                    "close_reason": None,
                }
            ],
        }
    )

    assert repo.query_thread_sessions("thread-1") == [
        {
            "chat_session_id": "sess-1",
            "status": "active",
            "started_at": "2026-04-05T10:01:00",
            "ended_at": None,
            "close_reason": None,
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "last_error": "last boom",
        }
    ]


def test_query_sandbox_sessions_no_longer_roundtrips_through_lease_session_shell(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    legacy_lease_id="lease-1",
                    last_error="last boom",
                )
            ],
            "chat_sessions": [
                {
                    **_session("sess-1", "thread-1", "lease-1", started_at="2026-04-05T10:01:00"),
                    "ended_at": None,
                    "close_reason": None,
                }
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "query_lease_sessions",
        lambda lease_id: (_ for _ in ()).throw(AssertionError("query_sandbox_sessions should not roundtrip through query_lease_sessions")),
    )

    assert repo.query_sandbox_sessions("sandbox-1") == [
        {
            "chat_session_id": "sess-1",
            "status": "active",
            "started_at": "2026-04-05T10:01:00",
            "ended_at": None,
            "close_reason": None,
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "last_error": "last boom",
            "thread_id": "thread-1",
        }
    ]


def test_query_lease_sessions_no_longer_roundtrips_through_query_lease(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    legacy_lease_id="lease-1",
                    last_error="last boom",
                )
            ],
            "chat_sessions": [
                {
                    **_session("sess-1", "thread-1", "lease-1", started_at="2026-04-05T10:01:00"),
                    "ended_at": None,
                    "close_reason": None,
                }
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "query_lease",
        lambda lease_id: (_ for _ in ()).throw(AssertionError("query_lease_sessions should not roundtrip through query_lease")),
    )

    assert repo.query_lease_sessions("lease-1") == [
        {
            "chat_session_id": "sess-1",
            "status": "active",
            "started_at": "2026-04-05T10:01:00",
            "ended_at": None,
            "close_reason": None,
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "last_error": "last boom",
            "thread_id": "thread-1",
        }
    ]


def test_query_thread_sessions_no_longer_roundtrips_through_lease_summary_shell(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    legacy_lease_id="lease-1",
                    last_error="last boom",
                )
            ],
            "chat_sessions": [
                {
                    **_session("sess-1", "thread-1", "lease-1", started_at="2026-04-05T10:01:00"),
                    "ended_at": None,
                    "close_reason": None,
                }
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "_sandboxes_by_legacy_lease_id",
        lambda operation: (_ for _ in ()).throw(
            AssertionError("query_thread_sessions should not roundtrip through _sandboxes_by_legacy_lease_id")
        ),
    )

    assert repo.query_thread_sessions("thread-1") == [
        {
            "chat_session_id": "sess-1",
            "status": "active",
            "started_at": "2026-04-05T10:01:00",
            "ended_at": None,
            "close_reason": None,
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "last_error": "last boom",
        }
    ]


def test_query_leases_uses_latest_terminal_binding() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-1",
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
            "sandbox_id": "sandbox-1",
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


def test_query_sandboxes_uses_latest_terminal_binding() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-1",
                )
            ],
            "abstract_terminals": [
                _terminal("term-old", "lease-1", "thread-old", "2026-04-05T10:01:00"),
                _terminal("term-new", "lease-1", "thread-new", "2026-04-05T10:02:00"),
            ],
        }
    )

    assert repo.query_sandboxes() == [
        {
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": None,
            "recipe_json": None,
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "instance-1",
            "last_error": None,
            "updated_at": "2026-04-05T10:10:00",
            "thread_id": "thread-new",
        }
    ]


def test_query_leases_reads_container_sandboxes_with_terminal_binding() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="provider-env-1",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-1",
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
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "desired_state": "paused",
            "observed_state": "paused",
            "current_instance_id": "provider-env-1",
            "updated_at": "2026-04-05T10:10:00",
            "recipe_id": None,
            "recipe_json": None,
            "last_error": None,
            "thread_id": "thread-new",
        }
    ]


def test_query_leases_chunks_terminal_binding_lookup() -> None:
    sandboxes = [
        _sandbox(
            f"sandbox-{index}",
            provider_env_id=f"instance-{index}",
            updated_at=f"2026-04-05T10:{index % 60:02d}:00",
            legacy_lease_id=f"lease-{index}",
        )
        for index in range(175)
    ]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "container.sandboxes": sandboxes,
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
            "container.sandboxes": [
                _sandbox("sandbox-1", legacy_lease_id="lease-1"),
            ],
            "abstract_terminals": [
                _terminal("term-old", "lease-1", "thread-old", "2026-04-05T10:01:00"),
                _terminal("term-new", "lease-1", "thread-new", "2026-04-05T10:02:00"),
                _terminal("term-dupe", "lease-1", "thread-new", "2026-04-05T10:03:00"),
            ],
        }
    )

    assert repo.query_lease_threads("lease-1") == [{"thread_id": "thread-new"}, {"thread_id": "thread-old"}]


def test_query_lease_instance_id_prefers_provider_session_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    observed_state="detached",
                    provider_env_id="instance-sandbox",
                    legacy_lease_id="lease-1",
                )
            ],
            "sandbox_instances": [
                {"lease_id": "lease-1", "provider_session_id": "provider-session-1"},
            ],
        }
    )

    assert repo.query_lease_instance_id("lease-1") == "provider-session-1"


def test_query_lease_instance_ids_chunks_large_lookup() -> None:
    lease_ids = [f"lease-{index}" for index in range(175)]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "container.sandboxes": [
                    _sandbox(
                        f"sandbox-{index}",
                        provider_env_id=f"sandbox-instance-{lease_ids[index]}",
                        legacy_lease_id=lease_ids[index],
                    )
                    for index in range(175)
                ],
                "sandbox_instances": [{"lease_id": "lease-174", "provider_session_id": "provider-session-174"}],
            }
        )
    )

    result = repo.query_lease_instance_ids(lease_ids)

    assert result["lease-0"] == "sandbox-instance-lease-0"
    assert result["lease-174"] == "provider-session-174"


def test_query_sandbox_instance_ids_uses_legacy_bridge() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", legacy_lease_id="lease-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", legacy_lease_id="lease-2"),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-2", "provider_session_id": "provider-session-2"},
            ],
        }
    )

    assert repo.query_sandbox_instance_ids(["sandbox-1", "sandbox-2"]) == {
        "sandbox-1": "sandbox-instance-1",
        "sandbox-2": "provider-session-2",
    }


def test_query_sandbox_instance_ids_no_longer_roundtrips_through_lease_bridge(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", legacy_lease_id="lease-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", legacy_lease_id="lease-2"),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-2", "provider_session_id": "provider-session-2"},
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "query_lease_instance_ids",
        lambda _lease_ids: (_ for _ in ()).throw(
            AssertionError("sandbox-shaped instance lookup should not roundtrip through query_lease_instance_ids")
        ),
    )

    assert repo.query_sandbox_instance_ids(["sandbox-1", "sandbox-2"]) == {
        "sandbox-1": "sandbox-instance-1",
        "sandbox-2": "provider-session-2",
    }


def test_query_lease_events_requires_sandbox_bridge() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", legacy_lease_id="lease-1"),
            ],
            "provider_events": [
                {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:02:00", "event": "newer"},
                {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:01:00", "event": "older"},
            ],
        }
    )

    assert repo.query_lease_events("lease-1") == [
        {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:02:00", "event": "newer"},
        {"matched_lease_id": "lease-1", "created_at": "2026-04-05T10:01:00", "event": "older"},
    ]


@pytest.mark.parametrize(
    ("caller", "expected"),
    [
        (lambda repo: repo.query_lease_threads("lease-missing"), "sandbox legacy bridge is required"),
        (lambda repo: repo.query_lease_events("lease-missing"), "sandbox legacy bridge is required"),
        (lambda repo: repo.query_lease_instance_id("lease-missing"), "sandbox legacy bridge is required"),
    ],
    ids=["lease-threads", "lease-events", "lease-instance-id"],
)
def test_residue_keyed_surfaces_fail_loud_without_sandbox_bridge(caller, expected) -> None:
    repo = _repo({"container.sandboxes": []})

    with pytest.raises(RuntimeError, match=expected):
        caller(repo)


def test_list_probe_targets_prefers_provider_session_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-running",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-lease",
                    observed_state="detached",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    legacy_lease_id="lease-paused",
                ),
                _sandbox(
                    "sandbox-stopped",
                    provider_name="docker",
                    provider_env_id="instance-stopped",
                    desired_state="stopped",
                    observed_state="stopped",
                    updated_at="2026-04-05T10:12:00",
                    legacy_lease_id="lease-stopped",
                ),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-running", "provider_session_id": "provider-session-1"},
            ],
        }
    )

    assert repo.list_probe_targets() == [
        {
            "sandbox_id": "sandbox-paused",
            "legacy_lease_id": "lease-paused",
            "provider_name": "local",
            "instance_id": "instance-local",
            "observed_state": "paused",
        },
        {
            "sandbox_id": "sandbox-running",
            "legacy_lease_id": "lease-running",
            "provider_name": "daytona_selfhost",
            "instance_id": "provider-session-1",
            "observed_state": "detached",
        },
    ]


def test_list_probe_targets_no_longer_roundtrips_through_lease_instance_bridge(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-running",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-lease",
                    observed_state="detached",
                    updated_at="2026-04-05T10:10:00",
                    legacy_lease_id="lease-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    legacy_lease_id="lease-paused",
                ),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-running", "provider_session_id": "provider-session-1"},
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "query_lease_instance_ids",
        lambda lease_ids: (_ for _ in ()).throw(
            AssertionError("probe-target assembly should not roundtrip through query_lease_instance_ids")
        ),
    )

    assert repo.list_probe_targets() == [
        {
            "sandbox_id": "sandbox-paused",
            "legacy_lease_id": "lease-paused",
            "provider_name": "local",
            "instance_id": "instance-local",
            "observed_state": "paused",
        },
        {
            "sandbox_id": "sandbox-running",
            "legacy_lease_id": "lease-running",
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
    tables = {
        "container.sandboxes": [
            _sandbox(
                "sandbox-1",
                provider_name="daytona_selfhost",
                provider_env_id="instance-lease",
                observed_state="detached",
                updated_at="2026-04-05T10:10:00" if include_updated_at else "2026-04-05T10:00:00",
                legacy_lease_id="lease-1",
            )
        ]
    }
    repo = SupabaseSandboxMonitorRepo(_BrokenSandboxInstancesClient(tables))

    with pytest.raises(RuntimeError, match="sandbox_instances exploded"):
        caller(repo)


def test_list_sessions_with_leases_keeps_active_terminal_and_latest_closed_session_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", legacy_lease_id="lease-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    legacy_lease_id="lease-terminal",
                ),
                _sandbox(
                    "sandbox-recent",
                    provider_name="docker",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T12:00:00",
                    legacy_lease_id="lease-recent",
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
            "sandbox_id": "sandbox-recent",
            "lease_id": "lease-recent",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T12:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-terminal",
            "lease_id": "lease-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "subagent-deadbeef",
            "sandbox_id": "sandbox-terminal",
            "lease_id": "lease-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": "sess-active",
            "thread_id": "thread-active",
            "sandbox_id": "sandbox-active",
            "lease_id": "lease-active",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]


def test_list_sessions_with_leases_no_longer_materializes_lease_map(monkeypatch) -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", legacy_lease_id="lease-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    legacy_lease_id="lease-terminal",
                ),
            ],
            "abstract_terminals": [
                _terminal("term-parent", "lease-terminal", "thread-parent", "2026-04-05T11:05:00"),
            ],
            "chat_sessions": [
                _session("sess-active", "thread-active", "lease-active", started_at="2026-04-05T10:01:00"),
            ],
        }
    )

    monkeypatch.setattr(
        repo,
        "_lease_row_from_sandbox",
        lambda sandbox: (_ for _ in ()).throw(
            AssertionError("list_sessions_with_leases should not materialize a lease_map through _lease_row_from_sandbox")
        ),
    )

    assert repo.list_sessions_with_leases() == [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-terminal",
            "lease_id": "lease-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": "sess-active",
            "thread_id": "thread-active",
            "sandbox_id": "sandbox-active",
            "lease_id": "lease-active",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]
