from types import SimpleNamespace

from backend.web.services import sandbox_service


class _FakeMonitorRepo:
    def __init__(self, rows):
        self._rows = rows

    def list_leases_with_threads(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def close(self):
        pass


class _FakeUserRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, user_id: str):
        return self._rows.get(user_id)

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
            "thread-parent": {"agent_user_id": "agent-1"},
            "subagent-deadbeef": {"agent_user_id": "agent-1"},
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
                    "member_name": "Morel",
                    "avatar_url": "/api/members/agent-1/avatar",
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
            "thread-a": {"agent_user_id": "agent-1"},
            "thread-b": {"agent_user_id": "agent-1"},
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
            "member_name": "Morel",
            "avatar_url": "/api/members/agent-1/avatar",
        },
        {
            "thread_id": "thread-b",
            "member_name": "Morel",
            "avatar_url": "/api/members/agent-1/avatar",
        },
    ]


def test_list_user_leases_hides_stopped_and_destroying_leases(monkeypatch):
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
            "thread-running": {"agent_user_id": "agent-1"},
            "thread-paused": {"agent_user_id": "agent-1"},
            "thread-detached": {"agent_user_id": "agent-1"},
            "thread-destroying": {"agent_user_id": "agent-1"},
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

    assert [lease["lease_id"] for lease in leases] == ["lease-running", "lease-paused"]
