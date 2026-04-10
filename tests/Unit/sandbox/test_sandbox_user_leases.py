from pathlib import Path
from types import SimpleNamespace

from backend.web.services import sandbox_service


def test_sandbox_service_no_longer_imports_storage_factory() -> None:
    service_source = Path("backend/web/services/sandbox_service.py").read_text(encoding="utf-8")

    assert "backend.web.core.storage_factory" not in service_source
    assert "storage.runtime" in service_source
    assert "storage.providers.sqlite.kernel" not in service_source
    assert "resolve_role_db_path" not in service_source


class _FakeMonitorRepo:
    def __init__(self, rows, instance_ids=None):
        self._rows = rows
        self._instance_ids = instance_ids or {}
        self.instance_id_calls: list[str] = []

    def list_leases_with_threads(self):
        return list(self._rows)

    def query_lease_instance_id(self, lease_id: str):
        self.instance_id_calls.append(lease_id)
        return self._instance_ids.get(lease_id)

    def query_lease(self, lease_id: str):
        for row in self._rows:
            if row.get("lease_id") == lease_id:
                return dict(row)
        return None

    def query_lease_threads(self, lease_id: str):
        return [{"thread_id": row.get("thread_id")} for row in self._rows if row.get("lease_id") == lease_id]

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows
        self.list_by_owner_calls: list[str] = []

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def list_by_owner_user_id(self, owner_user_id: str):
        self.list_by_owner_calls.append(owner_user_id)
        result = []
        for thread_id, row in self._rows.items():
            if row.get("owner_user_id") == owner_user_id:
                result.append({"id": thread_id, **row})
        return result

    def close(self):
        pass


class _FakeUserRepo:
    def __init__(self, rows):
        self._rows = rows
        self.list_by_owner_calls: list[str] = []

    def get_by_id(self, user_id: str):
        return self._rows.get(user_id)

    def list_by_owner_user_id(self, owner_user_id: str):
        self.list_by_owner_calls.append(owner_user_id)
        return [row for row in self._rows.values() if getattr(row, "owner_user_id", None) == owner_user_id]

    def close(self):
        pass


def test_list_user_leases_hides_subagent_threads_and_deduplicates_visible_agents(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "subagent-deadbeef",
        },
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-parent": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "subagent-deadbeef": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert leases == [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe": {
                "id": "daytona:default",
                "name": "Daytona Default",
                "desc": "Default recipe for daytona",
                "provider_type": "daytona",
                "features": {"lark_cli": False},
                "configurable_features": {"lark_cli": True},
                "feature_options": [
                    {
                        "key": "lark_cli",
                        "name": "Lark CLI",
                        "description": "在 sandbox 初始化时懒安装并校验。",
                        "icon": "feishu",
                    }
                ],
                "builtin": True,
            },
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_ids": ["thread-parent"],
            "agents": [
                {
                    "thread_id": "thread-parent",
                    "agent_user_id": "agent-1",
                    "agent_name": "Morel",
                    "avatar_url": "/api/users/agent-1/avatar",
                }
            ],
            "recipe_name": "Daytona Default",
        }
    ]


def test_list_user_leases_keeps_distinct_visible_threads_even_for_same_member(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/tmp/app",
            "thread_id": "thread-a",
        },
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/tmp/app",
            "thread_id": "thread-b",
        },
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-b": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert leases[0]["thread_ids"] == ["thread-a", "thread-b"]
    assert leases[0]["agents"] == [
        {
            "thread_id": "thread-a",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": "/api/users/agent-1/avatar",
        },
        {
            "thread_id": "thread-b",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": "/api/users/agent-1/avatar",
        },
    ]


def test_list_user_leases_uses_owner_bulk_repo_surfaces(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/tmp/app",
            "thread_id": "thread-a",
        },
        {
            "lease_id": "lease-2",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:01:00Z",
            "cwd": "/tmp/app2",
            "thread_id": "thread-b",
        },
    ]

    class _BulkOnlyThreadRepo(_FakeThreadRepo):
        def get_by_id(self, thread_id: str):
            raise AssertionError(f"unexpected per-thread lookup: {thread_id}")

    class _BulkOnlyUserRepo(_FakeUserRepo):
        def get_by_id(self, user_id: str):
            raise AssertionError(f"unexpected per-user lookup: {user_id}")

    thread_repo = _BulkOnlyThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-b": {"agent_user_id": "agent-2", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _BulkOnlyUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
            "agent-2": SimpleNamespace(id="agent-2", display_name="Toad", avatar=None, owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [lease["lease_id"] for lease in leases] == ["lease-1", "lease-2"]
    assert thread_repo.list_by_owner_calls == ["owner-1"]
    assert user_repo.list_by_owner_calls == ["owner-1"]


def test_list_user_leases_only_queries_runtime_session_id_once_per_lease(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/tmp/app",
            "thread_id": "thread-a",
        },
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:01Z",
            "cwd": "/tmp/app",
            "thread_id": "thread-b",
        },
    ]
    monitor_repo = _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-1"})
    thread_repo = _FakeThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-b": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=True,
    )

    assert leases[0]["runtime_session_id"] == "provider-session-1"
    assert monitor_repo.instance_id_calls == ["lease-1"]


