from storage.providers.supabase.sandbox_monitor_repo import SupabaseSandboxMonitorRepo
from tests.fakes.supabase import FakeSupabaseClient, FakeSupabaseQuery

SANDBOX_RUNTIME_KEY = "sandbox_runtime_" + "id"


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


class _CountingQuery(FakeSupabaseQuery):
    def __init__(self, table_name: str, tables: dict[str, list[dict]], counts: dict[str, int]):
        super().__init__(table_name, tables)
        self._counts = counts

    def execute(self):
        self._counts[self._table_name] = self._counts.get(self._table_name, 0) + 1
        return super().execute()


class _CountingClient(FakeSupabaseClient):
    def __init__(
        self,
        tables: dict[str, list[dict]] | None = None,
        auto_seq_tables: set[str] | None = None,
        schema_name: str | None = None,
        *,
        counts: dict[str, int] | None = None,
    ):
        super().__init__(tables, auto_seq_tables, schema_name=schema_name)
        self._counts = counts if counts is not None else {}

    def table(self, table_name: str):
        resolved_table = f"{self._schema_name}.{table_name}" if self._schema_name else table_name
        query = _CountingQuery(resolved_table, self._tables, self._counts)
        if resolved_table in self._auto_seq_tables:
            query._auto_seq = True
        return query

    def schema(self, schema_name: str):
        return _CountingClient(self._tables, self._auto_seq_tables, schema_name=schema_name, counts=self._counts)


def _repo(tables: dict) -> SupabaseSandboxMonitorRepo:
    return SupabaseSandboxMonitorRepo(FakeSupabaseClient(tables))


def _chat_session(
    session_id: str,
    thread_id: str,
    sandbox_runtime_handle: str,
    *,
    status: str = "active",
    started_at: str | None = None,
    last_active_at: str | None = None,
) -> dict:
    row = {
        "chat_session_id": session_id,
        "thread_id": thread_id,
        SANDBOX_RUNTIME_KEY: sandbox_runtime_handle,
        "status": status,
    }
    if started_at is not None:
        row["started_at"] = started_at
    if last_active_at is not None:
        row["last_active_at"] = last_active_at
    return row


def _terminal(terminal_id: str, sandbox_runtime_handle: str, thread_id: str, created_at: str) -> dict:
    return {
        "terminal_id": terminal_id,
        SANDBOX_RUNTIME_KEY: sandbox_runtime_handle,
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
    sandbox_runtime_handle: str | None = None,
    **config_extra,
) -> dict:
    config = dict(config_extra)
    if sandbox_runtime_handle is not None:
        config["runtime_handle"] = sandbox_runtime_handle
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
                    sandbox_runtime_handle="runtime-1",
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
                    sandbox_runtime_handle="runtime-1",
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
        _sandbox(f"sandbox-{index}", provider_env_id=f"instance-{index}", sandbox_runtime_handle=f"runtime-{index}") for index in range(175)
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
                    sandbox_runtime_handle="runtime-1",
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
                    sandbox_runtime_handle="runtime-1",
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


def test_query_sandbox_allows_missing_sandbox_runtime_handle() -> None:
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
                    sandbox_runtime_handle=None,
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
                    sandbox_runtime_handle="runtime-1",
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
                    sandbox_runtime_handle="runtime-1",
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
                        sandbox_runtime_handle="runtime-1",
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
            sandbox_runtime_handle=f"runtime-{index}",
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
                    sandbox_runtime_handle="runtime-1",
                )
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-1", "provider_session_id": "instance-runtime"},
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
                    sandbox_runtime_handle="runtime-1",
                )
            ],
        }
    )

    assert repo.query_sandbox_cleanup_target("sandbox-1") == {
        "sandbox_id": "sandbox-1",
        "provider_name": "daytona_selfhost",
        "provider_env_id": "instance-sandbox",
        "sandbox_runtime_handle": "runtime-1",
    }


