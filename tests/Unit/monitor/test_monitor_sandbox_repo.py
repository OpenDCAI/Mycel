import pytest

from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient, FakeSupabaseQuery


class _BrokenSandboxInstancesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_instances":
            raise RuntimeError("sandbox_instances exploded")
        return super().table(table_name)


class _BrokenChatSessionsClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "chat_sessions":
            raise RuntimeError("chat_sessions exploded")
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


class _NoWorkspaceSandboxInQuery(FakeSupabaseQuery):
    def in_(self, column: str, values: list[object]):
        if self._table_name == "container.workspaces" and column == "sandbox_id":
            raise AssertionError("query_sandboxes should not use sandbox_id IN against container.workspaces")
        return super().in_(column, values)


class _NoWorkspaceSandboxInClient(FakeSupabaseClient):
    def table(self, table_name: str):
        resolved_table = f"{self._schema_name}.{table_name}" if self._schema_name else table_name
        query = _NoWorkspaceSandboxInQuery(resolved_table, self._tables)
        if resolved_table in self._auto_seq_tables:
            query._auto_seq = True
        return query

    def schema(self, schema_name: str):
        return _NoWorkspaceSandboxInClient(self._tables, self._auto_seq_tables, schema_name=schema_name)


def _repo(tables: dict) -> SupabaseSandboxMonitorRepo:
    return SupabaseSandboxMonitorRepo(FakeSupabaseClient(tables))


def _chat_session(
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


def _workspace(workspace_id: str, sandbox_id: str, *, updated_at: str = "2026-04-05T10:00:00") -> dict:
    return {
        "id": workspace_id,
        "sandbox_id": sandbox_id,
        "owner_user_id": "owner-1",
        "workspace_path": "/workspace",
        "updated_at": updated_at,
    }


def _thread(thread_id: str, workspace_id: str, *, updated_at: str = "2026-04-05T10:00:00") -> dict:
    return {
        "id": thread_id,
        "current_workspace_id": workspace_id,
        "updated_at": updated_at,
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
    lower_runtime_handle: str | None = None,
    **config_extra,
) -> dict:
    config = dict(config_extra)
    if lower_runtime_handle is not None:
        config["runtime_handle"] = lower_runtime_handle
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
                    lower_runtime_handle="lease-1",
                )
            ],
            "container.workspaces": [
                _workspace("workspace-1", "sandbox-1", updated_at="2026-04-05T10:01:00"),
                _workspace("workspace-2", "sandbox-1", updated_at="2026-04-05T10:06:00"),
            ],
            "agent.threads": [
                _thread("thread-1", "workspace-1", updated_at="2026-04-05T10:01:00"),
                _thread("thread-2", "workspace-2", updated_at="2026-04-05T10:06:00"),
            ],
        }
    )

    assert repo.query_threads(thread_id="thread-2") == [
        {
            "thread_id": "thread-2",
            "session_count": 0,
            "sandbox_id": "sandbox-1",
            "last_active": "2026-04-05T10:06:00",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "running",
            "current_instance_id": "instance-1",
        }
    ]


def test_query_threads_projects_workspace_backed_sandbox_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_env_id="instance-1",
                    lower_runtime_handle="lease-1",
                )
            ],
            "container.workspaces": [
                _workspace("workspace-1", "sandbox-1", updated_at="2026-04-05T10:01:00"),
            ],
            "agent.threads": [
                _thread("thread-1", "workspace-1", updated_at="2026-04-05T10:01:00"),
            ],
        }
    )

    assert repo.query_threads() == [
        {
            "thread_id": "thread-1",
            "session_count": 0,
            "sandbox_id": "sandbox-1",
            "last_active": "2026-04-05T10:01:00",
            "provider_name": "local",
            "desired_state": "running",
            "observed_state": "running",
            "current_instance_id": "instance-1",
        }
    ]