def test_list_user_leases_prefers_current_instance_id_without_extra_probe(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "current_instance_id": "provider-session-inline",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
    ]
    monitor_repo = _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-probed"})
    thread_repo = _FakeThreadRepo(
        {
            "thread-parent": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=True,
    )

    assert leases[0]["runtime_session_id"] == "provider-session-inline"
    assert monitor_repo.instance_id_calls == []


def test_list_user_leases_keeps_runtime_session_ids_per_lease(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
    ]
    thread_repo = _FakeThreadRepo({"thread-parent": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"}})
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(
        sandbox_service,
        "make_sandbox_monitor_repo",
        lambda: _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-1"}),
    )

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=True,
    )

    assert leases[0]["runtime_session_id"] == "provider-session-1"


def test_list_user_leases_skips_runtime_session_probe_by_default(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
    ]
    monitor_repo = _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-1"})
    thread_repo = _FakeThreadRepo({"thread-parent": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"}})
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert "runtime_session_id" not in leases[0]
    assert monitor_repo.instance_id_calls == []


def test_resolve_owned_lease_filters_to_single_authorized_lease(monkeypatch):
    rows = [
        {
            "lease_id": "lease-1",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/home/daytona/files/app",
            "thread_id": "thread-parent",
        },
        {
            "lease_id": "lease-2",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:01:00Z",
            "cwd": "/tmp/other",
            "thread_id": "thread-other",
        },
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-parent": {"agent_user_id": "agent-1"},
            "thread-other": {"agent_user_id": "agent-2"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
            "agent-2": SimpleNamespace(id="agent-2", display_name="Toad", avatar=None, owner_user_id="owner-2"),
        }
    )

    monkeypatch.setattr(
        sandbox_service,
        "make_sandbox_monitor_repo",
        lambda: _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-1"}),
    )

    lease = sandbox_service.resolve_owned_lease(
        "owner-1",
        "lease-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert lease == {
        "lease_id": "lease-1",
        "provider_name": "daytona_selfhost",
        "recipe_id": "daytona:default",
        "recipe_json": None,
        "observed_state": "running",
        "desired_state": "running",
        "created_at": "2026-04-07T10:00:00Z",
        "cwd": "/home/daytona/files/app",
        "thread_id": "thread-parent",
        "thread_ids": ["thread-parent"],
        "agents": [
            {
                "thread_id": "thread-parent",
                "agent_user_id": "agent-1",
                "agent_name": "Morel",
                "avatar_url": "/api/users/agent-1/avatar",
            }
        ],
        "recipe": {
            "id": "daytona:default",
            "name": "Daytona Default",
            "desc": "Default recipe for daytona",
            "provider_type": "daytona",
            "features": {"lark_cli": False},
            "configurable_features": {"lark_cli": True},
            "feature_options": [
                {
                    "key": "lark_cli",
                    "name": "Lark CLI",
                    "description": "在 sandbox 初始化时懒安装并校验。",
                    "icon": "feishu",
                }
            ],
            "builtin": True,
        },
        "recipe_name": "Daytona Default",
        "runtime_session_id": "provider-session-1",
    }


def test_list_user_leases_keeps_detached_but_hides_destroying_leases(monkeypatch):
    rows = [
        {
            "lease_id": "lease-running",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-07T10:00:00Z",
            "cwd": "/tmp/running",
            "thread_id": "thread-running",
        },
        {
            "lease_id": "lease-paused",
            "provider_name": "daytona_selfhost",
            "recipe_id": "daytona:default",
            "recipe_json": None,
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-07T10:01:00Z",
            "cwd": "/home/daytona/app",
            "thread_id": "thread-paused",
        },
        {
            "lease_id": "lease-detached",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-07T10:02:00Z",
            "cwd": "/tmp/stale",
            "thread_id": "thread-detached",
        },
        {
            "lease_id": "lease-destroying",
            "provider_name": "local",
            "recipe_id": "local:default",
            "recipe_json": None,
            "observed_state": "paused",
            "desired_state": "destroyed",
            "created_at": "2026-04-07T10:03:00Z",
            "cwd": "/tmp/destroying",
            "thread_id": "thread-destroying",
        },
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-running": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-paused": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-detached": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-destroying": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [lease["lease_id"] for lease in leases] == ["lease-running", "lease-paused", "lease-detached"]