def test_query_sandbox_instance_id_falls_back_without_sandbox_runtime_handle() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-1",
                    provider_name="local",
                    provider_env_id="sandbox-instance-1",
                    observed_state="running",
                    sandbox_runtime_handle=None,
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
                        sandbox_runtime_handle=f"runtime-{index}",
                    )
                    for index in range(175)
                ],
                "sandbox_instances": [{SANDBOX_RUNTIME_KEY: "runtime-174", "provider_session_id": "sandbox-instance-sandbox-174"}],
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
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", sandbox_runtime_handle="runtime-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", sandbox_runtime_handle="runtime-2"),
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-2", "provider_session_id": "stale-instance-2"},
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
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", sandbox_runtime_handle="runtime-1"),
                _sandbox("sandbox-2", provider_env_id="sandbox-instance-2", sandbox_runtime_handle="runtime-2"),
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-2", "provider_session_id": "stale-instance-2"},
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
                _sandbox("sandbox-1", provider_env_id="sandbox-instance-1", sandbox_runtime_handle="runtime-1"),
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-1", "provider_session_id": "instance-runtime"},
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
                    sandbox_runtime_handle="runtime-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    sandbox_runtime_handle="runtime-paused",
                ),
                _sandbox(
                    "sandbox-stopped",
                    provider_name="docker",
                    provider_env_id="instance-stopped",
                    desired_state="stopped",
                    observed_state="stopped",
                    updated_at="2026-04-05T10:12:00",
                    sandbox_runtime_handle="runtime-stopped",
                ),
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-running", "provider_session_id": "instance-runtime"},
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
                    sandbox_runtime_handle=None,
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
                    sandbox_runtime_handle="runtime-running",
                ),
                _sandbox(
                    "sandbox-paused",
                    provider_env_id="instance-local",
                    desired_state="paused",
                    observed_state="paused",
                    updated_at="2026-04-05T10:11:00",
                    sandbox_runtime_handle="runtime-paused",
                ),
            ],
            "sandbox_instances": [
                {SANDBOX_RUNTIME_KEY: "runtime-running", "provider_session_id": "instance-runtime"},
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


def test_query_resource_rows_uses_sandbox_thread_rows_without_session_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", sandbox_runtime_handle="runtime-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    sandbox_runtime_handle="runtime-terminal",
                ),
                _sandbox(
                    "sandbox-recent",
                    provider_name="docker",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T12:00:00",
                    sandbox_runtime_handle="runtime-recent",
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
                _chat_session("sess-active", "thread-active", "runtime-active", started_at="2026-04-05T10:01:00"),
                _chat_session("sess-recent-a", "thread-old", "runtime-recent", status="closed", started_at="2026-04-05T12:01:00"),
                _chat_session("sess-recent-b", "thread-new", "runtime-recent", status="closed", started_at="2026-04-05T12:02:00"),
            ],
        }
    )

    assert repo.query_resource_rows() == [
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


def test_query_resource_rows_does_not_require_sandbox_runtime_handle() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox(
                    "sandbox-clean",
                    provider_name="docker",
                    desired_state="running",
                    observed_state="running",
                    created_at="2026-04-05T13:00:00",
                    sandbox_runtime_handle=None,
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

    assert repo.query_resource_rows() == [
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


def test_query_resource_rows_projects_sandbox_rows_without_session_rows() -> None:
    repo = _repo(
        {
            "container.sandboxes": [
                _sandbox("sandbox-active", created_at="2026-04-05T10:00:00", sandbox_runtime_handle="runtime-active"),
                _sandbox(
                    "sandbox-terminal",
                    provider_name="daytona_selfhost",
                    desired_state="paused",
                    observed_state="paused",
                    created_at="2026-04-05T11:00:00",
                    sandbox_runtime_handle="runtime-terminal",
                ),
            ],
            "container.workspaces": [
                _workspace("workspace-parent", "sandbox-terminal", updated_at="2026-04-05T11:05:00"),
            ],
            "agent.threads": [
                _thread("thread-parent", "workspace-parent", updated_at="2026-04-05T11:05:00"),
            ],
            "chat_sessions": [
                _chat_session("sess-active", "thread-active", "runtime-active", started_at="2026-04-05T10:01:00"),
            ],
        }
    )

    assert repo.query_resource_rows() == [
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


def test_query_resource_rows_bulk_loads_workspace_thread_bindings() -> None:
    counts: dict[str, int] = {}
    repo = SupabaseSandboxMonitorRepo(
        _CountingClient(
            {
                "container.sandboxes": [
                    _sandbox("sandbox-1", created_at="2026-04-05T10:00:00"),
                    _sandbox("sandbox-2", created_at="2026-04-05T11:00:00"),
                ],
                "container.workspaces": [
                    _workspace("workspace-1", "sandbox-1", updated_at="2026-04-05T10:05:00"),
                    _workspace("workspace-2", "sandbox-2", updated_at="2026-04-05T11:05:00"),
                ],
                "agent.threads": [
                    _thread("thread-1", "workspace-1", updated_at="2026-04-05T10:05:00"),
                    _thread("thread-2", "workspace-2", updated_at="2026-04-05T11:05:00"),
                ],
            },
            counts=counts,
        )
    )

    assert repo.query_resource_rows() == [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-2",
            "sandbox_id": "sandbox-2",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T11:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "sandbox_id": "sandbox-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-05T10:00:00",
        },
    ]
    assert counts["container.workspaces"] == 1
    assert counts["agent.threads"] == 1