def test_query_threads_chunks_sandbox_lookup() -> None:
    sandboxes = [
        _sandbox(f"sandbox-{index}", provider_env_id=f"instance-{index}", lower_runtime_handle=f"lease-{index}") for index in range(175)
    ]
    workspaces = [
        _workspace(f"workspace-{index}", f"sandbox-{index}", updated_at=f"2026-04-05T10:{index % 60:02d}:00") for index in range(175)
    ]
    threads = [_thread(f"thread-{index}", f"workspace-{index}", updated_at=f"2026-04-05T10:{index % 60:02d}:00") for index in range(175)]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "container.sandboxes": sandboxes,
                "container.workspaces": workspaces,
                "agent.threads": threads,
            }
        )
    )

    rows = repo.query_threads()

    assert len(rows) == 175
    assert next(row for row in rows if row["thread_id"] == "thread-174")["current_instance_id"] == "instance-174"


def test_query_sandbox_threads_returns_workspace_thread_ids() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    lower_runtime_handle="lease-1",
                )
            ],
            "container.workspaces": [
                _workspace("workspace-1", "sandbox-1", updated_at="2026-04-05T10:01:00"),
                _workspace("workspace-2", "sandbox-1", updated_at="2026-04-05T10:02:00"),
            ],
            "agent.threads": [
                _thread("thread-1", "workspace-1", updated_at="2026-04-05T10:01:00"),
                _thread("thread-2", "workspace-2", updated_at="2026-04-05T10:02:00"),
            ],
        }
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
                    lower_runtime_handle="lease-1",
                    sandbox_template_id="template-1",
                )
            ]
        }
    )

    assert repo.query_sandbox("sandbox-1") == {
        "sandbox_id": "sandbox-1",
        "provider_name": "daytona_selfhost",
        "recipe_id": "template-1",
        "recipe_json": None,
        "desired_state": "paused",
        "observed_state": "paused",
        "current_instance_id": "provider-env-1",
        "last_error": None,
        "updated_at": "2026-04-05T10:10:00",
    }


def test_query_sandbox_allows_missing_lower_runtime_handle() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="local",
                    provider_env_id=None,
                    desired_state="running",
                    observed_state="running",
                    updated_at="2026-04-05T10:10:00",
                    sandbox_template_id="local:default",
                    lower_runtime_handle=None,
                )
            ]
        }
    )

    assert repo.query_sandbox("sandbox-1") == {
        "sandbox_id": "sandbox-1",
        "provider_name": "local",
        "recipe_id": "local:default",
        "recipe_json": None,
        "desired_state": "running",
        "observed_state": "running",
        "current_instance_id": None,
        "last_error": None,
        "updated_at": "2026-04-05T10:10:00",
    }


def test_query_thread_sessions_ignores_removed_chat_sessions_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-1",
                    desired_state="paused",
                    observed_state="paused",
                    lower_runtime_handle="lease-1",
                    last_error="last boom",
                )
            ],
            "chat_sessions": [
                {
                    **_chat_session("sess-1", "thread-1", "lease-1", started_at="2026-04-05T10:01:00"),
                    "ended_at": None,
                    "close_reason": None,
                }
            ],
        }
    )

    assert repo.query_thread_sessions("thread-1") == []


def test_chat_session_monitor_surfaces_do_not_read_removed_chat_sessions_table() -> None:
    repo = SupabaseSandboxMonitorRepo(
        _BrokenChatSessionsClient(
            {
                "container.sandboxes": [
                    _sandbox("sandbox-1", provider_env_id="instance-1", lower_runtime_handle="lease-1"),
                ],
                "container.workspaces": [
                    _workspace("workspace-1", "sandbox-1", updated_at="2026-04-05T10:05:00"),
                ],
                "agent.threads": [
                    _thread("thread-1", "workspace-1", updated_at="2026-04-05T10:05:00"),
                ],
            }
        )
    )

    assert repo.query_thread_sessions("thread-1") == []
    assert repo.query_sandbox_sessions("sandbox-1") == []
    assert repo.query_resource_sessions() == [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "sandbox_id": "sandbox-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T09:00:00",
        }
    ]


def test_query_sandboxes_uses_latest_workspace_thread_binding() -> None:
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
                    lower_runtime_handle="lease-1",
                )
            ],
            "container.workspaces": [
                _workspace("workspace-old", "sandbox-1", updated_at="2026-04-05T10:01:00"),
                _workspace("workspace-new", "sandbox-1", updated_at="2026-04-05T10:02:00"),
            ],
            "agent.threads": [
                _thread("thread-old", "workspace-old", updated_at="2026-04-05T10:01:00"),
                _thread("thread-new", "workspace-new", updated_at="2026-04-05T10:02:00"),
            ],
        }
    )

    assert repo.query_sandboxes() == [
        {
            "sandbox_id": "sandbox-1",
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


def test_query_sandboxes_reads_container_sandboxes_with_workspace_binding() -> None:
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
                    lower_runtime_handle="lease-1",
                )
            ],
            "container.workspaces": [
                _workspace("workspace-old", "sandbox-1", updated_at="2026-04-05T10:01:00"),
                _workspace("workspace-new", "sandbox-1", updated_at="2026-04-05T10:02:00"),
            ],
            "agent.threads": [
                _thread("thread-old", "workspace-old", updated_at="2026-04-05T10:01:00"),
                _thread("thread-new", "workspace-new", updated_at="2026-04-05T10:02:00"),
            ],
        }
    )

    assert repo.query_sandboxes() == [
        {
            "sandbox_id": "sandbox-1",
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


def test_query_sandboxes_does_not_depend_on_workspace_sandbox_id_in_filter() -> None:
    repo = SupabaseSandboxMonitorRepo(
        _NoWorkspaceSandboxInClient(
            {
                "container.sandboxes": [
                    _sandbox(
                        "sandbox-1",
                        provider_env_id="instance-1",
                        updated_at="2026-04-05T10:10:00",
                        lower_runtime_handle="lease-1",
                    )
                ],
                "container.workspaces": [_workspace("workspace-1", "sandbox-1")],
                "agent.threads": [_thread("thread-1", "workspace-1")],
            }
        )
    )

    assert repo.query_sandboxes()[0]["thread_id"] == "thread-1"


def test_query_sandboxes_handles_many_workspace_thread_bindings() -> None:
    sandboxes = [
        _sandbox(
            f"sandbox-{index}",
            provider_env_id=f"instance-{index}",
            updated_at=f"2026-04-05T10:{index % 60:02d}:00",
            lower_runtime_handle=f"lease-{index}",
        )
        for index in range(175)
    ]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "container.sandboxes": sandboxes,
                "container.workspaces": [_workspace("workspace-174", "sandbox-174", updated_at="2026-04-05T10:02:00")],
                "agent.threads": [_thread("thread-174", "workspace-174", updated_at="2026-04-05T10:02:00")],
            }
        )
    )

    rows = repo.query_sandboxes()

    assert len(rows) == 175
    assert next(row for row in rows if row["sandbox_id"] == "sandbox-174")["thread_id"] == "thread-174"


def test_query_sandbox_instance_id_uses_sandbox_provider_env_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    observed_state="detached",
                    provider_env_id="instance-sandbox",
                    lower_runtime_handle="lease-1",
                )
            ],
            "sandbox_instances": [
                {"lease_id": "lease-1", "provider_session_id": "instance-lease"},
            ],
        }
    )

    assert repo.query_sandbox_instance_id("sandbox-1") == "instance-sandbox"


def test_query_sandbox_cleanup_target_reads_structured_sandbox_target() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-sandbox",
                    observed_state="detached",
                    lower_runtime_handle="lease-1",
                )
            ],
        }
    )

    assert repo.query_sandbox_cleanup_target("sandbox-1") == {
        "sandbox_id": "sandbox-1",
        "provider_name": "daytona_selfhost",
        "provider_env_id": "instance-sandbox",
        "lower_runtime_handle": "lease-1",
    }


def test_query_sandbox_instance_id_falls_back_without_lower_runtime_handle() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="local",
                    provider_env_id="sandbox-instance-1",
                    observed_state="running",
                    lower_runtime_handle=None,
                )
            ],
        }
    )

    assert repo.query_sandbox_instance_id("sandbox-1") == "sandbox-instance-1"


def test_query_sandbox_instance_ids_chunks_large_lookup() -> None:
    sandbox_ids = [f"sandbox-{index}" for index in range(175)]
    repo = SupabaseSandboxMonitorRepo(
        _MaxInFilterClient(
            {
                "container.sandboxes": [
                    _sandbox(
                        f"sandbox-{index}",
                        provider_env_id=f"sandbox-instance-sandbox-{index}",
                        lower_runtime_handle=f"lease-{index}",
                    )
                    for index in range(175)
                ],
                "sandbox_instances": [{"lease_id": "lease-174", "provider_session_id": "sandbox-instance-sandbox-174"}],
            }
        )
    )

    result = repo.query_sandbox_instance_ids(sandbox_ids)

    assert result["sandbox-0"] == "sandbox-instance-sandbox-0"
    assert result["sandbox-174"] == "sandbox-instance-sandbox-174"


def test_query_sandbox_instance_ids_use_sandbox_provider_env_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", lower_runtime_handle="lease-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", lower_runtime_handle="lease-2"),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-2", "provider_session_id": "stale-instance-2"},
            ],
        }
    )

    assert repo.query_sandbox_instance_ids(["sandbox-1", "sandbox-2"]) == {
        "sandbox-1": "sandbox-instance-1",
        "sandbox-2": "sandbox-instance-2",
    }


def test_query_sandbox_instance_ids_use_sandbox_runtime_identity() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", lower_runtime_handle="lease-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", lower_runtime_handle="lease-2"),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-2", "provider_session_id": "stale-instance-2"},
            ],
        }
    )

    assert repo.query_sandbox_instance_ids(["sandbox-1", "sandbox-2"]) == {
        "sandbox-1": "sandbox-instance-1",
        "sandbox-2": "sandbox-instance-2",
    }


def test_query_sandbox_instance_id_uses_sandbox_runtime_identity() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", lower_runtime_handle="lease-1"),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-1", "provider_session_id": "instance-lease"},
            ],
        }
    )

    assert repo.query_sandbox_instance_id("sandbox-1") == "sandbox-instance-1"


def test_list_probe_targets_use_sandbox_provider_env_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-running",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-sandbox",
                    observed_state="detached",
                    updated_at="2026-04-05T10:10:00",
                    lower_runtime_handle="lease-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    lower_runtime_handle="lease-paused",
                ),
                _sandbox(
                    "sandbox-stopped",
                    provider_name="docker",
                    provider_env_id="instance-stopped",
                    desired_state="stopped",
                    observed_state="stopped",
                    updated_at="2026-04-05T10:12:00",
                    lower_runtime_handle="lease-stopped",
                ),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-running", "provider_session_id": "instance-lease"},
            ],
        }
    )

    assert repo.list_probe_targets() == [
        {
            "sandbox_id": "sandbox-paused",
            "provider_name": "local",
            "instance_id": "instance-local",
            "observed_state": "paused",
        },
        {
            "sandbox_id": "sandbox-running",
            "provider_name": "daytona_selfhost",
            "instance_id": "instance-sandbox",
            "observed_state": "detached",
        },
    ]


def test_list_probe_targets_skips_sandbox_without_provider_env_id() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-stale",
                    provider_name="local",
                    provider_env_id=None,
                    observed_state="running",
                    lower_runtime_handle=None,
                ),
            ],
        }
    )

    assert repo.list_probe_targets() == []


def test_list_probe_targets_use_sandbox_runtime_identity() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-running",
                    provider_name="daytona_selfhost",
                    provider_env_id="instance-sandbox",
                    observed_state="detached",
                    updated_at="2026-04-05T10:10:00",
                    lower_runtime_handle="lease-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    lower_runtime_handle="lease-paused",
                ),
            ],
            "sandbox_instances": [
                {"lease_id": "lease-running", "provider_session_id": "instance-lease"},
            ],
        }
    )

    assert repo.list_probe_targets() == [
        {
            "sandbox_id": "sandbox-paused",
            "provider_name": "local",
            "instance_id": "instance-local",
            "observed_state": "paused",
        },
        {
            "sandbox_id": "sandbox-running",
            "provider_name": "daytona_selfhost",
            "instance_id": "instance-sandbox",
            "observed_state": "detached",
        },
    ]


@pytest.mark.parametrize(
    ("include_updated_at", "caller"),
    [
        (False, lambda repo: repo.query_sandbox_instance_id("sandbox-1")),
        (True, lambda repo: repo.list_probe_targets()),
    ],
    ids=["query-sandbox-instance-id", "list-probe-targets"],
)
def test_instance_lookup_does_not_read_removed_instances_table(include_updated_at, caller) -> None:
    tables = {
        "container.sandboxes": [
            _sandbox(
                "sandbox-1",
                provider_name="daytona_selfhost",
                provider_env_id="instance-lease",
                observed_state="detached",
                updated_at="2026-04-05T10:10:00" if include_updated_at else "2026-04-05T10:00:00",
                lower_runtime_handle="lease-1",
            )
        ]
    }
    repo = SupabaseSandboxMonitorRepo(_BrokenSandboxInstancesClient(tables))

    result = caller(repo)

    if include_updated_at:
        assert result == [
            {
                "sandbox_id": "sandbox-1",
                "provider_name": "daytona_selfhost",
                "instance_id": "instance-lease",
                "observed_state": "detached",
            }
        ]
    else:
        assert result == "instance-lease"


def test_query_resource_sessions_uses_sandbox_thread_rows_without_session_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", lower_runtime_handle="lease-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    lower_runtime_handle="lease-terminal",
                ),
                _sandbox(
                    "sandbox-recent",
                    provider_name="docker",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T12:00:00",
                    lower_runtime_handle="lease-recent",
                ),
            ],
            "container.workspaces": [
                _workspace("workspace-parent", "sandbox-terminal", updated_at="2026-04-05T11:05:00"),
                _workspace("workspace-subagent", "sandbox-terminal", updated_at="2026-04-05T11:06:00"),
            ],
            "agent.threads": [
                _thread("thread-parent", "workspace-parent", updated_at="2026-04-05T11:05:00"),
                _thread("subagent-deadbeef", "workspace-subagent", updated_at="2026-04-05T11:06:00"),
            ],
            "chat_sessions": [
                _chat_session("sess-active", "thread-active", "lease-active", started_at="2026-04-05T10:01:00"),
                _chat_session("sess-recent-a", "thread-old", "lease-recent", status="closed", started_at="2026-04-05T12:01:00"),
                _chat_session("sess-recent-b", "thread-new", "lease-recent", status="closed", started_at="2026-04-05T12:02:00"),
            ],
        }
    )

    assert repo.query_resource_sessions() == [
        {
            "provider": "docker",
            "session_id": None,
            "thread_id": None,
            "sandbox_id": "sandbox-recent",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T12:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "subagent-deadbeef",
            "sandbox_id": "sandbox-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": None,
            "sandbox_id": "sandbox-active",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]


def test_query_resource_sessions_does_not_require_lower_runtime_handle() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-clean",
                    provider_name="docker",
                    desired_state="running",
                    observed_state="running",
                    created_at="2026-04-05T13:00:00",
                    lower_runtime_handle=None,
                ),
            ],
            "container.workspaces": [
                _workspace("workspace-clean", "sandbox-clean", updated_at="2026-04-05T13:05:00"),
            ],
            "agent.threads": [
                _thread("thread-clean", "workspace-clean", updated_at="2026-04-05T13:05:00"),
            ],
        }
    )

    assert repo.query_resource_sessions() == [
        {
            "provider": "docker",
            "session_id": None,
            "thread_id": "thread-clean",
            "sandbox_id": "sandbox-clean",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T13:00:00",
        }
    ]


def test_query_resource_sessions_projects_sandbox_rows_without_session_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", lower_runtime_handle="lease-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    lower_runtime_handle="lease-terminal",
                ),
            ],
            "container.workspaces": [
                _workspace("workspace-parent", "sandbox-terminal", updated_at="2026-04-05T11:05:00"),
            ],
            "agent.threads": [
                _thread("thread-parent", "workspace-parent", updated_at="2026-04-05T11:05:00"),
            ],
            "chat_sessions": [
                _chat_session("sess-active", "thread-active", "lease-active", started_at="2026-04-05T10:01:00"),
            ],
        }
    )

    assert repo.query_resource_sessions() == [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-terminal",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": None,
            "sandbox_id": "sandbox-active",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]
